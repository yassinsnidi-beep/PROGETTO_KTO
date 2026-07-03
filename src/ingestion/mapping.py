"""Column and geographic mappings."""

from __future__ import annotations

import logging
from typing import Any

from src.utils import normalize_column_name

logger = logging.getLogger(__name__)

COMPANY_COLUMN_ALIASES: dict[str, list[str]] = {
    "company_name": ["company name"],
    "province": ["province", "provincia"],
    "accounting_closing_date": ["accounting closing date"],
    "revenues_th_eur": ["revenues from sales and services th eur last avail yr"],
    "employees": ["number of employees last avail yr"],
    "tax_code": ["tax code number"],
    "cciaa_number": ["cciaa number"],
    "rnd_last_year_th_eur": ["research and dev exp th eur last avail yr"],
    "rnd_year_minus_1_th_eur": ["research and dev exp th eur year 1"],
    "rnd_year_minus_2_th_eur": ["research and dev exp th eur year 2"],
    "rnd_year_minus_3_th_eur": ["research and dev exp th eur year 3"],
    "nace_code": ["nace rev 2"],
    "nace_description": ["nace rev 2 description"],
    "ateco_2007_code": ["ateco 2007 code"],
    "ateco_2007_description": ["ateco 2007 description"],
    "ateco_2002_code": ["ateco 2002 code"],
    "ateco_2002_description": ["ateco 2002 description"],
    "trade_description_it": ["trade description it"],
    "trade_description_gb": ["trade description gb"],
}

PATENT_COLUMN_ALIASES: dict[str, list[str]] = {
    "scheda_id": ["scheda id", "id scheda"],
    "title": ["titolo", "title"],
    "subtitle": ["sottotitolo", "subtitle"],
    "url": ["url", "link"],
    "abstract": ["abstract"],
    "short_description": ["descrizione breve", "short description"],
    "full_description": ["descrizione completa", "full description"],
    "advantages": ["vantaggi", "advantages"],
    "applications": ["applicazioni", "applications"],
    "development_stage": ["stadio sviluppo", "development stage"],
    "protection_type": ["tipo protezione", "protection type"],
    "patent_status": ["stato brevetto", "patent status"],
    "patent_number": ["numero brevetto", "patent number"],
    "application_number": ["numero domanda", "application number"],
    "kto_contact_name": ["kto contatto nome", "kto contact name"],
    "kto_contact_email": ["kto contatto email", "kto contact email"],
    "kto_contact_phone": ["kto contatto telefono", "kto contact phone"],
}


def rename_columns(records: list[dict[str, Any]], aliases: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Rename source dictionaries to internal names using normalized aliases."""
    normalized_aliases = {
        field: {normalize_column_name(alias) for alias in field_aliases}
        for field, field_aliases in aliases.items()
    }
    output: list[dict[str, Any]] = []
    for record in records:
        normalized_record = {normalize_column_name(key): value for key, value in record.items()}
        row: dict[str, Any] = {}
        for field, candidates in normalized_aliases.items():
            matched = next((candidate for candidate in candidates if candidate in normalized_record), None)
            if matched is None:
                logger.warning("Missing expected column for field %s", field)
                row[field] = None
            else:
                row[field] = normalized_record.get(matched)
        output.append(row)
    return output


PROVINCE_TO_REGION: dict[str, str] = {
    "ag": "Sicilia", "agrigento": "Sicilia", "al": "Piemonte", "alessandria": "Piemonte",
    "an": "Marche", "ancona": "Marche", "ao": "Valle d'Aosta", "aosta": "Valle d'Aosta",
    "ap": "Marche", "ascoli piceno": "Marche", "aq": "Abruzzo", "laquila": "Abruzzo", "l aquila": "Abruzzo",
    "ar": "Toscana", "arezzo": "Toscana", "at": "Piemonte", "asti": "Piemonte",
    "av": "Campania", "avellino": "Campania", "ba": "Puglia", "bari": "Puglia",
    "bg": "Lombardia", "bergamo": "Lombardia", "bi": "Piemonte", "biella": "Piemonte",
    "bl": "Veneto", "belluno": "Veneto", "bn": "Campania", "benevento": "Campania",
    "bo": "Emilia-Romagna", "bologna": "Emilia-Romagna", "br": "Puglia", "brindisi": "Puglia",
    "bs": "Lombardia", "brescia": "Lombardia", "bt": "Puglia", "barletta andria trani": "Puglia",
    "bz": "Trentino-Alto Adige", "bolzano": "Trentino-Alto Adige", "ca": "Sardegna", "cagliari": "Sardegna",
    "cb": "Molise", "campobasso": "Molise", "ce": "Campania", "caserta": "Campania",
    "ch": "Abruzzo", "chieti": "Abruzzo", "cl": "Sicilia", "caltanissetta": "Sicilia",
    "cn": "Piemonte", "cuneo": "Piemonte", "co": "Lombardia", "como": "Lombardia",
    "cr": "Lombardia", "cremona": "Lombardia", "cs": "Calabria", "cosenza": "Calabria",
    "ct": "Sicilia", "catania": "Sicilia", "cz": "Calabria", "catanzaro": "Calabria",
    "en": "Sicilia", "enna": "Sicilia", "fc": "Emilia-Romagna", "forli cesena": "Emilia-Romagna",
    "fe": "Emilia-Romagna", "ferrara": "Emilia-Romagna", "fg": "Puglia", "foggia": "Puglia",
    "fi": "Toscana", "firenze": "Toscana", "fm": "Marche", "fermo": "Marche",
    "fr": "Lazio", "frosinone": "Lazio", "ge": "Liguria", "genova": "Liguria",
    "go": "Friuli-Venezia Giulia", "gorizia": "Friuli-Venezia Giulia", "gr": "Toscana", "grosseto": "Toscana",
    "im": "Liguria", "imperia": "Liguria", "is": "Molise", "isernia": "Molise",
    "kr": "Calabria", "crotone": "Calabria", "lc": "Lombardia", "lecco": "Lombardia",
    "le": "Puglia", "lecce": "Puglia", "li": "Toscana", "livorno": "Toscana",
    "lo": "Lombardia", "lodi": "Lombardia", "lt": "Lazio", "latina": "Lazio",
    "lu": "Toscana", "lucca": "Toscana", "mb": "Lombardia", "monza brianza": "Lombardia",
    "mc": "Marche", "macerata": "Marche", "me": "Sicilia", "messina": "Sicilia",
    "mi": "Lombardia", "milano": "Lombardia", "mn": "Lombardia", "mantova": "Lombardia",
    "mo": "Emilia-Romagna", "modena": "Emilia-Romagna", "ms": "Toscana", "massa carrara": "Toscana",
    "mt": "Basilicata", "matera": "Basilicata", "na": "Campania", "napoli": "Campania",
    "no": "Piemonte", "novara": "Piemonte", "nu": "Sardegna", "nuoro": "Sardegna",
    "or": "Sardegna", "oristano": "Sardegna", "pa": "Sicilia", "palermo": "Sicilia",
    "pc": "Emilia-Romagna", "piacenza": "Emilia-Romagna", "pd": "Veneto", "padova": "Veneto",
    "pe": "Abruzzo", "pescara": "Abruzzo", "pg": "Umbria", "perugia": "Umbria",
    "pi": "Toscana", "pisa": "Toscana", "pn": "Friuli-Venezia Giulia", "pordenone": "Friuli-Venezia Giulia",
    "po": "Toscana", "prato": "Toscana", "pr": "Emilia-Romagna", "parma": "Emilia-Romagna",
    "pt": "Toscana", "pistoia": "Toscana", "pu": "Marche", "pesaro urbino": "Marche",
    "pv": "Lombardia", "pavia": "Lombardia", "pz": "Basilicata", "potenza": "Basilicata",
    "ra": "Emilia-Romagna", "ravenna": "Emilia-Romagna", "rc": "Calabria", "reggio calabria": "Calabria",
    "re": "Emilia-Romagna", "reggio emilia": "Emilia-Romagna", "rg": "Sicilia", "ragusa": "Sicilia",
    "ri": "Lazio", "rieti": "Lazio", "rm": "Lazio", "roma": "Lazio",
    "rn": "Emilia-Romagna", "rimini": "Emilia-Romagna", "ro": "Veneto", "rovigo": "Veneto",
    "sa": "Campania", "salerno": "Campania", "si": "Toscana", "siena": "Toscana",
    "so": "Lombardia", "sondrio": "Lombardia", "sp": "Liguria", "la spezia": "Liguria",
    "sr": "Sicilia", "siracusa": "Sicilia", "ss": "Sardegna", "sassari": "Sardegna",
    "su": "Sardegna", "sud sardegna": "Sardegna", "sv": "Liguria", "savona": "Liguria",
    "ta": "Puglia", "taranto": "Puglia", "te": "Abruzzo", "teramo": "Abruzzo",
    "tn": "Trentino-Alto Adige", "trento": "Trentino-Alto Adige", "to": "Piemonte", "torino": "Piemonte",
    "tp": "Sicilia", "trapani": "Sicilia", "tr": "Umbria", "terni": "Umbria",
    "ts": "Friuli-Venezia Giulia", "trieste": "Friuli-Venezia Giulia", "tv": "Veneto", "treviso": "Veneto",
    "ud": "Friuli-Venezia Giulia", "udine": "Friuli-Venezia Giulia", "va": "Lombardia", "varese": "Lombardia",
    "vb": "Piemonte", "verbano cusio ossola": "Piemonte", "vc": "Piemonte", "vercelli": "Piemonte",
    "ve": "Veneto", "venezia": "Veneto", "vi": "Veneto", "vicenza": "Veneto",
    "vr": "Veneto", "verona": "Veneto", "vt": "Lazio", "viterbo": "Lazio",
    "vv": "Calabria", "vibo valentia": "Calabria",
}


def map_province_to_region(province: Any) -> str | None:
    """Map an Italian province code or name to its region."""
    key = normalize_column_name(province)
    if not key:
        return None
    return PROVINCE_TO_REGION.get(key)
