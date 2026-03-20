import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.cloud import aiplatform
from openinference.instrumentation.langchain import LangChainInstrumentor
from phoenix.otel import register

from app.api.router import api
from app.core.config import settings
from app.core.global_depends import Container
from app.llms.executor import LLMExecutor
from app.middleware.trace_id import injectCustomTraceId
from app.prompts.loader import PromptStore
from app.repositories.document_embeddings_repository import (
    DocumentEmbeddingsRepository,
)
from app.repositories.teacher_system_prompt_repository import (
    TeacherSystemPromptRepository,
)
from app.services.content_service import ContentService
from app.services.exam_rag_service import ExamRagService
from app.services.exam_service import ExamService
from app.services.mindmap_rag_service import MindmapRagService
from app.services.slide_rag_service import SlideRagService
from app.services.teacher_system_prompt_service import (
    TeacherSystemPromptService,
)

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):

    llm_tracer = register(
        project_name=settings.phoenix_project_name,
        endpoint=settings.phoenix_collector_endpoint,
        auto_instrument=False,  # Disabled to prevent duplicate spans
    )

    LangChainInstrumentor().instrument(tracer_provider=llm_tracer)

    prompt_store = PromptStore()
    llm_executor = LLMExecutor()
    content_service = ContentService(
        llm_executor=llm_executor,
        prompt_store=prompt_store,
    )
    exam_service = ExamService(
        llm_executor=llm_executor, prompt_store=prompt_store
    )

    # Initialize DI Container
    container = Container()
    container.config.from_dict(settings.model_dump())

    document_embeddings_repository = DocumentEmbeddingsRepository(
        pg_connection_string=settings.pg_connection_string,
        vertex_project_id=settings.project_id,
        vertex_location=settings.location,
        service_account_file=settings.service_account_json,
    )

    # Initialize specialized RAG services
    slide_rag_service = SlideRagService(
        llm_executor=llm_executor,
        prompt_store=prompt_store,
    )
    mindmap_rag_service = MindmapRagService(
        llm_executor=llm_executor,
        prompt_store=prompt_store,
    )
    exam_rag_service = ExamRagService(
        llm_executor=llm_executor,
        prompt_store=prompt_store,
    )

    teacher_prompt_repo = TeacherSystemPromptRepository(
        pg_connection_string=settings.pg_connection_string
    )
    teacher_prompt_service = TeacherSystemPromptService(
        repo=teacher_prompt_repo
    )

    app.state.settings = settings
    app.state.teacher_prompt_service = teacher_prompt_service
    app.state.content_service = content_service
    app.state.slide_rag_service = slide_rag_service
    app.state.mindmap_rag_service = mindmap_rag_service
    app.state.exam_rag_service = exam_rag_service
    app.state.exam_service = exam_service
    app.state.document_embeddings_repository = document_embeddings_repository
    app.state.container = container

    def init_vertexai():
        """Initialize Vertex AI settings."""
        import os

        from google.oauth2 import service_account

        # Skip initialization if service account file doesn't exist (for testing/mock mode)
        if not os.path.exists(settings.service_account_json):
            print(
                f"Warning: Service account file not found at {settings.service_account_json}"
            )
            print("Vertex AI initialization skipped - using mock mode")
            return

        service_account_info = json.load(open(settings.service_account_json))
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info
        )

        aiplatform.init(
            project=settings.project_id,
            location=settings.location,
            credentials=credentials,
        )

    init_vertexai()

    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        swagger_ui_parameters={"syntaxHighlight.theme": "obsidian"},
        lifespan=lifespan,
    )

    app.include_router(api, prefix="/api")

    # Add custom trace ID middleware (must be before CORS)
    app.middleware("http")(injectCustomTraceId)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=settings.allow_credentials,
        allow_methods=settings.allowed_methods,
        allow_headers=settings.allowed_headers,
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Catch-all exception handler for unexpected exceptions"""
        logger.exception("Unhandled exception")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": "Internal server error",
                "data": {},
            },
        )

    return app


app = create_app()
