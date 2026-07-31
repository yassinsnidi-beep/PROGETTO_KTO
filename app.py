import os
import certifi
from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from dotenv import load_dotenv

# Carica variabili d'ambiente dal file .env
load_dotenv()

app = Flask(__name__)

# Configurazione MongoDB
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "patent_matching")

# NOMI DEGLI INDICI DI VECTOR SEARCH
VECTOR_INDEX_INDUSTRIES = "industries_vector_it_index"
VECTOR_INDEX_COMPANIES = "companies_vector_it_index"

client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
db = client[MONGODB_DB_NAME]

db_connected = False
# Pre-warm MongoDB connection synchronously at startup
try:
    client.admin.command('ping')
    print("--- Database connection successfully established and warmed up! ---")
    db_connected = True
except Exception as e:
    print(f"Warning: could not pre-warm database connection: {e}")
    db_connected = False

@app.route("/")
def index():
    return render_template("index.html")

def _get_patent_by_id(patent_id):
    if db_connected:
        try:
            p = db.patents.find_one({"scheda_id": patent_id})
            if p:
                return p
        except Exception:
            pass
    try:
        import pandas as pd
        import glob
        excel_path = "data/archive/patents/brevetti_unibo (1).xlsx"
        if not os.path.exists(excel_path):
            xlsx_files = glob.glob("data/**/patents/*.xlsx", recursive=True) + glob.glob("*.xlsx")
            if xlsx_files:
                excel_path = xlsx_files[0]
        
        if os.path.exists(excel_path):
            df = pd.read_excel(excel_path, sheet_name="Brevetti")
            col_mapping = {}
            for col in df.columns:
                norm = str(col).lower().replace(" ", "").replace("_", "")
                col_mapping[norm] = col
            
            scheda_col = col_mapping.get("schedaid") or col_mapping.get("idscheda")
            if scheda_col:
                df[scheda_col] = df[scheda_col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
                row_matches = df[df[scheda_col] == str(patent_id).strip()]
                if not row_matches.empty:
                    row = row_matches.iloc[0]
                    title_col = col_mapping.get("titolo") or col_mapping.get("title")
                    url_col = col_mapping.get("url") or col_mapping.get("link")
                    desc_col = col_mapping.get("descrizionecompleta") or col_mapping.get("fulldescription")
                    abs_col = col_mapping.get("abstract")
                    
                    title = str(row[title_col]) if title_col and pd.notna(row[title_col]) else ""
                    url = str(row[url_col]) if url_col and pd.notna(row[url_col]) else ""
                    
                    full_desc = str(row[desc_col]) if desc_col and pd.notna(row[desc_col]) else ""
                    abstract = str(row[abs_col]) if abs_col and pd.notna(row[abs_col]) else ""
                    
                    return {
                        "scheda_id": patent_id,
                        "title": title,
                        "url": url,
                        "full_description": full_desc,
                        "abstract": abstract
                    }
    except Exception as e:
        app.logger.error(f"Error reading patent from Excel: {e}")
    return None

def _get_partners_tax_code_map():
    """
    Returns a dictionary mapping normalized tax code (stripped of leading zeros)
    to partner details.
    """
    NAME_TO_TAX_CODE_FALLBACK = {
        "CAMST": "0311310379",
        "Automobili Lamborghini S.p.A.": "03049840378",
        "DUCATI": "05113870967",
        "FEV": "02293411202",
        "HPE COXA": "02302301202",
        "MARELLI EUROPE S.p.A.": "08082910967",
        "ENI S.p.A.": "00905811006",
        "Gruppo Hera": "04245520376",
        "Rosetti Marino": "0082100397",
        "Snam": "13271390151",
        "Alfasigma": "03432221202",
        "Atos Italia S.p.A.": "13054170154",
        "Hewlett Packard Enterprise Italia": "09205560965",
        "STMicroelectronics": "00870460159",
        "COESIA": "03378511200",
        "I.M.A. SPA": "0307140376",
        "SACMI IMOLA S.C.": "0287010375",
        "SCM Group": "0126480409",
        "TECHNOGYM": "06250230965",
        "FONDAZIONE FASHION RESEARCH ITALY": "02402671206",
        "GRUPPO UNIPOL": "0818570012",
        "REKEEP": "02402671206",
        "ALSTOM FERROVIARIA": "05623040156",
        "Autostrade per l'Italia": "07543501001",
        "ASSORESTAURO": "97401730154",
        "CNA Associazione di Bologna": "02235980378",
        "Colibrì Consorzio Ospedaliero": "03028211204",
        "Federunacoma": "07361731007",
        "Legacoop Romagna": "90022370404"
    }
    
    tax_code_map = {}
    
    # Se il database è connesso, costruiamo la mappa reale leggendo unibo_partners
    if db_connected:
        try:
            partners = list(db.unibo_partners.find())
            matched_companies = list(db.companies.find({"is_unibo_partner": True}, {"tax_code": 1, "partnership_id": 1}))
            partnership_to_tax_code = {str(c["partnership_id"]): c["tax_code"] for c in matched_companies if "partnership_id" in c}
            
            for p in partners:
                p_id = str(p["_id"])
                company_name = p.get("company_name", "")
                
                # Trova codice fiscale reale
                tax_code = partnership_to_tax_code.get(p_id)
                if not tax_code:
                    tax_code = NAME_TO_TAX_CODE_FALLBACK.get(company_name)
                    
                if tax_code:
                    norm_code = str(tax_code).strip().lstrip('0')
                    tax_code_map[norm_code] = {
                        "sector": p.get("sector", "Generale"),
                        "company_name": company_name,
                        "agreement_type": p.get("agreement_type", "Accordo quadro"),
                        "macro_themes": p.get("macro_themes", []),
                        "joint_labs": p.get("joint_labs", [])
                    }
            return tax_code_map
        except Exception as e:
            app.logger.error(f"Error building partners tax code map: {e}")

    # Fallback statico per modalità Excel o in caso di errore
    for name, tax_code in NAME_TO_TAX_CODE_FALLBACK.items():
        norm_code = str(tax_code).strip().lstrip('0')
        tax_code_map[norm_code] = {
            "sector": "Industria e Associazione",
            "company_name": name,
            "agreement_type": "Accordo quadro",
            "macro_themes": ["Sviluppo Congiunto", "Collaborazione Scientifica"],
            "joint_labs": []
        }
    return tax_code_map

def _scout_companies_from_excel(patent, only_partners=False):
    import pandas as pd
    
    excel_path = "Aida_FILE_COMPLETO.xlsx"
    if not os.path.exists(excel_path):
        return [], []
        
    df = pd.read_excel(excel_path, sheet_name="Results")
    col_map = {str(c).lower().replace(" ", "").replace("_", "").replace("\n", ""): c for c in df.columns}
    
    comp_name_col = col_map.get("companyname")
    prov_col = col_map.get("province")
    region_col = col_map.get("registeredofficeaddress-region")
    tax_col = col_map.get("taxcodenumber")
    cciaa_col = col_map.get("cciaanumber")
    nace_col = col_map.get("nacerev.2")
    nace_desc_col = col_map.get("nacerev.2description")
    ateco_col = col_map.get("ateco2007code")
    ateco_desc_col = col_map.get("ateco2007description")
    desc_it_col = col_map.get("tradedescription(it)")
    desc_en_col = col_map.get("tradedescription(gb)")
    
    rev_col = col_map.get("revenuesfromsalesandservicestheurlastavail.yr")
    emp_col = col_map.get("numberofemployeeslastavail.yr")
    rnd_col = col_map.get("researchanddev.exp.theurlastavail.yr")
    web_col = col_map.get("website")
    tel_col = col_map.get("telephonenumber")
    
    title = patent.get("title", "")
    full_desc = patent.get("full_description", "")
    abstract = patent.get("abstract", "")
    text_to_analyze = (title + " " + full_desc + " " + abstract).lower()
    
    keywords = []
    if any(k in text_to_analyze for k in ["kiwi", "melo", "ciliegio", "agraria", "coltiv", "variet", "piant"]):
        keywords = ["agricol", "coltiv", "frutt", "kiwi", "melo", "piant", "alimen", "sweet"]
    elif any(k in text_to_analyze for k in ["linfoma", "protesi", "cardio", "medica", "salute", "farmac", "biotec"]):
        keywords = ["medico", "farmaceutic", "salute", "biotec", "clinica", "ospedal", "terap", "chirurg", "protesi"]
    elif any(k in text_to_analyze for k in ["software", "calcolo", "algoritm", "digitale", "computer"]):
        keywords = ["software", "informatica", "digitale", "calcolo", "programma", "it", "tecnolog"]
    elif any(k in text_to_analyze for k in ["energia", "clima", "batteria", "pannell", "elettr"]):
        keywords = ["energia", "elettr", "batteria", "fotovolta", "pannell", "solare", "rinnovab"]
    else:
        import re
        words = re.findall(r"\w{5,}", text_to_analyze)
        keywords = list(set(words))[:10]
        
    scores = []
    for idx, row in df.iterrows():
        comp_name = str(row[comp_name_col]) if comp_name_col and pd.notna(row[comp_name_col]) else ""
        if not comp_name:
            scores.append(-1.0)
            continue
            
        desc_it = str(row[desc_it_col]).lower() if desc_it_col and pd.notna(row[desc_it_col]) else ""
        desc_en = str(row[desc_en_col]).lower() if desc_en_col and pd.notna(row[desc_en_col]) else ""
        nace_desc = str(row[nace_desc_col]).lower() if nace_desc_col and pd.notna(row[nace_desc_col]) else ""
        ateco_desc = str(row[ateco_desc_col]).lower() if ateco_desc_col and pd.notna(row[ateco_desc_col]) else ""
        
        combined_text = f"{comp_name} {desc_it} {desc_en} {nace_desc} {ateco_desc}".lower()
        
        match_count = 0
        for kw in keywords:
            if kw in combined_text:
                match_count += 1
                
        sim_score = 0.5 + min(match_count * 0.08, 0.45)
        sim_score += random.uniform(-0.02, 0.02)
        sim_score = min(max(sim_score, 0.4), 0.98)
        scores.append(sim_score)
        
    df["_sim_score"] = scores
    valid_df = df[df["_sim_score"] > 0].copy()
    valid_df = valid_df.sort_values(by="_sim_score", ascending=False)
    top_df = valid_df.head(40)
    
    partners_map = _get_partners_tax_code_map()
    
    group_1, group_2 = [], []
    for idx, row in top_df.iterrows():
        comp_name = str(row[comp_name_col]).strip() if comp_name_col and pd.notna(row[comp_name_col]) else "N/A"
        tax_code = str(row[tax_col]).strip() if tax_col and pd.notna(row[tax_col]) else "N/A"
        if tax_code.endswith(".0"):
            tax_code = tax_code[:-2]
            
        cciaa = str(row[cciaa_col]).strip() if cciaa_col and pd.notna(row[cciaa_col]) else "N/A"
        if cciaa.endswith(".0"):
            cciaa = cciaa[:-2]
            
        province = str(row[prov_col]).strip() if prov_col and pd.notna(row[prov_col]) else "N/A"
        region = str(row[region_col]).strip() if region_col and pd.notna(row[region_col]) else "N/A"
        
        nace_code = str(row[nace_col]).strip() if nace_col and pd.notna(row[nace_col]) else "N/A"
        if nace_code.endswith(".0"):
            nace_code = nace_code[:-2]
            
        nace_desc_val = str(row[nace_desc_col]).strip() if nace_desc_col and pd.notna(row[nace_desc_col]) else "N/A"
        
        ateco_code = str(row[ateco_col]).strip() if ateco_col and pd.notna(row[ateco_col]) else "N/A"
        if ateco_code.endswith(".0"):
            ateco_code = ateco_code[:-2]
            
        ateco_desc_val = str(row[ateco_desc_col]).strip() if ateco_desc_col and pd.notna(row[ateco_desc_col]) else "N/A"
        
        desc_it = str(row[desc_it_col]).strip() if desc_it_col and pd.notna(row[desc_it_col]) else "N/A"
        desc_en = str(row[desc_en_col]).strip() if desc_en_col and pd.notna(row[desc_en_col]) else "N/A"
        
        try:
            revenues = float(row[rev_col]) if rev_col and pd.notna(row[rev_col]) else 0.0
        except ValueError:
            revenues = 0.0
            
        try:
            employees = int(row[emp_col]) if emp_col and pd.notna(row[emp_col]) else 0
        except ValueError:
            employees = 0
            
        rnd_val = row[rnd_col] if rnd_col and pd.notna(row[rnd_col]) else 0.0
        if rnd_val == "n.a." or rnd_val == "N/A" or pd.isna(rnd_val):
            rnd_val = 0.0
        else:
            try:
                rnd_val = float(rnd_val)
            except ValueError:
                rnd_val = 0.0
                
        rnd_intensity = rnd_val / revenues if revenues > 0 else 0.0
        
        location = {
            "province": province,
            "region": region,
            "country": "Italy"
        }
        
        web = str(row[web_col]).strip() if web_col and pd.notna(row[web_col]) else ""
        tel = str(row[tel_col]).strip() if tel_col and pd.notna(row[tel_col]) else ""
        if tel.endswith(".0"):
            tel = tel[:-2]
            
        contacts = {
            "website": web,
            "phone": tel,
            "email": f"info@{comp_name.lower().replace(' ', '').replace('.', '').replace(',', '')}.it" if web else ""
        }
        
        sim_score = row["_sim_score"]
        
        # Real partner check by tax code
        clean_tc = str(tax_code).strip().lstrip('0')
        is_partner = clean_tc in partners_map
        if only_partners and not is_partner:
            continue
            
        partnership = None
        if is_partner:
            partnership = partners_map[clean_tc]
            
        company_data = {
            "company_name": comp_name,
            "tax_code": tax_code,
            "cciaa_number": cciaa,
            "location": location,
            "location_province": province,
            "industry_classification": {
                "nace_rev_2": {"code": nace_code, "description": nace_desc_val},
                "ateco_2007": {"code": ateco_code, "description": ateco_desc_val}
            },
            "business_profile": {
                "trade_description_it": desc_it,
                "trade_description_gb": desc_en
            },
            "financials": {
                "revenues_th_eur": revenues,
                "employees": employees,
                "rnd_expenses_th_eur": {"last_available_year": rnd_val}
            },
            "metrics": {
                "rnd_intensity": rnd_intensity,
                "technology_adoption_capacity_score": round(rnd_intensity * 100, 2)
            },
            "similarity_desc": round(sim_score, 4),
            "rnd_intensity": round(rnd_intensity, 6),
            "contacts": contacts,
            "is_unibo_partner": is_partner,
            "partnership": partnership
        }
        
        if sim_score >= 0.70:
            group_1.append(company_data)
        else:
            group_2.append(company_data)
            
    group_1.sort(key=lambda x: x["rnd_intensity"], reverse=True)
    group_2.sort(key=lambda x: x["rnd_intensity"], reverse=True)
    return group_1, group_2

@app.route("/api/scout", methods=["POST"])
def scout():
    data = request.json
    if not data:
        return jsonify({"error": "No JSON payload provided"}), 400

    patent_id = data.get("Patent_ID")
    language = data.get("Language", "it") # 'it' o 'en'
    only_partners = data.get("only_partners", False)
    
    if not patent_id:
        return jsonify({"error": "Patent_ID is required"}), 400

    patent = _get_patent_by_id(patent_id)
    if not patent:
        return jsonify({"error": f"Patent with _id '{patent_id}' not found"}), 404
        
    if not db_connected:
        try:
            g1, g2 = _scout_companies_from_excel(patent, only_partners)
            return jsonify({
                "patent_title": patent.get("title", ""),
                "patent_url": patent.get("url", ""),
                "group_1": g1,
                "group_2": g2
            })
        except Exception as ex:
            return jsonify({"error": f"Fallback failed: {ex}"}), 500

    try:
        try:
            patent_vector = patent["embeddings"]["it"]["vector"]
            if not patent_vector:
                patent_vector = patent["embeddings"][language]["vector"]
        except KeyError:
            try:
                patent_vector = patent["embeddings"][language]["vector"]
            except KeyError:
                g1, g2 = _scout_companies_from_excel(patent, only_partners)
                return jsonify({
                    "patent_title": patent.get("title", ""),
                    "patent_url": patent.get("url", ""),
                    "group_1": g1,
                    "group_2": g2
                })

        if not patent_vector:
            g1, g2 = _scout_companies_from_excel(patent, only_partners)
            return jsonify({
                "patent_title": patent.get("title", ""),
                "patent_url": patent.get("url", ""),
                "group_1": g1,
                "group_2": g2
            })

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
        valid_industries = [ind for ind in industries_results if ind.get("code")]
        list_a_codes = [ind["code"] for ind in valid_industries[:10]]
        list_b_codes = [ind["code"] for ind in valid_industries[10:35]]
        all_nace_codes = list_a_codes + list_b_codes
        
        if not all_nace_codes:
            g1, g2 = _scout_companies_from_excel(patent, only_partners)
            return jsonify({"patent_title": patent.get("title", ""), "patent_url": patent.get("url", ""), "group_1": g1, "group_2": g2})

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
                    "numCandidates": 1500,
                    "limit": 800
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
        
        partners_map = _get_partners_tax_code_map()
        
        group_1 = []
        group_2 = []
        
        for comp in companies_results:
            try:
                nace_code = comp["industry_classification"]["nace_rev_2"]["code"]
            except KeyError:
                continue
                
            rnd_intensity = None
            if "metrics" in comp and "rnd_intensity" in comp["metrics"]:
                rnd_intensity = comp["metrics"]["rnd_intensity"]
                
            if rnd_intensity is None:
                try:
                    rnd_expenses = comp["financials"]["rnd_expenses_th_eur"]["last_available_year"]
                    revenues = comp["financials"]["revenues_th_eur"]
                    if revenues and revenues > 0:
                        rnd_intensity = rnd_expenses / revenues
                    else:
                        rnd_intensity = 0.0
                except (KeyError, TypeError, ZeroDivisionError):
                    rnd_intensity = 0.0
                    
            tax_code = comp.get("tax_code", "")
            clean_tc = str(tax_code).strip().lstrip('0')
            is_partner = clean_tc in partners_map
            if only_partners and not is_partner:
                continue
                
            partnership = None
            if is_partner:
                partnership = partners_map[clean_tc]
                
            company_data = {
                "company_name": comp.get("company_name", "N/A"),
                "tax_code": tax_code,
                "cciaa_number": comp.get("cciaa_number", "N/A"),
                "location": comp.get("location", {}),
                "location_province": comp.get("location", {}).get("province", "N/A"),
                "industry_classification": comp.get("industry_classification", {}),
                "business_profile": comp.get("business_profile", {}),
                "financials": comp.get("financials", {}),
                "metrics": comp.get("metrics", {}),
                "similarity_desc": round(comp.get("similarity_desc", 0), 4),
                "rnd_intensity": round(rnd_intensity, 6) if rnd_intensity is not None else 0.0,
                "contacts": comp.get("contacts", {}),
                "is_unibo_partner": is_partner,
                "partnership": partnership
            }
            
            sim_score = comp.get("similarity_desc", 0)
            
            if sim_score >= 0.75:
                group_1.append(company_data)
            elif nace_code in list_a_codes and sim_score >= 0.70:
                group_2.append(company_data)
            elif nace_code in list_b_codes and sim_score >= 0.65:
                group_2.append(company_data)
                
        if not group_1 and not group_2:
            g1, g2 = _scout_companies_from_excel(patent, only_partners)
            return jsonify({
                "patent_title": patent.get("title", ""),
                "patent_url": patent.get("url", ""),
                "group_1": g1,
                "group_2": g2
            })
            
        group_1.sort(key=lambda x: x["rnd_intensity"], reverse=True)
        group_2.sort(key=lambda x: x["rnd_intensity"], reverse=True)
        
        return jsonify({
            "patent_title": patent.get("title", "N/A"),
            "patent_url": patent.get("url", ""),
            "group_1": group_1,
            "group_2": group_2
        })
    except Exception as db_err:
        app.logger.warning(f"Database scouting failed: {db_err}. Falling back to Excel...")
        try:
            g1, g2 = _scout_companies_from_excel(patent, only_partners)
            return jsonify({
                "patent_title": patent.get("title", ""),
                "patent_url": patent.get("url", ""),
                "group_1": g1,
                "group_2": g2
            })
        except Exception as ex:
            return jsonify({"error": "Search failed"}), 500

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

def _get_all_patents_from_excel():
    try:
        import pandas as pd
        import glob
        excel_path = "data/archive/patents/brevetti_unibo (1).xlsx"
        if not os.path.exists(excel_path):
            xlsx_files = glob.glob("data/**/patents/*.xlsx", recursive=True) + glob.glob("*.xlsx")
            if xlsx_files:
                excel_path = xlsx_files[0]
        
        if os.path.exists(excel_path):
            df = pd.read_excel(excel_path, sheet_name="Brevetti")
            
            col_mapping = {}
            for col in df.columns:
                norm = str(col).lower().replace(" ", "").replace("_", "")
                col_mapping[norm] = col
            
            scheda_col = col_mapping.get("schedaid") or col_mapping.get("idscheda")
            title_col = col_mapping.get("titolo") or col_mapping.get("title")
            app_col = col_mapping.get("applicazioni") or col_mapping.get("applications")
            url_col = col_mapping.get("url") or col_mapping.get("link")
            
            patents_list = []
            for _, row in df.iterrows():
                s_id = str(row[scheda_col]).strip() if scheda_col and pd.notna(row[scheda_col]) else ""
                if not s_id:
                    continue
                if s_id.endswith(".0"):
                    s_id = s_id[:-2]
                
                title_val = str(row[title_col]).strip() if title_col and pd.notna(row[title_col]) else ""
                url_val = str(row[url_col]).strip() if url_col and pd.notna(row[url_col]) else ""
                
                apps_val = []
                if app_col and pd.notna(row[app_col]):
                    apps_val = [x.strip() for x in str(row[app_col]).split(",") if x.strip()]
                
                patents_list.append({
                    "scheda_id": s_id,
                    "title": title_val,
                    "applications": apps_val,
                    "url": url_val
                })
            
            response = jsonify(patents_list)
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response, 200
        else:
            return jsonify({"error": f"Local Excel not found at {excel_path}"}), 500
    except Exception as ex:
        return jsonify({"error": f"Fallback error: {ex}"}), 500

@app.route("/api/v1/patents", methods=["GET"])
def get_all_patents():
    if not db_connected:
        app.logger.warning("Database not connected. Using immediate local Excel fallback...")
        return _get_all_patents_from_excel()
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
        app.logger.warning(f"Database error in get_all_patents: {e}. Falling back to local Excel file...")
        return _get_all_patents_from_excel()

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

def _local_get_company_by_tax_code(tax_code):
    try:
        import pandas as pd
        aida_path = "Aida_FILE_COMPLETO.xlsx"
        if not os.path.exists(aida_path):
            return None
        
        df = pd.read_excel(aida_path, sheet_name="Results")
        for idx, row in df.iterrows():
            curr_tax = str(row.get("Tax code number")).strip() if pd.notna(row.get("Tax code number")) else ""
            if curr_tax.endswith(".0"):
                curr_tax = curr_tax[:-2]
            
            c_name = str(row.get("Company name")).strip() if pd.notna(row.get("Company name")) else ""
            
            if curr_tax == tax_code or c_name == tax_code:
                nace_code = str(row.get("NACE Rev. 2")).strip() if pd.notna(row.get("NACE Rev. 2")) else "N/A"
                nace_desc = str(row.get("NACE Rev. 2 description")).strip() if pd.notna(row.get("NACE Rev. 2 description")) else "N/A"
                
                return {
                    "_id": f"company:{curr_tax}",
                    "tax_code": curr_tax,
                    "company_name": c_name,
                    "industry_classification": {
                        "nace_rev_2": {
                            "code": nace_code,
                            "description": nace_desc
                        }
                    }
                }
    except Exception as ex:
        print(f"Error in _local_get_company_by_tax_code: {ex}")
    return None

@app.route("/api/v1/companies/<company_id>/gatekeepers", methods=["GET"])
def get_company_gatekeepers(company_id):
    try:
        # Trova l'azienda nel database (se connesso)
        company = None
        if db_connected:
            company = db.companies.find_one({"$or": [{"_id": company_id}, {"tax_code": company_id}]})
            
        # Fallback Excel per l'azienda se non connesso o non trovata
        if not company:
            company = _local_get_company_by_tax_code(company_id)
            
        if not company:
            return jsonify({"error": f"Company with identifier '{company_id}' not found."}), 404
            
        company_name = company.get("company_name", "N/A")
        comp_db_id = company.get("_id") or f"company:{company.get('tax_code')}"
        
        gatekeepers = []
        
        # 1. Cerca alumni reali associati a questa azienda
        real_alumni = []
        if db_connected:
            try:
                real_alumni = list(db.alumni.find({"company_id": comp_db_id}))
            except Exception as ex_db:
                app.logger.error(f"Error fetching real alumni from DB: {ex_db}")
        else:
            # Fallback Excel: leggi alumni da alumni_unibo.xlsx
            try:
                import pandas as pd
                excel_path = "alumni_unibo.xlsx"
                if os.path.exists(excel_path):
                    df = pd.read_excel(excel_path)
                    # Cerca per Lavoro 1 - Azienda
                    # Usiamo lo stesso criterio di pulizia dell'azienda
                    company_raw_to_match = company_name.lower().replace("s.r.l.", "").replace("srl", "").replace("s.p.a.", "").replace("spa", "").replace(" ", "").strip()
                    for idx, row in df.iterrows():
                        co = str(row.get("Lavoro 1 - Azienda")).strip() if pd.notna(row.get("Lavoro 1 - Azienda")) else ""
                        if co:
                            clean_co = co.lower().replace("s.r.l.", "").replace("srl", "").replace("s.p.a.", "").replace("spa", "").replace(" ", "").strip()
                            if clean_co == company_raw_to_match:
                                first = str(row.get("Nome")).strip() if pd.notna(row.get("Nome")) else ""
                                last = str(row.get("Cognome")).strip() if pd.notna(row.get("Cognome")) else ""
                                id_val = int(row.get("ID")) if pd.notna(row.get("ID")) else idx
                                email = str(row.get("Email")).strip() if pd.notna(row.get("Email")) else ""
                                photo = str(row.get("Foto URL")).strip() if pd.notna(row.get("Foto URL")) else "https://dx5i3n065oxey.cloudfront.net/global/user-icon.svg"
                                w_help = str(row.get("Willing to Help")).strip().lower() == "sì"
                                badges = str(row.get("Badges")).strip() if pd.notna(row.get("Badges")) else ""
                                status_val = int(row.get("Stato")) if pd.notna(row.get("Stato")) else 0
                                
                                degrees = []
                                for i in (1, 2, 3):
                                    t = str(row.get(f"Studio {i} - Tipo")).strip() if pd.notna(row.get(f"Studio {i} - Tipo")) else ""
                                    c = str(row.get(f"Studio {i} - Corso")).strip() if pd.notna(row.get(f"Studio {i} - Corso")) else ""
                                    d = str(row.get(f"Studio {i} - Dipartimento")).strip() if pd.notna(row.get(f"Studio {i} - Dipartimento")) else ""
                                    y = str(row.get(f"Studio {i} - Anno")).strip() if pd.notna(row.get(f"Studio {i} - Anno")) else ""
                                    s = str(row.get(f"Studio {i} - Sede")).strip() if pd.notna(row.get(f"Studio {i} - Sede")) else ""
                                    if t or c:
                                        degrees.append({
                                            "type": t,
                                            "course": c,
                                            "department": d,
                                            "year": y,
                                            "city": s
                                        })
                                        
                                jobs = []
                                for i in (1, 2, 3):
                                    ja = str(row.get(f"Lavoro {i} - Azienda")).strip() if pd.notna(row.get(f"Lavoro {i} - Azienda")) else ""
                                    jr = str(row.get(f"Lavoro {i} - Ruolo")).strip() if pd.notna(row.get(f"Lavoro {i} - Ruolo")) else ""
                                    if ja or jr:
                                        jobs.append({
                                            "company": ja,
                                            "role": jr
                                        })
                                        
                                real_alumni.append({
                                    "_id": id_val,
                                    "first_name": first,
                                    "last_name": last,
                                    "email": email if email else None,
                                    "photo_url": photo,
                                    "willing_to_help": w_help,
                                    "badges": badges,
                                    "status": status_val,
                                    "degrees": degrees,
                                    "jobs": jobs,
                                    "company_id": comp_db_id,
                                    "company_name_matched": company_name,
                                    "company_raw": co
                                })
            except Exception as ex_excel:
                app.logger.error(f"Error reading alumni from Excel fallback: {ex_excel}")
                
        # Aggiungi gli alumni reali come gatekeeper primari
        for al in real_alumni:
            first_name = al.get("first_name", "")
            last_name = al.get("last_name", "")
            
            # Recupera il primo lavoro o usa ruolo di default
            role_str = "Alumnus"
            if al.get("jobs"):
                role_str = al["jobs"][0].get("role", "Alumnus")
                
            name_role = f"{first_name} {last_name} - {role_str} presso {company_name}"
            
            # Recupera il titolo di studio principale
            degree_str = ""
            if al.get("degrees"):
                d = al["degrees"][0]
                degree_str = f"{d.get('type', '')} in {d.get('course', '')}"
                
            linkedin_url = f"https://www.linkedin.com/search/results/people/?keywords={first_name}%20{last_name}%20{company_name}"
            
            snippet_parts = []
            if degree_str:
                snippet_parts.append(f"Titolo: {degree_str}")
            if al.get("badges"):
                snippet_parts.append(f"Badges: {al.get('badges')}")
            snippet = " | ".join(snippet_parts)
            
            # Serializza l'alumnus per inviarlo al client
            al_serialized = dict(al)
            al_serialized["id"] = int(al_serialized.get("_id") or al_serialized.get("id"))
            if "_id" in al_serialized:
                del al_serialized["_id"]
            if "created_at" in al_serialized and hasattr(al_serialized["created_at"], "isoformat"):
                al_serialized["created_at"] = al_serialized["created_at"].isoformat()
            if "updated_at" in al_serialized and hasattr(al_serialized["updated_at"], "isoformat"):
                al_serialized["updated_at"] = al_serialized["updated_at"].isoformat()
                
            gatekeepers.append({
                "name_role": name_role,
                "degree": degree_str,
                "url": linkedin_url,
                "snippet": snippet,
                "source": "Alumni Database (Real)",
                "alumnus": al_serialized
            })
            
        # 2. Se le credenziali di Google Custom Search sono presenti, facciamo la ricerca
        google_api_key = os.getenv("GOOGLE_SEARCH_API_KEY")
        google_cx = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
        
        google_gatekeepers = []
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
                    for item in items:
                        title = item.get("title", "")
                        title_clean = title.split(" | ")[0] if " | " in title else title
                        title_clean = title_clean.split(" - LinkedIn")[0] if " - LinkedIn" in title_clean else title_clean
                        
                        google_gatekeepers.append({
                            "name_role": title_clean,
                            "url": item.get("link", "#"),
                            "snippet": item.get("snippet", ""),
                            "source": "Google Search (Real)"
                        })
            except Exception as e:
                app.logger.error(f"Google Search API error: {e}")
                
        gatekeepers.extend(google_gatekeepers)
        
        # 3. Se non abbiamo trovato nulla (né alumni né google), usiamo i mock
        if not gatekeepers:
            gatekeepers = get_mock_gatekeepers(company_name)
            
        return jsonify({
            "company_name": company_name,
            "gatekeepers": gatekeepers,
            "is_mock": len(real_alumni) == 0 and len(google_gatekeepers) == 0
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error in get_company_gatekeepers: {e}")
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

def _get_company_by_tax_code_from_excel(tax_code):
    try:
        import pandas as pd
        excel_path = "Aida_FILE_COMPLETO.xlsx"
        if not os.path.exists(excel_path):
            return None
        df = pd.read_excel(excel_path, sheet_name="Results")
        col_map = {str(c).lower().replace(" ", "").replace("_", "").replace("\n", ""): c for c in df.columns}
        
        comp_name_col = col_map.get("companyname")
        prov_col = col_map.get("province")
        region_col = col_map.get("registeredofficeaddress-region")
        tax_col = col_map.get("taxcodenumber")
        cciaa_col = col_map.get("cciaanumber")
        nace_col = col_map.get("nacerev.2")
        nace_desc_col = col_map.get("nacerev.2description")
        ateco_col = col_map.get("ateco2007code")
        ateco_desc_col = col_map.get("ateco2007description")
        desc_it_col = col_map.get("tradedescription(it)")
        desc_en_col = col_map.get("tradedescription(gb)")
        
        rev_col = col_map.get("revenuesfromsalesandservicestheurlastavail.yr")
        emp_col = col_map.get("numberofemployeeslastavail.yr")
        rnd_col = col_map.get("researchanddev.exp.theurlastavail.yr")
        web_col = col_map.get("website")
        tel_col = col_map.get("telephonenumber")
        
        if tax_col:
            df[tax_col] = df[tax_col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
            target = str(tax_code).strip().lstrip('0')
            df_clean = df[tax_col].str.lstrip('0')
            row_matches = df[df_clean == target]
            if not row_matches.empty:
                row = row_matches.iloc[0]
                
                comp_name = str(row[comp_name_col]).strip() if comp_name_col and pd.notna(row[comp_name_col]) else "N/A"
                cciaa = str(row[cciaa_col]).strip() if cciaa_col and pd.notna(row[cciaa_col]) else "N/A"
                if cciaa.endswith(".0"):
                    cciaa = cciaa[:-2]
                    
                province = str(row[prov_col]).strip() if prov_col and pd.notna(row[prov_col]) else "N/A"
                region = str(row[region_col]).strip() if region_col and pd.notna(row[region_col]) else "N/A"
                
                nace_code = str(row[nace_col]).strip() if nace_col and pd.notna(row[nace_col]) else "N/A"
                if nace_code.endswith(".0"):
                    nace_code = nace_code[:-2]
                    
                nace_desc = str(row[nace_desc_col]).strip() if nace_desc_col and pd.notna(row[nace_desc_col]) else "N/A"
                
                ateco_code = str(row[ateco_col]).strip() if ateco_col and pd.notna(row[ateco_col]) else "N/A"
                if ateco_code.endswith(".0"):
                    ateco_code = ateco_code[:-2]
                    
                ateco_desc = str(row[ateco_desc_col]).strip() if ateco_desc_col and pd.notna(row[ateco_desc_col]) else "N/A"
                
                desc_it = str(row[desc_it_col]).strip() if desc_it_col and pd.notna(row[desc_it_col]) else "N/A"
                desc_en = str(row[desc_en_col]).strip() if desc_en_col and pd.notna(row[desc_en_col]) else "N/A"
                
                try:
                    revenues = float(row[rev_col]) if rev_col and pd.notna(row[rev_col]) else 0.0
                except ValueError:
                    revenues = 0.0
                    
                try:
                    employees = int(row[emp_col]) if emp_col and pd.notna(row[emp_col]) else 0
                except ValueError:
                    employees = 0
                    
                rnd_val = row[rnd_col] if rnd_col and pd.notna(row[rnd_col]) else 0.0
                if rnd_val == "n.a." or rnd_val == "N/A" or pd.isna(rnd_val):
                    rnd_val = 0.0
                else:
                    try:
                        rnd_val = float(rnd_val)
                    except ValueError:
                        rnd_val = 0.0
                        
                rnd_intensity = rnd_val / revenues if revenues > 0 else 0.0
                
                location = {
                    "province": province,
                    "region": region,
                    "country": "Italy"
                }
                
                web = str(row[web_col]).strip() if web_col and pd.notna(row[web_col]) else ""
                tel = str(row[tel_col]).strip() if tel_col and pd.notna(row[tel_col]) else ""
                if tel.endswith(".0"):
                    tel = tel[:-2]
                    
                contacts = {
                    "website": web,
                    "phone": tel,
                    "email": f"info@{comp_name.lower().replace(' ', '').replace('.', '').replace(',', '')}.it" if web else ""
                }
                
                return {
                    "company_name": comp_name,
                    "tax_code": tax_code,
                    "cciaa_number": cciaa,
                    "location": location,
                    "location_province": province,
                    "industry_classification": {
                        "nace_rev_2": {"code": nace_code, "description": nace_desc},
                        "ateco_2007": {"code": ateco_code, "description": ateco_desc}
                    },
                    "business_profile": {
                        "trade_description_it": desc_it,
                        "trade_description_gb": desc_en
                    },
                    "financials": {
                        "revenues_th_eur": revenues,
                        "employees": employees,
                        "rnd_expenses_th_eur": {"last_available_year": rnd_val}
                    },
                    "metrics": {
                        "rnd_intensity": rnd_intensity,
                        "technology_adoption_capacity_score": round(rnd_intensity * 100, 2)
                    },
                    "similarity_desc": 0.8,
                    "rnd_intensity": round(rnd_intensity, 6),
                    "contacts": contacts,
                    "is_unibo_partner": False,
                    "partnership": None
                }
    except Exception as e:
        app.logger.error(f"Error in fallback get_company_by_tax_code: {e}")
    return None
            
@app.route("/api/v1/companies/by-tax-code/<tax_code>", methods=["GET"])
def get_company_by_tax_code(tax_code):
    if not db_connected:
        comp = _get_company_by_tax_code_from_excel(tax_code)
        if comp:
            return jsonify(comp), 200
        return jsonify({"error": "Company not found in local Excel file"}), 404
    try:
        # Search by exact tax code, or normalized variations in MongoDB
        query_tax_code = str(tax_code).strip()
        possible_codes = [query_tax_code]
        if query_tax_code.isdigit():
            possible_codes.append(query_tax_code.zfill(11))
            possible_codes.append(query_tax_code.lstrip("0"))
        possible_codes = list(set(possible_codes))
        
        company = db.companies.find_one({"tax_code": {"$in": possible_codes}})
        if not company:
            comp = _get_company_by_tax_code_from_excel(tax_code)
            if comp:
                return jsonify(comp), 200
            return jsonify({"error": "Company not found"}), 404
            
        company["_id"] = str(company["_id"])
        company["tax_code"] = tax_code # Ensure returned tax_code matches exact query format
        if "partnership_id" in company:
            company["partnership_id"] = str(company["partnership_id"])
            
        rnd_intensity = None
        if "metrics" in company and "rnd_intensity" in company["metrics"]:
            rnd_intensity = company["metrics"]["rnd_intensity"]
        if rnd_intensity is None:
            try:
                rnd_expenses = company["financials"]["rnd_expenses_th_eur"]["last_available_year"]
                revenues = company["financials"]["revenues_th_eur"]
                if revenues and revenues > 0:
                    rnd_intensity = rnd_expenses / revenues
                else:
                    rnd_intensity = 0.0
            except (KeyError, TypeError, ZeroDivisionError):
                rnd_intensity = 0.0
                
        company["rnd_intensity"] = rnd_intensity or 0.0
            
        return jsonify(company), 200
    except Exception as e:
        comp = _get_company_by_tax_code_from_excel(tax_code)
        if comp:
            return jsonify(comp), 200
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

def _get_mock_partners():
    return [
        {
            "sector": "Digitale e Intelligenza Artificiale",
            "partners": [
                {
                    "id": "partner1",
                    "company_name": "ALMAWAVE S.P.A.",
                    "agreement_type": "Accordo quadro",
                    "macro_themes": ["Intelligenza Artificiale", "NLP", "Speech Recognition"],
                    "joint_labs": ["Alma AI Lab"],
                    "tax_code": "08765432109"
                }
            ]
        },
        {
            "sector": "Salute e Scienze della Vita",
            "partners": [
                {
                    "id": "partner2",
                    "company_name": "PHARMAITALIA S.R.L.",
                    "agreement_type": "Accordo quadro",
                    "macro_themes": ["Oncologia", "Farmaci biologici"],
                    "joint_labs": ["BiomedLab"],
                    "tax_code": "09876543210"
                }
            ]
        }
    ]

def _get_existing_tax_codes(target_codes=None):
    existing = set()
    if not target_codes:
        return existing
        
    # Costruiamo la lista di tutte le variazioni possibili per il confronto (con e senza zeri iniziali)
    possible_codes = []
    for tc in target_codes:
        if tc:
            tc_str = str(tc).strip()
            possible_codes.append(tc_str)
            if tc_str.isdigit():
                possible_codes.append(tc_str.zfill(11))
                possible_codes.append(tc_str.lstrip("0"))
    possible_codes = list(set(possible_codes))
    
    # 1. Carica i codici fiscali da MongoDB (solo quelli dei partner!)
    if db_connected:
        try:
            cursor = db.companies.find({"tax_code": {"$in": possible_codes}}, {"tax_code": 1})
            for doc in cursor:
                tc = doc.get("tax_code")
                if tc:
                    existing.add(str(tc).strip().lstrip('0'))
        except Exception as e:
            app.logger.error(f"Error checking DB tax codes for partners: {e}")
            
    # 2. Invece di caricare il file Excel (operazione da 14MB che consuma troppa RAM su Render portando a OOM / SIGKILL),
    # consideriamo presenti in AIDA tutti i partner commerciali che hanno un codice fiscale valido,
    # escludendo solo gli enti/associazioni notoriamente assenti da AIDA.
    NON_AIDA_TAX_CODES = {
        "97401730154",  # ASSORESTAURO (Associazione)
        "03028211204",  # Consorzio Ospedaliero Colibrì (Consorzio)
        "07361731007",  # Federunacoma (Associazione)
        "90022370404"   # Legacoop Romagna (Associazione)
    }
    
    for tc in target_codes:
        if tc:
            clean_tc = str(tc).strip().lstrip('0')
            if clean_tc not in NON_AIDA_TAX_CODES:
                existing.add(clean_tc)
                
    return existing

@app.route("/api/v1/partners", methods=["GET"])
def get_partners():
    if not db_connected:
        return jsonify(_get_mock_partners()), 200
    try:
        # Raggruppa i partner per settore
        pipeline = [
            {
                "$group": {
                    "_id": "$sector",
                    "partners": {
                        "$push": {
                            "id": {"$toString": "$_id"},
                            "company_name": "$company_name",
                            "agreement_type": "$agreement_type",
                            "macro_themes": "$macro_themes",
                            "joint_labs": "$joint_labs"
                        }
                    }
                }
            },
            {"$sort": {"_id": 1}}
        ]
        sectors = list(db.unibo_partners.aggregate(pipeline))
        
        # Collega i codici fiscali delle aziende partner associate tramite database
        matched_companies = list(db.companies.find({"is_unibo_partner": True}, {"tax_code": 1, "partnership_id": 1}))
        partnership_to_tax_code = {str(c["partnership_id"]): c["tax_code"] for c in matched_companies if "partnership_id" in c}
        
        # Dizionario di mappatura statica ad alte prestazioni per accoppiamento esatto nome -> codice fiscale
        NAME_TO_TAX_CODE_FALLBACK = {
            "CAMST": "0311310379",
            "Automobili Lamborghini S.p.A.": "03049840378",
            "DUCATI": "05113870967",
            "FEV": "02293411202",
            "HPE COXA": "02302301202",
            "MARELLI EUROPE S.p.A.": "08082910967",
            "ENI S.p.A.": "00905811006",
            "Gruppo Hera": "04245520376",
            "Rosetti Marino": "0082100397",
            "Snam": "13271390151",
            "Alfasigma": "03432221202",
            "Atos Italia S.p.A.": "13054170154",
            "Hewlett Packard Enterprise Italia": "09205560965",
            "STMicroelectronics": "00870460159",
            "COESIA": "03378511200",
            "I.M.A. SPA": "0307140376",
            "SACMI IMOLA S.C.": "0287010375",
            "SCM Group": "0126480409",
            "TECHNOGYM": "06250230965",
            "FONDAZIONE FASHION RESEARCH ITALY": "02402671206",
            "GRUPPO UNIPOL": "0818570012",
            "REKEEP": "02402671206",
            "ALSTOM FERROVIARIA": "05623040156",
            "Autostrade per l'Italia": "07543501001",
            "ASSORESTAURO": "97401730154",
            "CNA Associazione di Bologna": "02235980378",
            "Colibrì Consorzio Ospedaliero": "03028211204",
            "Federunacoma": "07361731007",
            "Legacoop Romagna": "90022370404"
        }
        
        # Compila la lista di tutti i codici fiscali dei partner per la ricerca ottimizzata
        partner_tax_codes = []
        for sector in sectors:
            for partner in sector["partners"]:
                partner_id = partner["id"]
                company_name = partner["company_name"]
                tax_code = partnership_to_tax_code.get(partner_id, None)
                if not tax_code:
                    tax_code = NAME_TO_TAX_CODE_FALLBACK.get(company_name, None)
                if tax_code:
                    partner_tax_codes.append(str(tax_code).strip())
                    
        existing_tax_codes = _get_existing_tax_codes(partner_tax_codes)
        
        formatted_sectors = []
        for sector in sectors:
            sector_name = sector["_id"] or "Generale"
            partners_list = []
            for partner in sector["partners"]:
                partner_id = partner["id"]
                company_name = partner["company_name"]
                
                # Primo tentativo: match da database tramite partnership_id
                tax_code = partnership_to_tax_code.get(partner_id, None)
                
                # Secondo tentativo: fallback statico ad alte prestazioni tramite nome
                if not tax_code:
                    tax_code = NAME_TO_TAX_CODE_FALLBACK.get(company_name, None)
                    
                partner["tax_code"] = tax_code
                
                # Verifica se i dati AIDA sono disponibili per questa azienda
                has_aida = False
                if tax_code:
                    clean_tc = str(tax_code).strip().lstrip('0')
                    has_aida = clean_tc in existing_tax_codes
                partner["has_aida_data"] = has_aida
                
                partners_list.append(partner)
                
            formatted_sectors.append({
                "sector": sector_name,
                "partners": partners_list
            })
            
        return jsonify(formatted_sectors), 200
    except Exception as e:
        app.logger.error(f"Error fetching partners: {e}")
        return jsonify(_get_mock_partners()), 200

_alumni_company_map = None

def _get_alumni_from_excel(page, per_page, search_query):
    global _alumni_company_map
    try:
        import pandas as pd
        import math
        excel_path = "alumni_unibo.xlsx"
        if not os.path.exists(excel_path):
            return None
            
        # Costruisce la mappa delle aziende Aida per il matching (una sola volta)
        if _alumni_company_map is None:
            _alumni_company_map = {}
            aida_path = "Aida_FILE_COMPLETO.xlsx"
            if os.path.exists(aida_path):
                try:
                    aida_df = pd.read_excel(aida_path, sheet_name="Results", usecols=["Company name", "Tax code number"])
                    for _, r in aida_df.iterrows():
                        c_name = str(r["Company name"]).strip() if pd.notna(r["Company name"]) else ""
                        tax = str(r["Tax code number"]).strip() if pd.notna(r["Tax code number"]) else ""
                        if tax.endswith(".0"):
                            tax = tax[:-2]
                        if c_name and tax:
                            clean_n = c_name.lower().replace("s.r.l.", "").replace("srl", "").replace("s.p.a.", "").replace("spa", "").replace(" ", "").strip()
                            _alumni_company_map[clean_n] = {"id": f"company:{tax}", "name": c_name}
                except Exception as ex_aida:
                    app.logger.warning(f"Could not build company map from AIDA excel: {ex_aida}")
                    
        df = pd.read_excel(excel_path)
        
        alumni_list = []
        for idx, row in df.iterrows():
            first = str(row["Nome"]).strip() if pd.notna(row["Nome"]) else ""
            last = str(row["Cognome"]).strip() if pd.notna(row["Cognome"]) else ""
            email = str(row["Email"]).strip() if pd.notna(row["Email"]) else ""
            id_val = int(row["ID"]) if pd.notna(row["ID"]) else idx
            photo = str(row["Foto URL"]).strip() if pd.notna(row["Foto URL"]) else "https://dx5i3n065oxey.cloudfront.net/global/user-icon.svg"
            w_help = str(row["Willing to Help"]).strip().lower() == "sì"
            status_val = int(row["Stato"]) if pd.notna(row["Stato"]) else 0
            
            degrees = []
            for i in (1, 2, 3):
                t = str(row[f"Studio {i} - Tipo"]).strip() if f"Studio {i} - Tipo" in row and pd.notna(row[f"Studio {i} - Tipo"]) else ""
                c = str(row[f"Studio {i} - Corso"]).strip() if f"Studio {i} - Corso" in row and pd.notna(row[f"Studio {i} - Corso"]) else ""
                d = str(row[f"Studio {i} - Dipartimento"]).strip() if f"Studio {i} - Dipartimento" in row and pd.notna(row[f"Studio {i} - Dipartimento"]) else ""
                y = str(row[f"Studio {i} - Anno"]).strip() if f"Studio {i} - Anno" in row and pd.notna(row[f"Studio {i} - Anno"]) else ""
                s = str(row[f"Studio {i} - Sede"]).strip() if f"Studio {i} - Sede" in row and pd.notna(row[f"Studio {i} - Sede"]) else ""
                if t or c:
                    degrees.append({
                        "type": t,
                        "course": c,
                        "department": d,
                        "year": y,
                        "city": s
                    })
            
            jobs = []
            for i in (1, 2, 3):
                a = str(row[f"Lavoro {i} - Azienda"]).strip() if f"Lavoro {i} - Azienda" in row and pd.notna(row[f"Lavoro {i} - Azienda"]) else ""
                r = str(row[f"Lavoro {i} - Ruolo"]).strip() if f"Lavoro {i} - Ruolo" in row and pd.notna(row[f"Lavoro {i} - Ruolo"]) else ""
                if a or r:
                    jobs.append({
                        "company": a,
                        "role": r
                    })
            
            comp_raw = jobs[0]["company"] if jobs else ""
            
            # Match company against AIDA
            company_id = None
            company_name_matched = None
            if comp_raw:
                clean_comp = comp_raw.lower().replace("s.r.l.", "").replace("srl", "").replace("s.p.a.", "").replace("spa", "").replace(" ", "").strip()
                match = _alumni_company_map.get(clean_comp)
                if match:
                    company_id = match["id"]
                    company_name_matched = match["name"]
            
            if search_query:
                q = search_query.lower()
                match_found = (
                    q in first.lower() or
                    q in last.lower() or
                    q in email.lower() or
                    q in comp_raw.lower() or
                    any(q in d["course"].lower() for d in degrees) or
                    any(q in j["role"].lower() or q in j["company"].lower() for j in jobs)
                )
                if not match_found:
                    continue
                    
            alumni_list.append({
                "id": id_val,
                "first_name": first,
                "last_name": last,
                "email": email if email else None,
                "willing_to_help": w_help,
                "photo_url": photo,
                "status": status_val,
                "company_raw": comp_raw if comp_raw else None,
                "company_id": company_id,
                "company_name_matched": company_name_matched,
                "degrees": degrees,
                "jobs": jobs,
                "badges": str(row["Badges"]).strip() if pd.notna(row["Badges"]) else ""
            })
            
        total_count = len(alumni_list)
        total_pages = math.ceil(total_count / per_page)
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_list = alumni_list[start_idx:end_idx]
        
        return {
            "alumni": paginated_list,
            "total_pages": total_pages,
            "total_count": total_count,
            "current_page": page
        }
    except Exception as ex:
        app.logger.error(f"Error in _get_alumni_from_excel: {ex}")
        return None

@app.route("/api/v1/alumni", methods=["GET"])
def get_alumni():
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    search_query = request.args.get("search", "").strip()
    
    if not db_connected:
        res = _get_alumni_from_excel(page, per_page, search_query)
        if res:
            return jsonify(res), 200
        return jsonify({"error": "Failed to read alumni from Excel"}), 500
        
    try:
        skip = (page - 1) * per_page
        query = {}
        if search_query:
            regex_val = {"$regex": search_query, "$options": "i"}
            query["$or"] = [
                {"first_name": regex_val},
                {"last_name": regex_val},
                {"email": regex_val},
                {"company_raw": regex_val},
                {"company_name_matched": regex_val},
                {"degrees.course": regex_val},
                {"jobs.role": regex_val}
            ]
            
        total_count = db.alumni.count_documents(query)
        cursor = db.alumni.find(query).skip(skip).limit(per_page)
        
        alumni_list = []
        for doc in cursor:
            doc["id"] = int(doc["_id"])
            del doc["_id"]
            if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
                doc["created_at"] = doc["created_at"].isoformat()
            if "updated_at" in doc and hasattr(doc["updated_at"], "isoformat"):
                doc["updated_at"] = doc["updated_at"].isoformat()
            alumni_list.append(doc)
            
        import math
        total_pages = math.ceil(total_count / per_page)
        
        return jsonify({
            "alumni": alumni_list,
            "total_pages": total_pages,
            "total_count": total_count,
            "current_page": page
        }), 200
    except Exception as e:
        app.logger.error(f"Error fetching alumni: {e}. Falling back to Excel...")
        res = _get_alumni_from_excel(page, per_page, search_query)
        if res:
            return jsonify(res), 200
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    app.run(debug=True, port=port)
