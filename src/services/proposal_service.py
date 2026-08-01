import os
import logging
from datetime import datetime
from typing import List
from pydantic import BaseModel, Field
from src.config import Settings, load_settings
from src.db import get_database

logger = logging.getLogger(__name__)

# --- PYDANTIC SCHEMAS FOR STRUCTURED OUTPUT ---

class WorkPackage(BaseModel):
    title: str = Field(description="Titolo del Work Package (es. WP1: Adattamento Prototipo)")
    description: str = Field(description="Descrizione dettagliata delle attività")
    duration_months: int = Field(description="Durata stimata in mesi")
    expected_deliverable: str = Field(description="Risultato tangibile e misurabile atteso")

class RiskMitigation(BaseModel):
    risk: str = Field(description="Rischio tecnico o commerciale identificato")
    mitigation: str = Field(description="Strategia concreta di mitigazione del rischio")

class ProjectProposalJSON(BaseModel):
    project_title: str = Field(description="Titolo accattivante e innovativo per il progetto congiunto")
    executive_summary: str = Field(description="Sintesi esecutiva della proposta di sinergia (max 150 parole)")
    synergy_analysis: str = Field(description="Analisi dettagliata del perché il brevetto risolve un problema o potenzia il business specifico dell'azienda")
    current_trl: str = Field(description="TRL di partenza del brevetto")
    target_trl: str = Field(description="TRL obiettivo al termine del progetto")
    innovation_impact: str = Field(description="Impatto sull'innovazione e competitività aziendale")
    work_packages: List[WorkPackage] = Field(description="Piano di lavoro diviso in fasi o Work Packages")
    timeline_total_months: int = Field(description="Durata totale stimata del progetto in mesi")
    risks_and_mitigations: List[RiskMitigation] = Field(description="Principali rischi e relative mitigazioni")
    next_steps: List[str] = Field(description="Primi 3 step operativi immediati per avviare la collaborazione (es. NDA, incontro tecnico)")


# --- SERVICE LOGIC ---

def generate_proposal(
    company_id: str,
    patent_id: str,
    force_regenerate: bool = False,
    db = None,
    settings: Settings | None = None
) -> dict:
    """Generate or retrieve cached project proposal matching a company and a patent."""
    settings = settings or load_settings()
    if db is None:
        db = get_database(settings)

    cache_col = db["project_proposals"]

    # 1. Caching check
    if not force_regenerate:
        cached = cache_col.find_one({"company_id": company_id, "patent_id": patent_id})
        if cached and "proposal" in cached:
            logger.info("Retrieved proposal from MongoDB cache for company=%s, patent=%s", company_id, patent_id)
            return cached["proposal"]

    # 2. Retrieve company and patent documents
    company = db.companies.find_one({"$or": [{"_id": company_id}, {"tax_code": company_id}]})
    if not company:
        raise ValueError(f"Company with identifier '{company_id}' not found.")

    patent = db.patents.find_one({"$or": [{"_id": patent_id}, {"scheda_id": patent_id}]})
    if not patent:
        raise ValueError(f"Patent with identifier '{patent_id}' not found.")

    # 3. Extract relevant fields
    company_name = company.get("company_name", "N/A")
    company_desc_it = company.get("embeddings", {}).get("it", {}).get("text", "")
    company_desc_en = company.get("embeddings", {}).get("en", {}).get("text", "")
    company_desc = f"{company_desc_it} / {company_desc_en}".strip(" / ")
    
    nace_code = company.get("industry_classification", {}).get("nace_rev_2", {}).get("code", "N/A")
    nace_desc = company.get("industry_classification", {}).get("nace_rev_2", {}).get("description", "N/A")
    
    employees = company.get("metrics", {}).get("employees_count")
    if not employees:
        employees = company.get("business_profile", {}).get("employees", "N/A")

    rnd_intensity = company.get("metrics", {}).get("rnd_intensity")
    rnd_expenses = company.get("financials", {}).get("rnd_expenses_th_eur", {}).get("last_available_year")
    rd_metrics = f"R&D Intensity: {rnd_intensity}" if rnd_intensity else (f"R&D Expenses: {rnd_expenses} th EUR" if rnd_expenses else "N/A")

    patent_title = patent.get("title", "N/A")
    patent_desc = patent.get("full_description") or patent.get("short_description") or patent.get("abstract") or "N/A"
    patent_trl = patent.get("trl", "N/A")
    patent_kto = patent.get("kto", {}).get("name", "N/A")

    # 4. Formulate Prompts
    system_prompt = (
        "Sei un esperto senior di Open Innovation, Trasferimento Tecnologico e Grant Writing scientifico-industriale. "
        "Il tuo compito è analizzare il profilo di un'azienda e una scheda brevettuale universitaria (UNIBO) e progettare una proposta di collaborazione industriale realistica, ad alto valore aggiunto e tecnicamente rigorosa.\n"
        "Utilizza le tue elevate capacità di ragionamento per identificare la sinergia esatta tra le capacità operative/commerciali dell'azienda e l'innovazione portata dal brevetto. "
        "Restituisci RIGOROSAMENTE E SOLO il JSON strutturato secondo lo schema fornito."
    )

    user_prompt = f"""Analizza i seguenti dati:

PROFILO AZIENDA:
Nome: {company_name}
Settore/NACE: {nace_code} - {nace_desc}
Descrizione Business: {company_desc}
Metriche: Dipendenti: {employees}, R&D info: {rd_metrics}

SCHEDA BREVETTO UNIBO:
ID/Titolo: {patent_title}
Contenuto/Abstract: {patent_desc}
TRL Attuale: {patent_trl}
Dettagli KTO / Ambito: {patent_kto}

Genera una Proposta di Progetto di Trasferimento Tecnologico completa, strategica e pronta da presentare al management. Spiega esattamente come la tecnologia brevettata si integra nei processi o nei prodotti dell'azienda."""

    # 5. Invoke Google Gemini API via raw HTTPS request to avoid gRPC memory bloat
    api_key = settings.gemini_api_key
    if not api_key:
        api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured in .env file or environment.")

    logger.info("Calling raw Gemini API for joint proposal generation...")
    
    # Costruiamo il payload JSON secondo le specifiche delle API Google GenAI
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": f"SYSTEM_PROMPT:\n{system_prompt}\n\nUSER_PROMPT:\n{user_prompt}"}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "project_title": {"type": "STRING"},
                    "executive_summary": {"type": "STRING"},
                    "synergy_analysis": {"type": "STRING"},
                    "current_trl": {"type": "STRING"},
                    "target_trl": {"type": "STRING"},
                    "innovation_impact": {"type": "STRING"},
                    "work_packages": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "title": {"type": "STRING"},
                                "description": {"type": "STRING"},
                                "duration_months": {"type": "INTEGER"},
                                "expected_deliverable": {"type": "STRING"}
                            },
                            "required": ["title", "description", "duration_months", "expected_deliverable"]
                        }
                    },
                    "timeline_total_months": {"type": "INTEGER"},
                    "risks_and_mitigations": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "risk": {"type": "STRING"},
                                "mitigation": {"type": "STRING"}
                            },
                            "required": ["risk", "mitigation"]
                        }
                    },
                    "next_steps": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    }
                },
                "required": [
                    "project_title", "executive_summary", "synergy_analysis", "current_trl", 
                    "target_trl", "innovation_impact", "work_packages", "timeline_total_months", 
                    "risks_and_mitigations", "next_steps"
                ]
            },
            "temperature": 0.2
        }
    }
    
    import urllib.request
    import json
    
    model_name = settings.llm_model.strip()
    # Rimuoviamo eventuali prefissi duplicati models/
    if model_name.startswith("models/"):
        model_name = model_name[7:]
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    import time
    max_attempts = 3
    proposal_dict = None
    last_error = None
    
    for attempt in range(max_attempts):
        try:
            logger.info(f"Attempt {attempt + 1} of {max_attempts} to call Gemini API...")
            with urllib.request.urlopen(req, timeout=45) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                candidate = res_data["candidates"][0]
                text_response = candidate["content"]["parts"][0]["text"]
                proposal_dict = json.loads(text_response)
                logger.info("Successfully received and parsed proposal from Gemini.")
                break
        except Exception as api_err:
            last_error = api_err
            logger.warning(f"Gemini API attempt {attempt + 1} failed: {api_err}")
            if attempt < max_attempts - 1:
                # Aspetta prima di riprovare (1.5 secondi)
                time.sleep(1.5)
                
    if proposal_dict is None:
        logger.error(f"All {max_attempts} attempts failed calling raw Gemini API: {last_error}")
        raise RuntimeError(f"Error calling model '{settings.llm_model}': {last_error}")

    # 6. Save to cache
    cache_doc = {
        "company_id": company_id,
        "patent_id": patent_id,
        "proposal": proposal_dict,
        "created_at": datetime.utcnow().isoformat()
    }
    
    # Store MongoDB document representation
    cache_col.update_one(
        {"company_id": company_id, "patent_id": patent_id},
        {"$set": cache_doc},
        upsert=True
    )
    logger.info("Successfully generated and cached proposal for company=%s, patent=%s", company_id, patent_id)
    
    return proposal_dict
