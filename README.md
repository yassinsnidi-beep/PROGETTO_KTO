# Brev2Market Ingestion

Pipeline Python per importare aziende AIDA, industrie NACE e brevetti UNIBO in MongoDB Atlas. La pipeline legge file Excel/CSV, normalizza i dati, valida i documenti con Pydantic, genera embedding multilingua opzionali e fa upsert senza duplicati.

## Installazione

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Su Linux/macOS usare `source .venv/bin/activate`.

Su Google Colab non serve creare un virtual environment: il runtime Colab e' gia un ambiente Python temporaneo.

## Configurazione

Copia `.env.example` in `.env` e compila i valori:

```env
MONGODB_URI=mongodb+srv://...
MONGODB_DB_NAME=patent_matching
GENERATE_EMBEDDINGS=false
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
SENTENCE_TRANSFORMERS_DEVICE=
```

MongoDB non genera embedding: i vettori vengono creati dalla pipeline Python solo quando `GENERATE_EMBEDDINGS=true` o quando passi `--generate-embeddings`.

Provider supportati:

- `EMBEDDING_PROVIDER=openai`: usa `langchain-openai`. Modelli tipici: `text-embedding-3-small`, `text-embedding-3-large`. Richiede `OPENAI_API_KEY`.
- `EMBEDDING_PROVIDER=sentence_transformers`: usa modelli locali Hugging Face via `sentence-transformers`. Modelli consigliati: `intfloat/multilingual-e5-base`, `intfloat/multilingual-e5-large`, `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, `sentence-transformers/all-MiniLM-L6-v2`.
- `EMBEDDING_PROVIDER=ollama`: chiama l'API locale di Ollama. Modelli tipici: `nomic-embed-text`, `mxbai-embed-large`. Richiede Ollama avviato e `OLLAMA_BASE_URL`, di default `http://localhost:11434`.

Per Colab e portabilita, `sentence_transformers` e' la scelta piu semplice. Ollama e' piu adatto all'esecuzione locale.

## Cartelle dati

La pipeline usa una struttura a cartelle:

```text
data/
  input/
    companies/
    industries/
    patents/
  archive/
    companies/
    industries/
    patents/
  error/
    companies/
    industries/
    patents/
```

Metti i file da processare nelle cartelle `input`:

- aziende: `data/input/companies/*.xlsx`, sheet `Results`
- industrie: `data/input/industries/*.csv`
- brevetti: `data/input/patents/*.xlsx`, sheet `Brevetti`

Dopo l'elaborazione, il job sposta ogni file:

- in `data/archive/<categoria>/` se il file e' stato processato senza errori;
- in `data/error/<categoria>/` se ci sono errori di parsing, validazione, upsert o se non viene prodotto nessun documento valido.

Con `--dry-run` i file non vengono spostati. Con `--no-move` puoi processare senza routing verso `archive` o `error`.

## Esecuzione locale

Dry-run con un record per file:

```bash
python -m src.ingestion.ingest_all --dry-run --limit 1
```

Ingest completo:

```bash
python -m src.ingestion.ingest_all
```

Il comando sopra processa tutti i file trovati in `data/input/companies`, `data/input/industries` e `data/input/patents`.

Puoi ancora indicare file espliciti:

```bash
python -m src.ingestion.ingest_all ^
  --companies data/input/companies/Aida_Export_DEFINIT.xlsx ^
  --industries data/input/industries/nace_table.csv ^
  --patents data/input/patents/brevetti_unibo.xlsx
```

Con embedding:

```bash
python -m src.ingestion.ingest_all --generate-embeddings
```

Puoi saltare singole collection con `--skip-companies`, `--skip-industries`, `--skip-patents`.

## Google Colab

```python
from google.colab import files
uploaded = files.upload()
```

```bash
!pip install -r requirements.txt
```

Esempio Colab con embedding gratuiti/locali via Sentence Transformers:

```python
import os

os.environ["MONGODB_URI"] = "mongodb+srv://..."
os.environ["MONGODB_DB_NAME"] = "patent_matching"
os.environ["GENERATE_EMBEDDINGS"] = "true"
os.environ["EMBEDDING_PROVIDER"] = "sentence_transformers"
os.environ["EMBEDDING_MODEL"] = "intfloat/multilingual-e5-base"
```

```bash
!python -m src.ingestion.ingest_all \
  --companies "/content/Aida_Export_DEFINIT.xlsx" \
  --industries "/content/nace_table.csv" \
  --patents "/content/brevetti_unibo.xlsx" \
  --generate-embeddings
```

## Embedding Multilingua

Ogni documento contiene:

```json
{
  "embeddings": {
    "it": { "text": "...", "vector": [], "model": null },
    "en": { "text": "...", "vector": [], "model": null }
  }
}
```

Se gli embedding sono disabilitati, la pipeline salva solo `text`, lasciando `vector=[]` e `model=null`. Se sono abilitati, genera vettori separati per `embeddings.it.text` e `embeddings.en.text`.

Per le aziende, il testo embedding include solo `company_name`, `trade_description_it` e `trade_description_gb`. NACE, ATECO, provincia, regione, ricavi, dipendenti, R&D, tax code e CCIAA restano nel documento per filtri e ranking, ma non entrano nel vettore aziendale. Questo evita che il vettore descriva codici amministrativi invece del profilo operativo dell'impresa.

## Collection

`companies` usa `_id = company:{tax_code}` e contiene anagrafica, localizzazione, classificazioni NACE/ATECO, profilo business, financials, metriche R&D, qualita dati ed embedding.

`industries` usa `_id = industry:nace:{code}` e contiene gerarchia NACE, label IT/EN ed embedding separati.

`patents` usa `_id = patent:unibo:{scheda_id}` e contiene contenuti testuali del brevetto, KTO, TRL estratto, qualita dati ed embedding.

## Vector Search Index MongoDB Atlas

Gli indici Vector Search vanno creati manualmente in Atlas. Nomi consigliati:

- `companies_vector_it_index` su `embeddings.it.vector`
- `companies_vector_en_index` su `embeddings.en.vector`
- `industries_vector_it_index` su `embeddings.it.vector`
- `industries_vector_en_index` su `embeddings.en.vector`
- `patents_vector_it_index` su `embeddings.it.vector`
- `patents_vector_en_index` su `embeddings.en.vector`

JSON per ciascun indice, cambiando solo `path`:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embeddings.it.vector",
      "numDimensions": 1536,
      "similarity": "cosine"
    }
  ]
}
```

Per l'indice EN usa `embeddings.en.vector`.

`numDimensions` deve sempre corrispondere al modello:

- `text-embedding-3-small`: `1536`
- `text-embedding-3-large`: `3072`
- `sentence-transformers/all-MiniLM-L6-v2`: `384`
- `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`: `384`
- `intfloat/multilingual-e5-base`: `768`
- `intfloat/multilingual-e5-large`: `1024`
- `nomic-embed-text`: in genere `768`
- `mxbai-embed-large`: in genere `1024`

## Troubleshooting

- `MONGODB_URI is required`: stai eseguendo senza `--dry-run` e manca la variabile in `.env`.
- `OpenAI embeddings failed`: controlla `OPENAI_API_KEY` e `EMBEDDING_MODEL`, oppure esegui senza `--generate-embeddings`.
- `Sentence Transformers initialization failed`: controlla che `sentence-transformers` sia installato e che `EMBEDDING_MODEL` esista su Hugging Face.
- `Ollama connection refused`: avvia Ollama, scarica il modello con `ollama pull nomic-embed-text` e verifica `OLLAMA_BASE_URL`.
- Colonne mancanti: la pipeline logga warning e usa `None`; verifica newline e intestazioni del file sorgente.
- Documenti saltati: aziende senza tax code e senza nome, industrie senza codice NACE o brevetti senza `scheda_id` vengono scartati.
- Duplicati: gli upsert usano `_id` deterministici e `ReplaceOne(..., upsert=True)`.