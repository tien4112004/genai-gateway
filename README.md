# AI Worker

A FastAPI microservice for AI-powered educational content generation, exam creation, question grading, and mind mapping. Supports multiple LLM providers (Google Gemini, OpenAI, Anthropic, OpenRouter) with optional RAG via PostgreSQL + pgvector.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Environment Variables](#environment-variables)
- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [Production Deployment (Jenkins)](#production-deployment-jenkins)
- [CI/CD (GitHub Actions)](#cicd-github-actions)
- [API Reference](#api-reference)
- [Developer Guide](#developer-guide)
  - [Project Structure](#project-structure)
  - [Prompt System](#prompt-system)
  - [Audience Context System](#audience-context-system)
  - [RAG Flow](#rag-flow)
  - [Adding a New LLM Provider](#adding-a-new-llm-provider)
  - [Adding a New Endpoint](#adding-a-new-endpoint)
  - [Dependency Management](#dependency-management)
  - [Testing](#testing)
  - [Observability](#observability)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        FastAPI App                          │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐│
│  │Middleware│  │ API Endpoints│  │   Exception Handlers   ││
│  │(TraceID) │  │  /api/...    │  │                        ││
│  └──────────┘  └──────┬───────┘  └────────────────────────┘│
└─────────────────────────┼───────────────────────────────────┘
                          │ Depends()
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
   ContentService    ExamService     RAG Services
   ModificationSvc   GradingLogic    (Slide/Mindmap/Exam)
          │               │                │
          └───────────────┴────────────────┘
                          │
                    LLMExecutor
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
   GeminiAdapter    OpenAIAdapter    Other Adapters
                          │
                    PromptStore ──── registry.yaml
                          │
                  DocumentEmbeddingsRepository
                          │
                   PostgreSQL + pgvector
                   Vertex AI Embeddings
```

**Key design choices:**

| Concern | Solution |
|---------|----------|
| Multi-provider LLM | `LLMExecutor` routes by `provider` + `model` string |
| Prompt management | File-based `.st` templates registered in `registry.yaml` |
| Audience targeting | `get_audience_context()` injects education vs. general persona |
| RAG | LangGraph agent calls `search_documents` tool → pgvector |
| Tracing | Phoenix (Arize) via OpenTelemetry / LangChain instrumentation |
| DI | FastAPI `app.state` + `Depends()` annotated type aliases |

---

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.11 (3.10+ compatible) |
| Docker + docker-compose | 24+ |
| PostgreSQL with pgvector | 15+ |
| Google Cloud project | Vertex AI API enabled |

**GCP service account permissions required:**

- `Vertex AI User` — for embeddings and Vertex AI models
- `Storage Object Viewer` — if reading documents from GCS

---

## Environment Variables

Copy the sample file and fill in all required values:

```bash
cp .env.sample .env
```

### Required

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google AI Studio API key (Gemini models) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Vertex AI service account JSON |
| `VERTEX_PROJECT_ID` | GCP project ID |
| `VERTEX_LOCATION` | GCP region (default: `us-central1`) |
| `DATABASE_URL` | PostgreSQL connection string for the main DB |
| `PG_CONNECTION_STRING` | PostgreSQL + pgvector connection string (same DB or separate) |
| `PHOENIX_COLLECTOR_ENDPOINT` | Phoenix tracing server URL (e.g. `http://localhost:6006`) |

### Optional — LLM Providers

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `OPENROUTER_BASE_URL` | OpenRouter base URL (default in `.env.sample`) |
| `LOCALAI_API_KEY` | LocalAI key (default: `sk-local`) |
| `LOCALAI_BASE_URL` | LocalAI server URL |

### Optional — App Tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `APP_NAME` | `fastapi-langchain-starter` | Display name in Swagger UI |
| `DEFAULT_MODEL` | `gemini-2.5-flash-lite` | Fallback model when not specified |
| `LLM_TEMPERATURE` | `0.7` | Generation temperature |
| `LLM_MAX_TOKENS` | `2048` | Max tokens per response |
| `MAX_RETRIES` | `3` | LLM retry count |
| `ALLOWED_ORIGINS` | `http://localhost:3000,...` | CORS allowed origins |
| `COLLECTION_NAME` | `document_embeddings` | pgvector collection name |
| `EMBEDDING_MODEL` | `text-embedding-004` | Vertex AI embedding model |

### Optional — Observability

| Variable | Description |
|----------|-------------|
| `PHOENIX_API_KEY` | Phoenix authentication key |
| `PHOENIX_SECRET` | Phoenix auth secret |
| `PHOENIX_PROJECT_NAME` | Project label in Phoenix UI |
| `PHOENIX_SQL_DATABASE_URL` | PostgreSQL for Phoenix trace storage |
| `OTEL_EXPORTER_OTLP_HEADERS` | OTLP export headers (e.g. `Authorization=Bearer <key>`) |

### Vertex AI Service Account

1. Create a service account in Google Cloud Console with `Vertex AI User` role.
2. Download the JSON key file.
3. Place it at the path set in `GOOGLE_APPLICATION_CREDENTIALS` (default: `./service-account.json`).

> If the file is missing at startup, Vertex AI is skipped (mock mode). The app still boots, but RAG and embedding features will fail at request time.

---

## Local Development

### First-time Setup

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install pip-tools and compile + sync dependencies
pip install --upgrade pip pip-tools
make setup                         # compiles .in → .txt, syncs env, sets up pre-commit

# 3. Copy and configure environment
cp .env.sample .env
# Edit .env with your keys
```

### Run the Application

```bash
make run          # port 8081 (standard)
make run-default  # port 8080
```

Or directly:

```bash
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8081
```

Swagger UI is available at `http://localhost:8081/docs`.

### Makefile Reference

**Development:**

| Command | Description |
|---------|-------------|
| `make setup` | Full first-time setup |
| `make run` | Start app on port 8081 |
| `make test` | Run all tests |
| `make test-with-coverage` | Tests + HTML coverage report |
| `make clean` | Remove `__pycache__`, `.pytest_cache`, build artifacts |

**Dependencies:**

| Command | Description |
|---------|-------------|
| `make compile-deps` | Compile all `.in` → `.txt` files |
| `make upgrade-deps` | Upgrade all deps to latest compatible versions |
| `make sync-deps` | Sync venv with compiled `.txt` files |
| `make install-dev` | Install dev dependencies only |
| `make install-test` | Install test dependencies only |
| `make show-outdated` | List outdated packages |

**Docker:**

| Command | Description |
|---------|-------------|
| `make docker-build` | Build `ai-worker:latest` image |
| `make docker-build-fast` | Build with BuildKit |
| `make docker-run` | Run container on port 8081 |
| `make docker-compose-up` | Start full dev stack (app + Phoenix) |
| `make docker-compose-down` | Stop dev stack |
| `make docker-compose-rebuild` | Rebuild and restart dev stack |
| `make docker-compose-up-prod` | Start production stack |
| `make docker-logs` | Follow container logs |
| `make docker-shell` | Shell into running container |
| `make docker-test` | Build, smoke-test, then teardown |
| `make docker-push-ghcr` | Push image to GitHub Container Registry |

---

## Docker Deployment

### Development Stack

The `docker-compose.yml` starts two services:

- **ai-worker** — the FastAPI app on port `8081`
- **phoenix** — LLM tracing UI on port `6006`, gRPC on `4317`, HTTP on `9090`

```bash
# Start
make docker-compose-up

# View logs
make docker-compose-logs

# Stop
make docker-compose-down
```

Both services join an **external** Docker network (`datn-be_default`). Create it first if it does not exist:

```bash
docker network create datn-be_default
```

### Production Stack

`docker-compose.prod.yml` pulls the pre-built image from GHCR and uses a separate external network (`network-aiprimary`):

```bash
docker network create network-aiprimary   # once, if missing

make docker-compose-up-prod
```

The production image is `ghcr.io/tien4112004/genai-gateway:latest`.

### Dockerfile Details

The image uses a **two-stage build**:

1. **Builder** — installs all Python dependencies on `python:3.11-slim`
2. **Runtime** — minimal image, copies only the installed packages and app code

Runtime characteristics:

| Property | Value |
|----------|-------|
| Base image | `python:3.11-slim` |
| Exposed port | `8081` |
| Run user | `appuser` (non-root) |
| Health check | `curl -f http://localhost:8081/docs` every 30 s |
| CPU limit | 1 core |
| Memory limit | 768 MB |

---

## Production Deployment (Jenkins)

The `Jenkinsfile` automates the full deploy cycle:

1. **Validate environment** — checks Docker, docker-compose, and `.env` in `DEPLOY_DIR` (`/opt/ai-worker`)
2. **Authenticate** — logs into GHCR using `GITHUB_TOKEN`
3. **Pull image** — fetches `ghcr.io/tien4112004/genai-gateway:latest`
4. **Deploy** — runs `docker-compose -f docker-compose.prod.yml up -d`
5. **Health check** — polls `/docs` up to 5 times with 10 s interval
6. **Cleanup** — prunes dangling images

Required Jenkins credentials:

| ID | Type | Description |
|----|------|-------------|
| `github-token` | Secret text | GitHub PAT with `read:packages` |

Required Jenkins environment:

| Variable | Description |
|----------|-------------|
| `DEPLOY_DIR` | `/opt/ai-worker` (set in Jenkinsfile) |
| `ENV_FILE` | `${DEPLOY_DIR}/.env` |

---

## CI/CD (GitHub Actions)

Three workflows live in `.github/workflows/`:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push to `main`/`develop`, PRs | Install deps, run tests, coverage |
| `docker.yml` | Push to `main` | Build multi-platform image, push to GHCR |
| `security.yml` | Scheduled / PR | Security scanning |

**Secrets required in GitHub repo settings:**

`OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `VERTEX_LOCATION`, `VERTEX_PROJECT_ID`

---

## API Reference

All endpoints are prefixed with `/api`. Interactive docs: `GET /docs`.

### Content Generation

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/outline/generate` | Generate a course outline (batch) |
| POST | `/api/outline/generate/stream` | Same, streaming (SSE) |
| POST | `/api/presentation/generate` | Generate presentation slides (batch) |
| POST | `/api/presentation/generate/stream` | Same, streaming |
| POST | `/api/mindmap/generate` | Generate a mind map (batch) |
| POST | `/api/mindmap/generate/stream` | Same, streaming |
| POST | `/api/slides/generate` | Generate individual slides |
| POST | `/api/image/generate` | Generate an image (returns base64) |

**RAG is activated automatically** when `grade` + `subject` are both present in the request body (no `file_urls`). The service then retrieves from the pgvector store before generating.

**Example — generate outline (general mode):**

```bash
curl -X POST http://localhost:8081/api/outline/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Introduction to Artificial Intelligence",
    "slide_count": 5,
    "model": "gemini-2.5-flash-lite",
    "provider": "google",
    "language": "vi"
  }'
```

**Example — generate outline (education / RAG mode):**

```bash
curl -X POST http://localhost:8081/api/outline/generate \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "My House",
    "slide_count": 8,
    "model": "gemini-2.5-flash-lite",
    "provider": "google",
    "language": "vi",
    "grade": "3",
    "subject": "TA"
  }'
```

### Exam & Questions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/exams/matrix/generate` | Generate exam matrix structure |
| POST | `/api/exams/questions/generate` | Generate questions from matrix |
| POST | `/api/questions/generate` | Generate questions from topic |
| POST | `/api/questions/generate/context` | Generate questions from a reading passage |
| POST | `/api/questions/generate/by_topic` | Advanced topic-based generation |
| POST | `/api/questions/grade` | Grade an open-ended student answer |

**Example — grade a question:**

```bash
curl -X POST http://localhost:8081/api/questions/grade \
  -H "Content-Type: application/json" \
  -d '{
    "question_content": "What is 3 × 4?",
    "student_answer": "12",
    "expected_answer": "12",
    "max_score": 1,
    "grade": "3",
    "subject": "T"
  }'
```

Response: `{ "totalScore": 1.0, "feedback": "..." }` (feedback always in Vietnamese)

### Content Modification

| Method | Path | Operations |
|--------|------|------------|
| POST | `/api/modification/slides/{operation}` | `refine`, `expand`, `shorten`, `grammar`, `formal`, `layout` |
| POST | `/api/modification/elements/{operation}` | `refine`, `expand`, `shorten`, `grammar`, `formal`, `replace_image` |
| POST | `/api/modification/mindmap/nodes/{operation}` | `expand`, `shorten`, `grammar`, `formal`, `expand_branch`, `shorten_branch`, `grammar_branch`, `formal_branch` |

### Image Generation

```bash
curl -X POST http://localhost:8081/api/image/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A Vietnamese primary school classroom",
    "model": "imagen-3.0-generate-001",
    "provider": "google",
    "number_of_images": 1,
    "aspect_ratio": "16:9",
    "negative_prompt": "blurry, low quality"
  }'
```

Response: `{ "base64_image": "iVBORw0KGgo..." }`

### Streaming

Streaming endpoints return **Server-Sent Events (SSE)**. Use `curl -N` or an SSE client:

```bash
curl -N -X POST http://localhost:8081/api/outline/generate/stream \
  -H "Content-Type: application/json" \
  -d '{ "topic": "Photosynthesis", "slide_count": 5, "provider": "google", "model": "gemini-2.5-flash-lite", "language": "en" }'
```

---

## Developer Guide

### Project Structure

```
ai-worker/
├── app/
│   ├── main.py                      # FastAPI app factory + lifespan
│   ├── api/
│   │   ├── router.py                # Registers all sub-routers under /api
│   │   └── endpoints/
│   │       ├── generate.py          # Outline, presentation, mindmap, image, slides
│   │       ├── exams.py             # Exam matrix + questions
│   │       ├── grading_question.py  # Question grading
│   │       └── modification.py      # Content modification ops
│   ├── core/
│   │   ├── config.py                # Pydantic Settings (reads .env)
│   │   ├── fastapi_depends.py       # Annotated Depends() aliases
│   │   └── global_depends.py        # DI Container
│   ├── llms/
│   │   ├── executor.py              # LLMExecutor — routes provider+model to adapter
│   │   └── adaper/                  # Per-provider adapter classes
│   │       ├── gemini.py
│   │       ├── openai.py
│   │       ├── open_router.py
│   │       ├── localai.py
│   │       ├── rag_mixins.py        # RAGAdapterMixin
│   │       └── image_models/
│   │           └── nano_banana.py
│   ├── prompts/
│   │   ├── registry.yaml            # Maps prompt keys → .st file paths
│   │   ├── loader.py                # PromptStore class
│   │   ├── subject_prompt_router.py # subject code → curriculum key mapping
│   │   ├── common/                  # Shared partials (safety.st, audience *.st)
│   │   ├── outline/
│   │   ├── presentation/
│   │   ├── mindmap/
│   │   ├── question/
│   │   ├── exam/
│   │   ├── image/
│   │   ├── slide_generation/
│   │   ├── modification/
│   │   └── subject_grade/           # math/, literature/, english/ — grades 1–5
│   ├── services/
│   │   ├── content_service.py
│   │   ├── exam_service.py
│   │   ├── base_rag_service.py
│   │   ├── slide_rag_service.py
│   │   ├── mindmap_rag_service.py
│   │   ├── exam_rag_service.py
│   │   ├── content_rag_service.py
│   │   ├── modification_service.py
│   │   └── teacher_system_prompt_service.py
│   ├── repositories/
│   │   ├── document_embeddings_repository.py   # pgvector operations
│   │   └── teacher_system_prompt_repository.py
│   ├── schemas/                      # Pydantic request/response models
│   ├── middleware/
│   │   └── trace_id.py              # Injects X-Trace-ID into OpenTelemetry spans
│   └── utils/
│       ├── audience_context.py      # get_audience_context()
│       ├── file_extractor.py        # PDF, DOCX, image content extraction
│       ├── server_sent_event.py     # SSE helpers
│       └── token_tracker.py        # Accumulates TokenUsage across calls
├── ingestion_app/                   # Separate pipeline: load → chunk → embed → store
├── tests/
├── scripts/
│   ├── build-image.sh
│   └── setup-pre-commit.sh
├── Dockerfile
├── docker-compose.yml               # Dev stack
├── docker-compose.prod.yml          # Prod stack
├── Jenkinsfile
├── Makefile
├── pyproject.toml
├── requirements.in                  # Production deps (source)
├── requirements.txt                 # Compiled (auto-generated, commit this)
├── requirements-dev.in / .txt
└── requirements-test.in / .txt
```

---

### Prompt System

All prompts are plain-text **Python `string.Template`** files (`.st` extension). They are discovered through `registry.yaml` and rendered at request time by `PromptStore`.

#### Adding or Editing a Prompt

**1. Write the template file** using `${variable_name}` for substitution:

```
# app/prompts/my_feature/sys_prompt.st
${audience_context}

You are a helpful AI. The topic is ${topic}.

${safety_rules}
```

**2. Register it** in `registry.yaml`:

```yaml
prompts:
  my_feature.system:
    path: "my_feature/sys_prompt.st"
    format: "st"
```

**3. Render it** in a service:

```python
system_prompt = self.prompt_store.render(
    "my_feature.system",
    {"topic": request.topic, "audience_context": audience_ctx},
)
```

#### Built-in Template Variables

| Variable | Resolved by | Description |
|----------|-------------|-------------|
| `${safety_rules}` | `PromptStore.render()` automatically | Content from `common/safety.st` |
| `${audience_context}` | Caller via `get_audience_context()` | Education or general persona |
| `${subject_grade_prompt}` | `BaseRagService._system_with_subject_grade()` | Curriculum notes for grade/subject |

Missing variables silently become empty strings (via `_DefaultDict`), so templates are safe to render with partial variable sets.

#### Prompt Registry Key Convention

```
<domain>.<variant>.<modifier>

outline.system          → sys_prompt.st
outline.system.rag      → sys_prompt_rag.st  (RAG variant)
outline.user            → usr_prompt.st
subject_grade.math.3    → subject_grade/math/grade_3.st
```

---

### Audience Context System

The audience context system switches the AI persona between **education mode** (primary school, ages 6–11) and **general mode** based on whether both `subject` and `grade` are provided in the request.

```
subject is not None AND grade is not None  →  Education mode
anything else                              →  General mode
```

**Utility:** `app/utils/audience_context.py`

```python
from app.utils.audience_context import get_audience_context

ctx = get_audience_context(subject=request.subject, grade=request.grade)
# Returns one of two strings loaded from:
#   app/prompts/common/education_audience.st
#   app/prompts/common/general_audience.st
```

Both files are read **once at module load** — zero I/O per request. A missing file raises `RuntimeError` at startup.

**Routing table:**

| `subject` | `grade` | Mode |
|-----------|---------|------|
| `"T"` | `3` | Education |
| `"TA"` | `0` | Education |
| `None` | `None` | General |
| `"T"` | `None` | General |
| `None` | `5` | General |

**Subject code mapping** (`app/prompts/subject_prompt_router.py`):

| Code | Subject |
|------|---------|
| `T` | Math (Toán) |
| `TV` | Literature (Tiếng Việt) |
| `TA` | English (Tiếng Anh) |

**To add a new audience mode**, see [`audience-context-system.md`](./audience-context-system.md) for a step-by-step guide (create `.st` file → extend `get_audience_context()` → add tests).

---

### RAG Flow

RAG (Retrieval-Augmented Generation) is used when generating content for a specific `grade` + `subject` pair, pulling relevant document chunks from the pgvector store before calling the LLM.

#### Ingestion (offline, `ingestion_app/`)

```
PDF/DOCX documents
      │
      ▼
LlamaParse (Vision model, result_type="markdown")
      │
      ▼
Hierarchical Chunking
  ├─ Parent chunks (~2000 chars) — full context
  └─ Child chunks (~500 chars)  — indexed for search
      │
      ▼
Vertex AI text-embedding-004 (768 dimensions)
      │
      ▼
PostgreSQL + pgvector
  metadata: { subject_code, grade, book_type }
```

#### Retrieval (runtime)

```
POST /api/outline/generate  { grade: "3", subject: "T" }
      │
      ▼
SlideRagService._system_with_subject_grade()
  ├─ get_audience_context(subject, grade)     → education persona
  ├─ get_subject_grade_prompt_key(subject, grade) → curriculum notes
  └─ prompt_store.render("outline.system.rag", vars)
      │
      ▼
LangGraph Agent (create_tool_calling_executor)
  Agent decides to call search_documents tool
      │
      ▼
DocumentEmbeddingsRepository.similarity_search(
    query=topic,
    filter={ subject_code: "T", grade: 3 },
    k=10
)
  Fallback: retry without filter if no results
      │
      ▼
Retrieved parent chunks injected into LLM context
      │
      ▼
LLM generates content grounded in textbook material
```

#### Embedding Model Consistency

> **Critical:** The embedding model used during ingestion and during retrieval **must be identical**. Vectors stored with one model are not comparable to query vectors produced by a different model — similarity scores will be meaningless and retrieval will silently return wrong results.
>
> Both sides are controlled by the same `EMBEDDING_MODEL` environment variable (default: `text-embedding-004`, 768 dimensions). If you change the model, you must **re-run the full ingestion pipeline** to rebuild all stored vectors.

#### Search Strategy

The system uses **MMR (Maximal Marginal Relevance)** retrieval to balance relevance with diversity:

- `k=10` results returned
- `fetch_k=20` candidates considered
- Filter by `subject_code` + `grade` metadata
- Auto-fallback to unfiltered search if no results match

#### Adding RAG to a New Feature

1. Create a RAG-specific system prompt `sys_prompt_rag.st` with `${audience_context}`, `${subject_grade_prompt}`, and `${safety_rules}`.
2. Register it in `registry.yaml` as `<feature>.system.rag`.
3. Create a service that extends `BaseRagService` and calls `_system_with_subject_grade()`.
4. Wire the service into `app/main.py` lifespan and expose via `fastapi_depends.py`.

---

### Adding a New LLM Provider

1. **Create adapter** in `app/llms/adaper/my_provider.py`:

```python
class MyProviderAdapter:
    def __init__(self, model_name: str, **kwargs):
        self.client = MyProviderClient(model=model_name, ...)

    def run(self, system_prompt: str, user_prompt: str, **kwargs) -> tuple[str, TokenUsage]:
        response = self.client.generate(...)
        return response.text, TokenUsage(...)

    def stream(self, system_prompt: str, user_prompt: str, **kwargs) -> Iterator[str]:
        for chunk in self.client.stream(...):
            yield chunk.text
```

2. **Register** in `app/llms/executor.py`:

```python
adapters = {
    "openai": OpenAIAdapter,
    "google": GeminiAdapter,
    "my_provider": MyProviderAdapter,   # add here
    ...
}
```

3. **Add API key** to `app/core/config.py` and `.env.sample`.

---

### Adding a New Endpoint

1. **Define schema** in `app/schemas/my_feature.py` (Pydantic models for request/response).

2. **Create service** in `app/services/my_feature_service.py`.

3. **Wire into lifespan** in `app/main.py`:

```python
my_service = MyFeatureService(llm_executor=llm_executor, prompt_store=prompt_store)
app.state.my_service = my_service
```

4. **Add dependency** in `app/core/fastapi_depends.py`:

```python
def get_my_service(request: Request) -> MyFeatureService:
    return request.app.state.my_service

MyServiceDep = Annotated[MyFeatureService, Depends(get_my_service)]
```

5. **Create router** in `app/api/endpoints/my_feature.py`:

```python
router = APIRouter()

@router.post("/my_feature/generate", response_model=MyFeatureResponse)
async def generate(request: MyFeatureRequest, service: MyServiceDep):
    return await service.generate(request)
```

6. **Register router** in `app/api/router.py`:

```python
from app.api.endpoints.my_feature import router as my_feature_router
api.include_router(my_feature_router, tags=["My Feature"])
```

---

### Dependency Management

This project uses [pip-tools](https://pip-tools.readthedocs.io/) for reproducible, pinned dependencies.

**Source files** (edit these):

| File | Contents |
|------|----------|
| `requirements.in` | Production dependencies |
| `requirements-dev.in` | Dev tools (black, mypy, etc.) |
| `requirements-test.in` | Test tools (pytest, coverage) |

**Compiled files** (auto-generated, **commit to git**):

| File | Generated from |
|------|----------------|
| `requirements.txt` | `requirements.in` |
| `requirements-dev.txt` | `requirements-dev.in` |
| `requirements-test.txt` | `requirements-test.in` |

**Adding a package:**

```bash
echo "httpx>=0.27" >> requirements.in
make compile-deps    # regenerates .txt files
make sync-deps       # installs into venv
```

**Upgrading a single package:**

```bash
pip-compile --upgrade-package httpx requirements.in
make sync-deps
```

---

### Testing

```bash
# Run all tests
make test

# With HTML coverage report (opens at htmlcov/index.html)
make test-with-coverage

# Run a specific test file
pytest tests/test_prompt_loader.py -v
```

**Test layout:**

```
tests/
├── conftest.py                    # Fixtures (PromptStore, mock services)
├── test_prompt_loader.py          # PromptStore rendering and registry
├── test_question_schemas.py       # Exam schema validation
└── test_fill_in_blank_schema.py   # Fill-in-blank question schemas
```

**Conventions:**

- Unit tests mock `LLMExecutor` — no real API calls during CI
- `conftest.py` provides a real `PromptStore` instance pointing at `app/prompts/`
- Integration tests that need a live database are skipped in CI via `pytest.mark.skip`

---

### Observability

The app ships with full LLM call tracing via **Arize Phoenix** (OpenTelemetry-based).

#### What is traced

- Every LangChain call (inputs, outputs, latency, token counts)
- RAG tool invocations (`search_documents` calls)
- Custom `X-Trace-ID` header propagation — pass a UUID from the upstream service; it appears in Phoenix spans for cross-service correlation

#### Accessing the Phoenix UI

With the dev stack running (`make docker-compose-up`), the Phoenix UI is at:

```
http://localhost:6006
```

Select project `aiprimary-tracing` (configurable via `PHOENIX_PROJECT_NAME`).

#### Custom Trace ID

Send `X-Trace-ID: <uuid>` in any request. The `TraceID` middleware (`app/middleware/trace_id.py`) converts it to a 128-bit hex OpenTelemetry trace ID and starts a root span, so upstream trace IDs appear in Phoenix exactly as sent.

---

## Web Test UI

A minimal HTML test client lives in `web_test_api/`. To use it:

```bash
cd web_test_api
python3 -m http.server 3000
# Open http://localhost:3000
```
