# Schema Completo delle Collezioni MongoDB (Campi Innestati Inclusi)

Questo documento elenca in modo esaustivo tutti i campi (inclusi quelli innestati all'interno di oggetti e liste) per le 3 collezioni MongoDB del progetto: `companies`, `industries` e `patents`.

---

## 1. Collezione `companies`
Questa collezione descrive le anagrafiche, la localizzazione geografica, le classificazioni industriali, i bilanci, i profili commerciali e le metriche delle aziende.

| Campo | Tipo | Descrizione |
| :--- | :--- | :--- |
| `_id` | `str` | Identificativo univoco del documento azienda all'interno del database MongoDB. |
| `source` | `str` | Nome o identificativo della sorgente da cui provengono i dati dell'azienda. |
| `company_name` | `str` | Nome o ragione sociale ufficiale dell'azienda. |
| `normalized_name` | `str` | Nome dell'azienda normalizzato per facilitare ricerche e confronti. |
| `tax_code` | `str` | Codice fiscale o partita IVA dell'azienda. |
| `cciaa_number` | `str` | Numero di iscrizione alla Camera di Commercio (CCIAA). |
| `location` | `dict` | Informazioni geografiche e di localizzazione dell'azienda. |
| `location.province` | `str` | Sigla o nome della provincia in cui risiede l'azienda. |
| `location.region` | `str` | Regione italiana in cui si trova l'azienda. |
| `location.country` | `str` | Stato in cui si trova l'azienda (es. "Italy"). |
| `industry_classification` | `dict` | Codici di classificazione industriale dell'attività svolta. |
| `industry_classification.nace_rev_2` | `dict` | Classificazione industriale secondo lo standard europeo NACE Rev. 2. |
| `industry_classification.nace_rev_2.raw_code` | `str` | Codice NACE originale importato direttamente dalla sorgente. |
| `industry_classification.nace_rev_2.code` | `str` | Codice NACE normalizzato e validato per la classificazione. |
| `industry_classification.nace_rev_2.division` | `str` | Divisione industriale estratta dal codice NACE. |
| `industry_classification.nace_rev_2.description` | `str` | Descrizione testuale dell'attività associata al codice NACE. |
| `industry_classification.ateco_2007` | `dict` | Classificazione industriale secondo lo standard italiano ATECO 2007. |
| `industry_classification.ateco_2007.raw_code` | `str` | Codice ATECO 2007 originale non normalizzato. |
| `industry_classification.ateco_2007.code` | `str` | Codice ATECO 2007 normalizzato e validato. |
| `industry_classification.ateco_2007.description` | `str` | Descrizione testuale dell'attività associata all'ATECO 2007. |
| `industry_classification.ateco_2002` | `dict` | Classificazione industriale secondo lo standard italiano ATECO 2002. |
| `industry_classification.ateco_2002.raw_code` | `str` | Codice ATECO 2002 originale non normalizzato. |
| `industry_classification.ateco_2002.code` | `str` | Codice ATECO 2002 normalizzato e validato. |
| `industry_classification.ateco_2002.description` | `str` | Descrizione testuale dell'attività associata all'ATECO 2002. |
| `business_profile` | `dict` | Profilo aziendale e descrizione dell'attività svolta. |
| `business_profile.trade_description_it` | `str` | Descrizione commerciale dell'attività aziendale in lingua italiana. |
| `business_profile.trade_description_gb` | `str` | Descrizione commerciale dell'attività aziendale in lingua inglese. |
| `embeddings` | `dict` | Vettori di embedding multilingua associati ai testi dell'azienda. |
| `embeddings.it` | `dict` | Oggetto contenente il payload dell'embedding in italiano. |
| `embeddings.it.text` | `str` | Testo in italiano da cui è generato l'embedding. |
| `embeddings.it.vector` | `list[float]` | Vettori numerici dell'embedding per la ricerca semantica. |
| `embeddings.it.model` | `str` | Nome del modello AI usato per calcolare l'embedding. |
| `embeddings.en` | `dict` | Oggetto contenente il payload dell'embedding in inglese. |
| `embeddings.en.text` | `str` | Testo in inglese da cui è generato l'embedding. |
| `embeddings.en.vector` | `list[float]` | Vettori numerici dell'embedding per la ricerca semantica. |
| `embeddings.en.model` | `str` | Nome del modello AI usato per calcolare l'embedding. |
| `financials` | `dict` | Informazioni economico-finanziarie storiche dell'azienda. |
| `financials.accounting_closing_date` | `str` | Data di chiusura dell'ultimo bilancio disponibile. |
| `financials.revenues_th_eur` | `float` | Ricavi dell'azienda espressi in migliaia di euro. |
| `financials.employees` | `int` | Numero di dipendenti registrati nell'ultimo anno. |
| `financials.rnd_expenses_th_eur` | `dict` | Spese in Ricerca e Sviluppo in migliaia di euro. |
| `financials.rnd_expenses_th_eur.last_available_year` | `float` | Spese R&D dell'ultimo anno contabile disponibile. |
| `financials.rnd_expenses_th_eur.year_minus_1` | `float` | Spese R&D del primo anno precedente (-1). |
| `financials.rnd_expenses_th_eur.year_minus_2` | `float` | Spese R&D del secondo anno precedente (-2). |
| `financials.rnd_expenses_th_eur.year_minus_3` | `float` | Spese R&D del terzo anno precedente (-3). |
| `metrics` | `dict` | Metriche di performance economico-tecnologica dell'azienda. |
| `metrics.rnd_intensity` | `float` | Rapporto tra spese R&D e ricavi dell'ultimo anno. |
| `metrics.avg_rnd_4y_th_eur` | `float` | Media delle spese R&D degli ultimi 4 anni. |
| `metrics.rnd_continuity_score` | `float` | Frequenza e costanza dell'investimento in R&D nel tempo. |
| `metrics.rnd_growth_3y` | `float` | Tasso di crescita della spesa R&D in 3 anni. |
| `metrics.company_size_raw` | `float` | Dimensione aziendale grezza calcolata con il logaritmo dei dipendenti. |
| `metrics.revenue_raw` | `float` | Ricavi aziendali grezzi calcolati in scala logaritmica. |
| `metrics.rnd_intensity_norm` | `float` | Intensità di R&D normalizzata rispetto al dataset. |
| `metrics.avg_rnd_4y_norm` | `float` | Spesa R&D media quadriennale normalizzata rispetto al dataset. |
| `metrics.rnd_growth_3y_norm` | `float` | Tasso di crescita R&D normalizzato rispetto al dataset. |
| `metrics.company_size_norm` | `float` | Dimensione aziendale normalizzata rispetto al dataset. |
| `metrics.revenue_norm` | `float` | Ricavi aziendali normalizzati rispetto al dataset. |
| `metrics.technology_adoption_capacity_score` | `float` | Punteggio sintetico di capacità di adozione tecnologica. |
| `metrics.data_quality_score` | `float` | Punteggio medio globale della qualità dei dati. |
| `data_quality` | `dict` | Indicatori di completezza e qualità del record azienda. |
| `data_quality.has_tax_code` | `bool` | Indica se è presente il codice fiscale valido. |
| `data_quality.has_nace_code` | `bool` | Indica se è presente il codice NACE. |
| `data_quality.has_ateco_2007_code` | `bool` | Indica se è presente il codice ATECO 2007. |
| `data_quality.has_trade_description_it` | `bool` | Indica se è presente la descrizione in italiano. |
| `data_quality.has_trade_description_gb` | `bool` | Indica se è presente la descrizione in inglese. |
| `data_quality.has_revenues` | `bool` | Indica se è presente il dato dei ricavi. |
| `data_quality.has_employees` | `bool` | Indica se è presente il numero dei dipendenti. |
| `data_quality.has_rnd_data` | `bool` | Indica se sono presenti dati sulle spese R&D. |
| `created_at` | `str` | Data e ora di inserimento del record. |
| `updated_at` | `str` | Data e ora dell'ultimo aggiornamento del record. |

---

## 2. Collezione `industries`
Questa collezione mappa la classificazione dei settori industriali NACE Rev. 2 con le relative descrizioni gerarchiche multilingua.

| Campo | Tipo | Descrizione |
| :--- | :--- | :--- |
| `_id` | `str` | Identificativo univoco della classificazione industriale. |
| `source` | `str` | Origine dei dati della classificazione industriale. |
| `system` | `str` | Sistema normativo di classificazione utilizzato. |
| `code` | `str` | Codice identificativo normalizzato della categoria industriale. |
| `raw_code` | `str` | Codice originale non normalizzato registrato alla sorgente. |
| `level` | `str` | Livello gerarchico della classificazione (es. classe). |
| `labels` | `dict` | Contiene le denominazioni in varie lingue. |
| `labels.it` | `dict` | Denominazioni della categoria in lingua italiana. |
| `labels.it.class` | `str` | Descrizione in italiano del livello Classe NACE. |
| `labels.it.group` | `str` | Descrizione in italiano del livello Gruppo NACE. |
| `labels.it.division` | `str` | Descrizione in italiano del livello Divisione NACE. |
| `labels.it.section` | `str` | Descrizione in italiano del livello Sezione NACE. |
| `labels.en` | `dict` | Denominazioni della categoria in lingua inglese. |
| `labels.en.class` | `str` | Descrizione in inglese del livello Classe NACE. |
| `labels.en.group` | `str` | Descrizione in inglese del livello Gruppo NACE. |
| `labels.en.division` | `str` | Descrizione in inglese del livello Divisione NACE. |
| `labels.en.section` | `str` | Descrizione in inglese del livello Sezione NACE. |
| `group` | `dict` | Dettagli del livello di Gruppo industriale. |
| `group.code` | `str` | Codice identificativo del Gruppo NACE. |
| `group.label_it` | `str` | Descrizione in italiano del Gruppo NACE. |
| `group.label_en` | `str` | Descrizione in inglese del Gruppo NACE. |
| `division` | `dict` | Dettagli del livello di Divisione industriale. |
| `division.code` | `str` | Codice identificativo della Divisione NACE. |
| `division.label_it` | `str` | Descrizione in italiano della Divisione NACE. |
| `division.label_en` | `str` | Descrizione in inglese della Divisione NACE. |
| `section` | `dict` | Dettagli del livello di Sezione industriale. |
| `section.code` | `str` | Lettera identificativa della Sezione NACE. |
| `section.label_it` | `str` | Descrizione in italiano della Sezione NACE. |
| `section.label_en` | `str` | Descrizione in inglese della Sezione NACE. |
| `embeddings` | `dict` | Vettori di embedding multilingua associati al settore. |
| `embeddings.it` | `dict` | Payload dell'embedding in lingua italiana. |
| `embeddings.it.text` | `str` | Testo italiano concatenato usato per l'embedding. |
| `embeddings.it.vector` | `list[float]` | Lista dei valori dell'embedding in italiano. |
| `embeddings.it.model` | `str` | Modello AI usato per l'embedding italiano. |
| `embeddings.en` | `dict` | Payload dell'embedding in lingua inglese. |
| `embeddings.en.text` | `str` | Testo inglese concatenato usato per l'embedding. |
| `embeddings.en.vector` | `list[float]` | Lista dei valori dell'embedding in inglese. |
| `embeddings.en.model` | `str` | Modello AI usato per l'embedding inglese. |
| `created_at` | `str` | Data e ora di inserimento del record. |
| `updated_at` | `str` | Data e ora dell'ultimo aggiornamento del record. |

---

## 3. Collezione `patents`
Questa collezione raccoglie i dettagli, lo stato legale, lo stadio di sviluppo e i contatti dei brevetti depositati.

| Campo | Tipo | Descrizione |
| :--- | :--- | :--- |
| `_id` | `str` | Identificativo univoco del documento brevetto nel database. |
| `source` | `str` | Portale o database di origine da cui proviene il brevetto. |
| `scheda_id` | `str` | Identificativo univoco del brevetto nella sorgente originale. |
| `title` | `str` | Titolo del brevetto che descrive l'invenzione. |
| `subtitle` | `str` | Sottotitolo o descrizione secondaria associata al brevetto. |
| `url` | `str` | Link di riferimento alla pagina ufficiale del brevetto. |
| `abstract` | `str` | Riassunto tecnico del funzionamento e dello scopo del brevetto. |
| `short_description` | `str` | Descrizione breve e sintetica dell'invenzione. |
| `full_description` | `str` | Descrizione completa e dettagliata dell'invenzione. |
| `advantages` | `list[str]` | Elenco di stringhe contenenti i vantaggi della tecnologia. |
| `advantages.[]` | `str` | Singolo vantaggio tecnico o economico offerto dall'invenzione. |
| `applications` | `list[str]` | Elenco di stringhe con i campi applicativi dell'invenzione. |
| `applications.[]` | `str` | Singolo settore industriale o campo d'uso consigliato. |
| `development_stage` | `str` | Stato attuale di sviluppo e maturità dell'invenzione. |
| `trl` | `int` | Technology Readiness Level, livello di maturità tecnologica (1-9). |
| `protection_type` | `str` | Tipologia di tutela o brevetto applicato. |
| `patent_status` | `str` | Stato legale o amministrativo della domanda di brevetto. |
| `patent_number` | `str` | Numero ufficiale di registrazione o concessione del brevetto. |
| `application_number` | `str` | Numero identificativo di deposito della domanda di brevetto. |
| `kto` | `dict` | Dettagli relativi al Knowledge Transfer Office di riferimento. |
| `kto.contact_name` | `str` | Nome del referente KTO per contatti commerciali. |
| `kto.email` | `str` | Email di contatto del referente KTO. |
| `kto.phone` | `str` | Numero di telefono del referente KTO. |
| `embeddings` | `dict` | Vettori di embedding multilingua per la ricerca semantica. |
| `embeddings.it` | `dict` | Payload dell'embedding in lingua italiana. |
| `embeddings.it.text` | `str` | Testo italiano concatenato usato per l'embedding. |
| `embeddings.it.vector` | `list[float]` | Lista dei valori dell'embedding in italiano. |
| `embeddings.it.model` | `str` | Modello AI usato per l'embedding italiano. |
| `embeddings.en` | `dict` | Payload dell'embedding in lingua inglese. |
| `embeddings.en.text` | `str` | Testo inglese concatenato usato per l'embedding. |
| `embeddings.en.vector` | `list[float]` | Lista dei valori dell'embedding in inglese. |
| `embeddings.en.model` | `str` | Modello AI usato per l'embedding inglese. |
| `data_quality` | `dict` | Indicatori qualitativi booleani del record brevetto. |
| `data_quality.has_title` | `bool` | Indica se è presente il titolo del brevetto. |
| `data_quality.has_abstract` | `bool` | Indica se è presente l'abstract del brevetto. |
| `data_quality.has_full_description` | `bool` | Indica se è presente la descrizione completa. |
| `data_quality.has_applications` | `bool` | Indica se sono presenti applicazioni descritte. |
| `data_quality.has_advantages` | `bool` | Indica se sono presenti vantaggi specificati. |
| `created_at` | `str` | Data e ora di inserimento del record. |
| `updated_at` | `str` | Data e ora dell'ultimo aggiornamento del record. |
