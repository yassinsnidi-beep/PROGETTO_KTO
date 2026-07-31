import re
import urllib.request
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from src.db import get_database
from src.config import load_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

URL = "https://www.unibo.it/it/con-societa-e-impresa/imprese-e-non-profit/elenco-partnership-strategiche-industriali"

def clean_text(text: str) -> str:
    """Normalize whitespace and replace unicode quotation marks/non-breaking spaces."""
    if not text:
        return ""
    text = text.replace('\u2019', "'").replace('\u2018', "'") # curly apostrophes
    text = text.replace('\xa0', ' ') # non-breaking space
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def normalize_name(name: str) -> str:
    """Normalize company name for comparison by removing legal suffixes and punctuation."""
    name = name.lower()
    name = name.replace("'", " ").replace("\u2019", " ").replace("\u2018", " ")
    # Strip dots completely to merge abbreviations (e.g. S.P.A. -> SPA, CON.AMI -> CONAMI)
    name = name.replace(".", "")
    name = re.sub(r"[^\w\s]", " ", name)
    # Remove common Italian legal designators and fillers
    suffixes = [
        "spa", "srl", "sca", "sc", "cooperativa", "coop",
        "societa' per azioni", "societa per azioni", "società per azioni", 
        "gruppo", "group", "societa", "società", "italia", "italy", "europe"
    ]
    for s in suffixes:
        name = re.sub(rf"\b{s}\b", " ", name)
    # clean extra whitespace
    return " ".join(name.split())

def get_match_score(scraped_norm: str, db_norm: str) -> float:
    """Calculate token overlap score between two normalized names."""
    scraped_words = set(scraped_norm.split())
    db_words = set(db_norm.split())
    if not scraped_words or not db_words:
        return 0.0
    
    # Filter out single-character tokens to prevent false matches (like 's', 'p', 'a')
    scraped_words = {w for w in scraped_words if len(w) > 1}
    db_words = {w for w in db_words if len(w) > 1}
    if not scraped_words or not db_words:
        return 0.0
        
    intersection = scraped_words.intersection(db_words)
    if not intersection:
        return 0.0
        
    # Heuristic: Avoid matching on generic tokens alone
    generic_words = {
        "consorzio", "fondazione", "associazione", "servizi", "industria", 
        "group", "cooperativa", "coop", "aeroporto", "autostrade", "fashion",
        "cons", "ass"
    }
    if len(intersection) == 1 and list(intersection)[0] in generic_words:
        return 0.0
    
    # Check for direct inclusion (e.g. "hera" inside "hera comm")
    if scraped_words.issubset(db_words) or db_words.issubset(scraped_words):
        subset = scraped_words if scraped_words.issubset(db_words) else db_words
        if len(subset) == 1 and list(subset)[0] in generic_words:
            return 0.0
        return 1.0
        
    return len(intersection) / max(len(scraped_words), len(db_words))



def scrape_unibo_partnerships() -> list[dict]:
    """Fetch and parse partnerships from the UNIBO page."""
    logger.info("Fetching UNIBO partnerships from %s", URL)
    req = urllib.request.Request(
        URL, 
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read()
    except Exception as e:
        logger.error("Failed to fetch live URL: %s. Using cached local copy if available.", e)
        # Fallback local copy path (the step 79 cache file)
        cache_path = r"C:\Users\Abdou\.gemini\antigravity\brain\4e5adbb4-2d9a-4b3f-ab7c-784c9add0810\.system_generated\steps\79\content.md"
        import os
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                html = f.read()
        else:
            raise e

    soup = BeautifulSoup(html, "html.parser")
    main_content = soup.find(id="parent-fieldname-text")
    if not main_content:
        main_content = soup.find(class_="parent-fieldname-text")
    if not main_content:
        main_content = soup

    partnerships = []
    current_sector = "Generale"

    # Iterate through content nodes
    for child in main_content.descendants:
        if child.name == 'h3':
            classes = child.get("class", [])
            text = child.get_text(strip=True)
            
            # Check if it defines a sector
            if "aprichiudititle" in classes or text in [
                "Agro-alimentare", "Automotive", "Energia e Ambiente", 
                "Farmaceutica e Chimica", "ICT", "Macchine automatiche, Meccatronica e Meccanica di precisione", 
                "Moda, Benessere e Stili di Vita", "Servizi, Banche e Assicurazioni", 
                "Trasporti, Aeronautica e Aerospazio", "Accordi con associazioni e consorzi di imprese"
            ]:
                current_sector = clean_text(text)
            else:
                company_name = clean_text(text)
                if not company_name:
                    continue
                
                ul = child.find_next_sibling()
                steps = 0
                while ul and ul.name != 'ul' and steps < 5:
                    ul = ul.find_next_sibling()
                    steps += 1
                    
                agreement_type = "N/A"
                macro_themes = "N/A"
                joint_labs = []
                
                if ul and ul.name == 'ul':
                    lis = ul.find_all("li")
                    for li in lis:
                        li_text = li.get_text(strip=True)
                        if "Tipo di accordo:" in li_text:
                            agreement_type = clean_text(li_text.replace("Tipo di accordo:", ""))
                        elif "Macrotemi di collaborazione:" in li_text:
                            macro_themes = clean_text(li_text.replace("Macrotemi di collaborazione:", ""))
                        elif "Joint Lab" in li_text:
                            joint_labs.append(clean_text(li_text))
                
                # Check siblings for Joint Lab mentions
                sibling = child.find_next_sibling()
                steps = 0
                while sibling and sibling.name != 'h3' and steps < 10:
                    if sibling.name in ['p', 'div']:
                        sib_text = sibling.get_text(strip=True)
                        if "Joint Lab" in sib_text:
                            joint_labs.append(clean_text(sib_text))
                    sibling = sibling.find_next_sibling()
                    steps += 1
                
                unique_labs = []
                for lab in joint_labs:
                    if lab not in unique_labs:
                        unique_labs.append(lab)
                        
                partnerships.append({
                    "company_name": company_name,
                    "sector": current_sector,
                    "agreement_type": agreement_type,
                    "macro_themes": macro_themes,
                    "joint_labs": unique_labs
                })

    return partnerships

def main():
    settings = load_settings()
    db = get_database(settings)
    
    # 1. Scrape partnerships
    scraped_data = scrape_unibo_partnerships()
    logger.info("Scraped %d partnerships successfully.", len(scraped_data))
    
    # 2. Ingest into 'unibo_partners' collection
    partners_col = db["unibo_partners"]
    partners_col.delete_many({}) # Refresh the collection
    
    now = datetime.utcnow()
    docs_to_insert = []
    for partner in scraped_data:
        partner["created_at"] = now
        docs_to_insert.append(partner)
        
    if docs_to_insert:
        partners_col.insert_many(docs_to_insert)
        logger.info("Inserted %d documents into 'unibo_partners' collection.", len(docs_to_insert))

    # 3. Reconcile / Match with 'companies' collection
    logger.info("Loading companies from database for matching...")
    db_companies = list(db.companies.find({}, {"_id": 1, "company_name": 1}))
    logger.info("Loaded %d companies from database.", len(db_companies))
    
    # Reset existing flags in companies collection
    db.companies.update_many(
        {"is_unibo_partner": True},
        {"$unset": {"is_unibo_partner": "", "partnership_id": ""}}
    )
    
    # Normalize DB names in memory
    normalized_db = []
    for company in db_companies:
        norm_name = normalize_name(company.get("company_name", ""))
        if norm_name:
            normalized_db.append((company["_id"], company["company_name"], norm_name))
            
    matches_count = 0
    
    for partner_doc in partners_col.find():
        scraped_name = partner_doc["company_name"]
        scraped_norm = normalize_name(scraped_name)
        if not scraped_norm:
            continue
            
        best_match_id = None
        best_match_name = None
        best_score = 0.0
        
        for db_id, db_name, db_norm in normalized_db:
            score = get_match_score(scraped_norm, db_norm)
            if score > best_score:
                best_score = score
                best_match_id = db_id
                best_match_name = db_name
                if score == 1.0: # Early exit for exact normalized matches
                    break
                    
        # If match exceeds threshold, link them
        if best_score >= 0.8:
            db.companies.update_one(
                {"_id": best_match_id},
                {"$set": {
                    "is_unibo_partner": True,
                    "partnership_id": partner_doc["_id"]
                }}
            )
            logger.info("Match Found: Scraped '%s' -> DB '%s' (Score: %.2f)", scraped_name, best_match_name, best_score)
            matches_count += 1
        else:
            logger.warning("No high-score match for: '%s' (Best score: %.2f for '%s')", scraped_name, best_score, best_match_name)
            
    logger.info("Finished Ingestion. Linked %d companies as UNIBO partners.", matches_count)

if __name__ == "__main__":
    main()
