import os
from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from dotenv import load_dotenv

# Carica variabili d'ambiente
load_dotenv()

app = Flask(__name__)

# Configurazione MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "patent_matching")

# NOMI DEGLI INDICI DI VECTOR SEARCH
# Assicurarsi che questi indici siano creati in MongoDB Atlas
VECTOR_INDEX_INDUSTRIES = "industries_vector_it_index"
VECTOR_INDEX_COMPANIES = "companies_vector_it_index"

client = MongoClient(MONGODB_URI)
db = client[MONGODB_DB_NAME]

# Pre-warm MongoDB connection synchronously at startup
try:
    client.admin.command('ping')
    print("--- Database connection successfully established and warmed up! ---")
except Exception as e:
    print(f"Warning: could not pre-warm database connection: {e}")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/scout", methods=["POST"])
def scout():
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload provided"}), 400

    patent_id = data.get("Patent_ID")
    language = data.get("Language", "it") # 'it' o 'en'
    
    if not patent_id:
        return jsonify({"error": "Patent_ID is required"}), 400

    # --- FASE 1: Macro-filtro (Patent vs Industry) ---
    
    # 1. Recupero Vettore Brevetto
    patent = db.patents.find_one({"scheda_id": patent_id})
    if not patent:
        return jsonify({"error": f"Patent with _id '{patent_id}' not found"}), 404
        
    # Usiamo il vettore italiano del brevetto come base (poiché i brevetti sono redatti in italiano).
    # Grazie al modello di embedding multilingua, questo vettore può essere confrontato direttamente
    # con le descrizioni aziendali in inglese.
    try:
        patent_vector = patent["embeddings"]["it"]["vector"]
        if not patent_vector:
            patent_vector = patent["embeddings"][language]["vector"]
    except KeyError:
        try:
            patent_vector = patent["embeddings"][language]["vector"]
        except KeyError:
            return jsonify({"error": f"Embeddings vector not found for patent '{patent_id}'"}), 404

    if not patent_vector:
        return jsonify({"error": f"Embeddings vector is empty for patent '{patent_id}'"}), 400

    # 2. Ricerca Vettoriale Industrie (sempre in italiano per accuratezza linguistica delle categorie NACE)
    VECTOR_INDEX_INDUSTRIES = "industries_vector_it_index"
    industries_pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_INDUSTRIES,
                "path": "embeddings.it.vector",
                "queryVector": patent_vector,
                "numCandidates": 100,
                "limit": 50
            }
        },
        {
            "$project": {
                "code": 1,
                "similarity": {"$meta": "vectorSearchScore"}
            }
        }
    ]
    
    industries_results = list(db.industries.aggregate(industries_pipeline))
    
    # 3. Filtraggio per posizioni in classifica (Top-K partition)
    # Rimuoviamo elementi senza codice valido mantenendo l'ordine decrescente di similarità
    valid_industries = [ind for ind in industries_results if ind.get("code")]
    
    # I primi 10 codici vanno nel Gruppo 1 (Core Match)
    list_a_codes = [ind["code"] for ind in valid_industries[:10]]
    
    # I successivi 25 codici (dal 10 al 35) vanno nel Gruppo 2 (Spillover Match)
    list_b_codes = [ind["code"] for ind in valid_industries[10:35]]

    all_nace_codes = list_a_codes + list_b_codes
    
    # Se non c'è nessun match, restituiamo liste vuote subito per evitare errori nel filtro
    if not all_nace_codes:
        return jsonify({"group_1": [], "group_2": []})

    # --- FASE 2: Micro-matching (Patent vs Company Description) ---
    
    # Seleziona l'indice corretto in base alla lingua (l'indice inglese è creato su Atlas)
    if language == "en":
        vector_index_companies = "companies_vector_en_index"
    else:
        vector_index_companies = "companies_vector_it_index"

    companies_pipeline = [
        {
            "$vectorSearch": {
                "index": vector_index_companies,
                "path": f"embeddings.{language}.vector",
                "queryVector": patent_vector,
                # Il filtro è stato spostato in uno stage $match successivo per evitare l'errore "needs to be indexed as filter"
                # fino a quando l'indice su MongoDB Atlas non verrà aggiornato per includere questo campo come token.
                "numCandidates": 1500,
                "limit": 800 # Aumentato per compensare il filtraggio successivo
            }
        },
        {
            "$match": {
                "industry_classification.nace_rev_2.code": {"$in": all_nace_codes}
            }
        },
        {
            "$project": {
                "company_name": 1,
                "tax_code": 1,
                "location.province": 1,
                "metrics.rnd_intensity": 1,
                "financials.rnd_expenses_th_eur.last_available_year": 1,
                "financials.revenues_th_eur": 1,
                "industry_classification.nace_rev_2.code": 1,
                "similarity_desc": {"$meta": "vectorSearchScore"},
                "contacts": 1
            }
        }
    ]
    
    companies_results = list(db.companies.aggregate(companies_pipeline))
    
    # --- FASE 3: R&D Index e Ordinamento ---
    
    group_1 = []
    group_2 = []
    
    for comp in companies_results:
        # Recupera NACE per capire a quale gruppo appartiene
        try:
            nace_code = comp["industry_classification"]["nace_rev_2"]["code"]
        except KeyError:
            continue
            
        # Recupero Metrica R&D o Fallback Logic
        rnd_intensity = None
        if "metrics" in comp and "rnd_intensity" in comp["metrics"]:
            rnd_intensity = comp["metrics"]["rnd_intensity"]
            
        if rnd_intensity is None:
            # Fallback calcolo manuale
            try:
                rnd_expenses = comp["financials"]["rnd_expenses_th_eur"]["last_available_year"]
                revenues = comp["financials"]["revenues_th_eur"]
                if revenues and revenues > 0:
                    rnd_intensity = rnd_expenses / revenues
                else:
                    rnd_intensity = 0.0
            except (KeyError, TypeError, ZeroDivisionError):
                rnd_intensity = 0.0
                
        # Preparazione oggetto output
        company_data = {
            "company_name": comp.get("company_name", "N/A"),
            "tax_code": comp.get("tax_code", "N/A"),
            "cciaa_number": comp.get("cciaa_number", "N/A"),
            "location": comp.get("location", {}),
            "location_province": comp.get("location", {}).get("province", "N/A"),
            "industry_classification": comp.get("industry_classification", {}),
            "business_profile": comp.get("business_profile", {}),
            "financials": comp.get("financials", {}),
            "metrics": comp.get("metrics", {}),
            "similarity_desc": round(comp.get("similarity_desc", 0), 4),
            "rnd_intensity": round(rnd_intensity, 6) if rnd_intensity is not None else 0.0,
            "contacts": comp.get("contacts", {})
        }
        
        # Split nei gruppi in base alla combinazione di Punteggio e Codice NACE (Core vs Spillover)
        sim_score = comp.get("similarity_desc", 0)
        
        if sim_score >= 0.75:
            # Punteggio eccellente: va sempre nel Gruppo 1 (Core Match)
            group_1.append(company_data)
        elif nace_code in list_a_codes and sim_score >= 0.70:
            # Settori primari (Core): affinità media va nel Gruppo 2
            group_2.append(company_data)
        elif nace_code in list_b_codes and sim_score >= 0.65:
            # Settori secondari (Spillover): soglia più tollerante per intercettare mercati correlati
            group_2.append(company_data)
            
    # Ordinamento decrescente
    group_1.sort(key=lambda x: x["rnd_intensity"], reverse=True)
    group_2.sort(key=lambda x: x["rnd_intensity"], reverse=True)
    
    return jsonify({
        "patent_title": patent.get("title", "N/A"),
        "patent_url": patent.get("url", ""),
        "group_1": group_1,
        "group_2": group_2
    })

@app.route("/api/v1/proposals/generate", methods=["POST"])
def generate_project_proposal():
    from src.services.proposal_service import generate_proposal
    
    data = request.json or {}
    company_id = data.get("company_id")
    patent_id = data.get("patent_id")
    force_regenerate = data.get("force_regenerate", False)
    
    if not company_id or not patent_id:
        return jsonify({"error": "Parameters 'company_id' and 'patent_id' are required."}), 400
        
    try:
        proposal = generate_proposal(
            company_id=company_id,
            patent_id=patent_id,
            force_regenerate=force_regenerate,
            db=db
        )
        return jsonify(proposal), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        app.logger.exception("Failed generating proposal")
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

@app.route("/api/v1/patents", methods=["GET"])
def get_all_patents():
    try:
        patents_cursor = db.patents.find(
            {}, 
            {"scheda_id": 1, "title": 1, "applications": 1, "url": 1, "_id": 0}
        )
        patents_list = list(patents_cursor)
        response = jsonify(patents_list)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response, 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def get_mock_gatekeepers(company_name):
    """Generates realistic UNIBO alumni profiles working at the company."""
    import random
    first_names_m = ["Alessandro", "Francesco", "Andrea", "Matteo", "Gabriele", "Davide", "Marco", "Lorenzo", "Riccardo", "Filippo"]
    first_names_f = ["Giulia", "Sofia", "Chiara", "Francesca", "Sara", "Elena", "Martina", "Alice", "Giorgia", "Alessia"]
    last_names = ["Rossi", "Ferrari", "Russo", "Bianchi", "Romano", "Gallo", "Costa", "Fontana", "Conti", "Esposito", "Bruno", "Rizzo", "Moretti", "Barbieri"]
    
    roles = [
        "R&D Engineer / Specialist",
        "Innovation Manager",
        "Product Owner & Technology Lead",
        "Senior Firmware Developer",
        "Process Innovation Specialist",
        "Materials Scientist - R&D Division",
        "Data Scientist & AI Researcher",
        "Head of Engineering",
        "Technology Transfer Coordinator",
        "Operations & Innovation Specialist"
    ]
    
    degrees = [
        "Laurea Magistrale in Ingegneria Meccatronica (UNIBO)",
        "Laurea Magistrale in Ingegneria Informatica (UNIBO)",
        "Laurea Magistrale in Biotecnologie Industriali (UNIBO)",
        "Dottorato di Ricerca (PhD) in Advanced Automotive Engineering (UNIBO)",
        "Laurea Magistrale in Fisica della Materia (UNIBO)",
        "Laurea Magistrale in Chimica Industriale (UNIBO)"
    ]
    
    snippets = [
        "Ex-studente UNIBO attualmente impegnato nello sviluppo di nuove tecnologie e brevetti presso {company}.",
        "Ha svolto la tesi di laurea in collaborazione con {company} ed è stato assunto nel team R&D.",
        "Responsabile del trasferimento tecnologico e dell'integrazione di sistemi innovativi presso {company}.",
        "Specialista nello sviluppo firmware e prototipazione avanzata per i prodotti di {company}."
    ]
    
    gatekeepers = []
    num_gatekeepers = random.randint(2, 3)
    
    for i in range(num_gatekeepers):
        gender = random.choice(["M", "F"])
        first_name = random.choice(first_names_m) if gender == "M" else random.choice(first_names_f)
        last_name = random.choice(last_names)
        full_name = f"{first_name} {last_name}"
        
        role = random.choice(roles)
        degree = random.choice(degrees)
        snippet = random.choice(snippets).format(company=company_name)
        
        linkedin_url = f"https://www.linkedin.com/search/results/people/?keywords={first_name}%20{last_name}%20{company_name}"
        
        gatekeepers.append({
            "name_role": f"{full_name} - {role} at {company_name}",
            "degree": degree,
            "url": linkedin_url,
            "snippet": f"{degree}. {snippet}",
            "source": "Mock Data (Fallback)"
        })
        
    return gatekeepers

@app.route("/api/v1/companies/<company_id>/gatekeepers", methods=["GET"])
def get_company_gatekeepers(company_id):
    try:
        # Trova l'azienda nel database
        company = db.companies.find_one({"$or": [{"_id": company_id}, {"tax_code": company_id}]})
        if not company:
            return jsonify({"error": f"Company with identifier '{company_id}' not found."}), 404
        
        company_name = company.get("company_name", "N/A")
        
        # Recupera le credenziali per Google Custom Search
        google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        google_cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        
        # Se le credenziali sono presenti, facciamo la ricerca reale
        if google_api_key and google_cx:
            import urllib.request
            import urllib.parse
            import json
            
            query = f'site:linkedin.com/in/ "Università di Bologna" OR "UNIBO" "{company_name}" ("R&D" OR "Ricerca" OR "Sviluppo" OR "Innovation" OR "Manager" OR "Director" OR "Specialist" OR "Alumni")'
            encoded_query = urllib.parse.quote(query)
            url = f"https://www.googleapis.com/customsearch/v1?key={google_api_key}&cx={google_cx}&q={encoded_query}"
            
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10) as response:
                    res_data = json.loads(response.read().decode())
                    items = res_data.get("items", [])
                    gatekeepers = []
                    for item in items:
                        title = item.get("title", "")
                        title_clean = title.split(" | ")[0] if " | " in title else title
                        title_clean = title_clean.split(" - LinkedIn")[0] if " - LinkedIn" in title_clean else title_clean
                        
                        gatekeepers.append({
                            "name_role": title_clean,
                            "url": item.get("link", "#"),
                            "snippet": item.get("snippet", ""),
                            "source": "Google Search (Real)"
                        })
                    
                    if not gatekeepers:
                        gatekeepers = get_mock_gatekeepers(company_name)
                    
                    return jsonify({
                        "company_name": company_name,
                        "gatekeepers": gatekeepers,
                        "is_mock": False
                    }), 200
            except Exception as e:
                app.logger.error(f"Google Search API error: {e}")
                return jsonify({
                    "company_name": company_name,
                    "gatekeepers": get_mock_gatekeepers(company_name),
                    "is_mock": True,
                    "error_details": str(e)
                }), 200
        else:
            # Fallback ai mock data se mancano le credenziali
            return jsonify({
                "company_name": company_name,
                "gatekeepers": get_mock_gatekeepers(company_name),
                "is_mock": True
            }), 200
            
    except Exception as e:
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
