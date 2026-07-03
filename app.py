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
        
    try:
        patent_vector = patent["embeddings"][language]["vector"]
    except KeyError:
        return jsonify({"error": f"Embeddings vector not found for language '{language}'"}), 404

    # 2. Ricerca Vettoriale Industrie
    industries_pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_INDUSTRIES,
                "path": f"embeddings.{language}.vector",
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
    
    # 3. Filtraggio Soglie e Estrazione Codici
    list_a_codes = [] # similarity >= 0.6
    list_b_codes = [] # similarity <= 0.2
    
    for ind in industries_results:
        sim = ind.get("similarity", 0)
        code = ind.get("code")
        if not code:
            continue
            
        if sim >= 0.6:
            list_a_codes.append(code)
        elif sim <= 0.2:
            list_b_codes.append(code)

    all_nace_codes = list_a_codes + list_b_codes
    
    # Se non c'è nessun match, restituiamo liste vuote subito per evitare errori nel filtro
    if not all_nace_codes:
        return jsonify({"group_1": [], "group_2": []})

    # --- FASE 2: Micro-matching (Patent vs Company Description) ---
    
    companies_pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_COMPANIES,
                "path": f"embeddings.{language}.vector",
                "queryVector": patent_vector,
                # Il filtro è stato spostato in uno stage $match successivo per evitare l'errore "needs to be indexed as filter"
                # fino a quando l'indice su MongoDB Atlas non verrà aggiornato per includere questo campo come token.
                "numCandidates": 1000,
                "limit": 500 # Aumentato per compensare il filtraggio successivo
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
                "similarity_desc": {"$meta": "vectorSearchScore"}
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
            "location_province": comp.get("location", {}).get("province", "N/A"),
            "similarity_desc": round(comp.get("similarity_desc", 0), 4),
            "rnd_intensity": round(rnd_intensity, 6) if rnd_intensity is not None else 0.0
        }
        
        # Split nei gruppi in base alla Lista di origine
        if nace_code in list_a_codes:
            group_1.append(company_data)
        elif nace_code in list_b_codes:
            group_2.append(company_data)
            
    # Ordinamento decrescente
    group_1.sort(key=lambda x: x["rnd_intensity"], reverse=True)
    group_2.sort(key=lambda x: x["rnd_intensity"], reverse=True)
    
    return jsonify({
        "group_1": group_1,
        "group_2": group_2
    })

if __name__ == "__main__":
    app.run(debug=True, port=5000)
