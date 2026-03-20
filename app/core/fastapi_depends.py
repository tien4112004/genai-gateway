from typing import Annotated

from fastapi import Depends, Request

from app.core.config import settings
from app.repositories.document_embeddings_repository import (
    DocumentEmbeddingsRepository,
)
from app.services.content_service import ContentService
from app.services.exam_rag_service import ExamRagService
from app.services.exam_service import ExamService
from app.services.mindmap_rag_service import MindmapRagService
from app.services.slide_rag_service import SlideRagService
from app.services.teacher_system_prompt_service import (
    TeacherSystemPromptService,
)


def get_logger():
    return settings.logger


def get_content_service(request: Request) -> ContentService:
    """Get the content service with the default model."""
    return request.app.state.content_service


def get_exam_service(request: Request) -> ExamService:
    """Get the exam service."""
    return request.app.state.exam_service


def get_doc_repository(request: Request):
    """Get the document embeddings repository."""
    return request.app.state.document_embeddings_repository


def get_slide_rag_service(request: Request) -> SlideRagService:
    """Get the slide rag service."""
    return request.app.state.slide_rag_service


def get_mindmap_rag_service(request: Request) -> MindmapRagService:
    """Get the mindmap rag service."""
    return request.app.state.mindmap_rag_service


def get_exam_rag_service(request: Request) -> ExamRagService:
    """Get the exam rag service."""
    return request.app.state.exam_rag_service


def get_teacher_prompt_service(request: Request) -> TeacherSystemPromptService:
    """Get the teacher system prompt service."""
    return request.app.state.teacher_prompt_service


ExamServiceDep = Annotated[ExamService, Depends(get_exam_service)]
TeacherSystemPromptServiceDep = Annotated[
    TeacherSystemPromptService, Depends(get_teacher_prompt_service)
]

ContentServiceDep = Annotated[ContentService, Depends(get_content_service)]
DocumentEmbeddingsRepositoryDep = Annotated[
    DocumentEmbeddingsRepository, Depends(get_doc_repository)
]

# Specialized RAG service dependencies
SlideRagServiceDep = Annotated[SlideRagService, Depends(get_slide_rag_service)]
MindmapRagServiceDep = Annotated[
    MindmapRagService, Depends(get_mindmap_rag_service)
]
ExamRagServiceDep = Annotated[ExamRagService, Depends(get_exam_rag_service)]
