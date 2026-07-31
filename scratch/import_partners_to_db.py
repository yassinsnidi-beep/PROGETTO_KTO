import os
import certifi
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# Carica configurazioni dal file .env
load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "patent_matching")

if not MONGODB_URI:
    print("Errore: MONGODB_URI non trovata nel file .env!")
    exit(1)

print("Connessione a MongoDB Atlas in corso...")
client = MongoClient(MONGODB_URI, tlsCAFile=certifi.where())
db = client[MONGODB_DB_NAME]

# Lista dei codici fiscali delle aziende partner strategici
PARTNER_TAX_CODES = [
    "0311310379",  # CAMST
    "03049840378",  # Automobili Lamborghini S.p.A.
    "05113870967",  # DUCATI
    "02293411202",  # FEV
    "02302301202",  # HPE COXA
    "08082910967",  # MARELLI EUROPE S.p.A.
    "00905811006",  # ENI S.p.A.
    "04245520376",  # Gruppo Hera
    "0082100397",   # Rosetti Marino
    "13271390151",  # Snam
    "03432221202",  # Alfasigma
    "13054170154",  # Atos Italia S.p.A.
    "09205560965",  # Hewlett Packard Enterprise Italia
    "00870460159",  # STMicroelectronics
    "03378511200",  # COESIA
    "0307140376",   # I.M.A. SPA
    "0287010375",   # SACMI IMOLA S.C.
    "0126480409",   # SCM Group
    "06250230965",  # TECHNOGYM
    "02402671206",  # FONDAZIONE FASHION RESEARCH ITALY / REKEEP
    "0818570012",   # GRUPPO UNIPOL
    "05623040156",  # ALSTOM FERROVIARIA
    "07543501001"   # Autostrade per l'Italia
]

excel_path = "Aida_FILE_COMPLETO.xlsx"
if not os.path.exists(excel_path):
    print(f"Errore: Il file {excel_path} non esiste nella cartella del progetto!")
    exit(1)

print("Lettura del file Excel AIDA in corso (potrebbe richiedere qualche secondo)...")
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

inserted_count = 0
updated_count = 0

print("Elaborazione e importazione dei profili AIDA nel database online...")
# Pulisce i target per il matching
clean_targets = {tc.strip().lstrip('0') for tc in PARTNER_TAX_CODES}

for idx, row in df.iterrows():
    tax_code_raw = str(row[tax_col]).strip() if tax_col and pd.notna(row[tax_col]) else ""
    if tax_code_raw.endswith(".0"):
        tax_code_raw = tax_code_raw[:-2]
        
    clean_tc = tax_code_raw.lstrip('0')
    if clean_tc in clean_targets:
        # Trovato match per un partner strategico! Estraiamo il profilo AIDA
        comp_name = str(row[comp_name_col]).strip() if comp_name_col and pd.notna(row[comp_name_col]) else "N/A"
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
        
        web = str(row[web_col]).strip() if web_col and pd.notna(row[web_col]) else ""
        tel = str(row[tel_col]).strip() if tel_col and pd.notna(row[tel_col]) else ""
        if tel.endswith(".0"):
            tel = tel[:-2]
            
        contacts = {
            "website": web,
            "phone": tel,
            "email": f"info@{comp_name.lower().replace(' ', '').replace('.', '').replace(',', '')}.it" if web else ""
        }
        
        # Struttura del documento compatibile con companies in MongoDB
        company_doc = {
            "company_name": comp_name,
            "tax_code": tax_code_raw,
            "cciaa_number": cciaa,
            "location": {
                "province": province,
                "region": region,
                "country": "Italy"
            },
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
            "contacts": contacts,
            "is_unibo_partner": True
        }
        
        # Verifica se l'azienda esiste già nella collezione companies di MongoDB
        existing_doc = db.companies.find_one({"tax_code": {"$in": [tax_code_raw, tax_code_raw.zfill(11), clean_tc]}})
        if existing_doc:
            # Aggiorna il profilo finanziario e imposta is_unibo_partner su True
            db.companies.update_one(
                {"_id": existing_doc["_id"]},
                {"$set": {
                    "financials": company_doc["financials"],
                    "metrics": company_doc["metrics"],
                    "business_profile": company_doc["business_profile"],
                    "industry_classification": company_doc["industry_classification"],
                    "contacts": company_doc["contacts"],
                    "is_unibo_partner": True
                }}
            )
            updated_count += 1
        else:
            # Inserisce un nuovo profilo aziendale
            db.companies.insert_one(company_doc)
            inserted_count += 1

print("\n--- IMPORTAZIONE COMPLETATA CON SUCCESSO! ---")
print(f"Profili aggiornati nel database: {updated_count}")
print(f"Nuovi profili inseriti nel database: {inserted_count}")
print("Ora puoi consultare le schede AIDA di queste aziende online in tempo reale!")
