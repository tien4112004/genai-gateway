# Ingestion App

Offline pipeline that loads Vietnamese educational textbooks (SGK/SGV PDFs), splits them into hierarchical chunks, embeds them with Vertex AI, and stores the vectors in PostgreSQL + pgvector for use by the main AI Worker's RAG endpoints.

Run this pipeline **once per document set** (or when new books are added). The main app queries the resulting vector store at request time — it does not ingest on its own.

---

## How It Fits in the System

```
[Textbook PDFs]
      │
      ▼  ingestion_app/main.py (offline, run once)
DocumentLoader  ──→  LlamaParse (Vision model, markdown output)
      │
      ▼
DocumentChunker ──→  Hierarchical parent/child chunks
      │
      ▼
EmbeddingService ──→  Vertex AI text-embedding-004  (768 dims)
      │
      ▼
VectorStoreManager ──→  PostgreSQL + pgvector
                              │
                              │  (at request time)
                              ▼
                    ai-worker / RAG endpoints
                    DocumentEmbeddingsRepository
                    Vertex AI text-embedding-004  ← same model
```

> **Embedding model must match on both sides.** Vectors written by ingestion and query vectors computed by the main app must come from the **same model**. Both sides read `EMBEDDING_MODEL` from the shared `.env`. If you ever switch models, re-run ingestion from scratch (`--reset`).

---

## Pipeline Steps

### 1. Load — `documents_loader.py`

Uses **LlamaParse** (Vision model) rather than plain PDF parsers, because SGK textbooks have complex layouts: mixed columns, embedded images, math formulas, and tables.

LlamaParse config applied:
- `result_type="markdown"` — preserves heading and list structure
- `auto_mode=True` — activates image-aware parsing when >30% of a page is image
- `table_structure_parsing="advanced"` — correctly extracts tabular data
- `parsing_instruction` — Vietnamese-specific hint so the model recognises exercise blocks and formulas

Falls back to basic PyMuPDF loader if LlamaParse is unavailable or fails.

Supported formats: `.pdf`, `.txt`, `.md`, `.docx`

### 2. Chunk — `documents_chunking.py`

Uses **hierarchical (parent-child) chunking** instead of fixed-size splitting:

| Chunk type | Default size | Purpose |
|------------|-------------|---------|
| Parent | ~2000 chars | Stores full context; returned to the LLM |
| Child | ~500 chars | Embedded and indexed for similarity search |

Each child chunk carries its parent's full text in metadata (`parent_text`). At retrieval time the main app searches on child embeddings but the LLM receives the parent text, giving it the wider context needed for accurate generation.

Splitter separators (in priority order): `\n\n` → `\n` → `. ` → ` ` → `""`

### 3. Embed — `documents_embedding.py`

- Model: **Vertex AI `text-embedding-004`**
- Dimension: **768**
- Auth: service account JSON via `GOOGLE_APPLICATION_CREDENTIALS`

### 4. Store — `vector_store.py`

- Database: PostgreSQL + pgvector extension
- LangChain `PGVector` integration
- Each chunk is stored with JSONB metadata for filtered search:

```json
{
  "grade": 3,
  "subject_code": "T",
  "subject_name": "Toán",
  "chunk_type": "child",
  "parent_text": "...",
  "parent_id": 12
}
```

### 5. Metadata — `metadata_parser.py`

Educational metadata (`grade`, `subject_code`) is automatically extracted from the **filename** using the naming convention below. This metadata is attached to every stored chunk and used as a filter at retrieval time.

---

## Filename Convention

The parser recognises the standard Vietnamese SGK/SGV naming scheme:

```
SG[VK]_KNTT_<SUBJECT><GRADE>[_T<VERSION>]
```

| Filename | Grade | Subject code | Subject name |
|----------|-------|--------------|--------------|
| `SGV_KNTT_T1.pdf` | 1 | `T` | Toán (Math) |
| `SGK_KNTT_TA3.pdf` | 3 | `TA` | Tiếng Anh (English) |
| `SGV_KNTT_TV5_T2.pdf` | 5 | `TV` | Tiếng Việt (Literature) |

Files that do not match the pattern are still ingested, but without grade/subject metadata — they will not be returned by filtered RAG queries.

---

## Prerequisites

- PostgreSQL 15+ with the `pgvector` extension installed
- A Vertex AI service account with `Vertex AI User` role
- A LlamaIndex Cloud API key (for LlamaParse PDF parsing)
- The shared `.env` file at the project root

**Install pgvector (Ubuntu/Debian):**

```bash
sudo apt install postgresql-15-pgvector   # adjust version
# then in psql:
CREATE EXTENSION vector;
```

For a full setup guide see [`PGVECTOR_SETUP.md`](./PGVECTOR_SETUP.md).

---

## Environment Variables

The ingestion app reads from the same `.env` as the main app. Variables specific to ingestion:

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `text-embedding-004` | **Must match the main app** |
| `COLLECTION_NAME` | `documents` | pgvector collection name |
| `PARENT_CHUNK_SIZE` | `2000` | Parent chunk size in characters |
| `CHILD_CHUNK_SIZE` | `500` | Child chunk size in characters |
| `CHUNK_OVERLAP` | `100` | Overlap between consecutive chunks |
| `PDF_LANGUAGE` | `vi` | OCR language hint for LlamaParse |
| `USE_PREMIUM_PDF_MODE` | `true` | Enable LlamaParse premium mode |
| `LLAMA_CLOUD_API_KEY` | — | LlamaIndex Cloud API key (required for PDF) |
| `PG_CONNECTION_STRING` | — | Full SQLAlchemy connection URL (preferred) |
| `PG_HOST` | `localhost` | Used if `PG_CONNECTION_STRING` is not set |
| `PG_PORT` | `5432` | — |
| `PG_DATABASE` | `vectordb` | — |
| `PG_USER` | `postgres` | — |
| `PG_PASSWORD` | — | Required if not using `PG_CONNECTION_STRING` |

---

## Running the Pipeline

From the **project root**:

```bash
# Activate your virtual environment first
source venv/bin/activate

# Ingest all documents in the default directory (./data/documents)
python ingestion_app/main.py

# Specify a different directory
python ingestion_app/main.py --docs-dir /path/to/textbooks

# Wipe the collection and re-ingest from scratch
python ingestion_app/main.py --reset

# Override collection name
python ingestion_app/main.py --collection-name my_collection

# All options combined
python ingestion_app/main.py \
  --docs-dir ./data/documents \
  --collection-name document_embeddings \
  --reset \
  --recursive
```

The script prints a live progress summary per document and a final count of chunks stored.

---

## Directory Structure

```
ingestion_app/
├── main.py                 # CLI entry point — orchestrates the full pipeline
├── documents_loader.py     # Load PDFs/DOCX/TXT via LlamaParse or fallback
├── documents_chunking.py   # Hierarchical parent-child splitting
├── documents_embedding.py  # Vertex AI embedding wrapper
├── vector_store.py         # PGVector store operations
├── metadata_parser.py      # Extract grade/subject from filename
├── debug_pdf.py            # Standalone tool to inspect a single PDF parse result
├── PGVECTOR_SETUP.md       # PostgreSQL + pgvector setup guide
└── README.md               # This file

data/
└── documents/              # Place source PDFs here (create this directory)
    ├── SGV_KNTT_T1.pdf
    ├── SGV_KNTT_TA3.pdf
    └── SGV_KNTT_TV5_T2.pdf
```

---

## Troubleshooting

**`Extension 'vector' does not exist`**

```sql
-- Run as a PostgreSQL superuser
CREATE EXTENSION vector;
```

**`VERTEX_PROJECT_ID environment variable is required`**

Ensure `.env` is present at the project root and `VERTEX_PROJECT_ID` is set.

**`Either PG_CONNECTION_STRING or PG_PASSWORD environment variable is required`**

Set `PG_CONNECTION_STRING` (e.g. `postgresql+psycopg2://postgres:pass@localhost:5432/vectordb`) or individual `PG_HOST` / `PG_PASSWORD` variables.

**LlamaParse fails / falls back to basic loader**

- Check `LLAMA_CLOUD_API_KEY` is set and valid (obtain from [cloud.llamaindex.ai](https://cloud.llamaindex.ai))
- The basic fallback (PyMuPDF) still works but loses table structure and mixed-layout accuracy

**Retrieval returns irrelevant results after changing embedding model**

Re-run ingestion with `--reset` to rebuild all vectors with the new model. Mixing vectors from different models in the same collection produces incorrect similarity scores.
