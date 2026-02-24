import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.fastapi_depends import (
    ContentServiceDep,
    ExamRagServiceDep,
    ExamServiceDep,
    MindmapRagServiceDep,
    SlideRagServiceDep,
)
from app.schemas.exam_content import (
    ExamMatrix,
    GenerateMatrixRequest,
    GenerateQuestionsFromContextRequest,
    GenerateQuestionsFromTopicRequest,
    Question,
)
from app.schemas.image_content import (
    ImageGenerateRequest,
    ImageGenerateResponse,
)
from app.schemas.mindmap_content import MindmapGenerateRequest
from app.schemas.slide_content import (
    OutlineGenerateRequest,
    PresentationGenerateRequest,
)
from app.schemas.token_usage import TokenUsage
from app.services.base_rag_service import ContentMismatchError
from app.utils.server_sent_event import sse_json_by_json, sse_word_by_word

logger = logging.getLogger(__name__)


class GenerateResponse(BaseModel):
    """Generic response wrapper with token usage."""

    data: Any
    token_usage: TokenUsage | None = None


router = APIRouter(tags=["generate"])


@router.post("/outline/generate")
def generateOutline(
    outlineGenerateRequest: OutlineGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: SlideRagServiceDep,
):
    req = outlineGenerateRequest
    if req.grade is not None and req.subject is not None:
        try:
            result = svc_rag.make_outline_with_rag(req)
        except ContentMismatchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        token_usage = svc_rag.last_token_usage
    else:
        result = svc.make_outline(req)
        token_usage = svc.last_token_usage
    logger.info(
        f"[OUTLINE/GENERATE] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
    )
    return GenerateResponse(data=result, token_usage=token_usage)


@router.post("/outline/generate/stream")
def generateOutline_Stream(
    request: Request,
    outlineGenerateRequest: OutlineGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: SlideRagServiceDep,
):
    req = outlineGenerateRequest
    if req.grade is not None and req.subject is not None:
        try:
            chunks = svc_rag.make_outline_rag_stream(req)
        except ContentMismatchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return EventSourceResponse(
            sse_word_by_word(request, chunks), ping=None
        )
    else:
        chunks, token_usage = svc.make_outline_stream(req)
        logger.info(
            f"[OUTLINE/GENERATE/STREAM] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
        )
        print("Starting outline stream response")
        return EventSourceResponse(
            sse_word_by_word(request, chunks, token_usage), ping=None
        )


@router.post("/presentations/generate")
def generatePresentation(
    presentationGenerateRequest: PresentationGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: SlideRagServiceDep,
):
    req = presentationGenerateRequest
    if req.grade is not None and req.subject is not None:
        try:
            result = svc_rag.make_presentation_with_rag(req)
        except ContentMismatchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        token_usage = svc_rag.last_token_usage
    else:
        result = svc.make_presentation(req)
        token_usage = svc.last_token_usage
    logger.info(
        f"[PRESENTATIONS/GENERATE] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
    )
    return GenerateResponse(data=result, token_usage=token_usage)


@router.post("/presentations/generate/stream")
def generatePresentation_Stream(
    request: Request,
    presentationGenerateRequest: PresentationGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: SlideRagServiceDep,
):
    req = presentationGenerateRequest
    print("Received presentation stream request:", req)
    if req.grade is not None and req.subject is not None:
        try:
            chunks = svc_rag.make_presentation_rag_stream(req)
        except ContentMismatchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return EventSourceResponse(
            sse_json_by_json(request, chunks), ping=None
        )
    else:
        chunks, token_usage = svc.make_presentation_stream(req)
        logger.info(
            f"[PRESENTATIONS/GENERATE/STREAM] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
        )
        return EventSourceResponse(
            sse_json_by_json(request, chunks, token_usage), ping=None
        )


# Mock endpoints for testing without LLM calls
@router.post("/outline/generate/mock")
def generateOutline_Mock(
    svc: ContentServiceDep, outlineGenerateRequest: OutlineGenerateRequest
):
    print("Received mock outline request:", outlineGenerateRequest)
    result, token_usage = svc.make_outline_mock(outlineGenerateRequest)
    logger.info(
        f"[OUTLINE/GENERATE/MOCK] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
    )
    return GenerateResponse(data=result, token_usage=token_usage)


@router.post("/outline/generate/stream/mock")
async def generateOutline_Mock_Stream(
    request: Request,
    outlineGenerateRequest: OutlineGenerateRequest,
    svc: ContentServiceDep,
):
    print("Received mock outline stream request:", outlineGenerateRequest)
    chunks, token_usage = svc.make_outline_stream_mock()
    logger.info(
        f"[OUTLINE/GENERATE/STREAM/MOCK] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
    )

    async def event_stream():
        for chunk in chunks:
            if await request.is_disconnected():
                break
            yield {
                "data": base64.b64encode(chunk.encode("utf-8")).decode("ascii")
            }

    return EventSourceResponse(
        sse_word_by_word(request, chunks, token_usage),
        media_type="text/event-stream",
    )


@router.post("/presentations/generate/mock")
def generatePresentation_Mock(
    svc: ContentServiceDep,
    presentationGenerateRequest: PresentationGenerateRequest,
):
    print("Received mock presentation request:", presentationGenerateRequest)
    result, token_usage = svc.make_presentation_mock(
        presentationGenerateRequest
    )
    logger.info(
        f"[PRESENTATIONS/GENERATE/MOCK] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
    )
    return GenerateResponse(data=result, token_usage=token_usage)


@router.post("/presentations/generate/stream/mock")
async def generatePresentation_Mock_Stream(
    request: Request,
    presentationGenerateRequest: PresentationGenerateRequest,
    svc: ContentServiceDep,
):
    print(
        "Received mock presentation stream request:",
        presentationGenerateRequest,
    )

    slides, token_usage = await svc.make_presentation_stream_mock()
    logger.info(
        f"[PRESENTATIONS/GENERATE/STREAM/MOCK] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
    )

    # Convert slide dicts to JSON strings for sse_json_by_json
    slide_strings = [json.dumps(slide, ensure_ascii=False) for slide in slides]

    return EventSourceResponse(
        sse_json_by_json(request, slide_strings, token_usage),
        media_type="text/event-stream",
    )


@router.post("/image/generate", response_model=ImageGenerateResponse)
def generate_image(
    imageGenerateRequest: ImageGenerateRequest, svc: ContentServiceDep
):
    print("Received image generation request:", imageGenerateRequest)

    result = svc.generate_image(imageGenerateRequest)
    if "error" in result and result["error"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    logger.info(
        f"[IMAGE/GENERATE] Images generated: count={result['count']}, model={imageGenerateRequest.model} (token_usage not available for image generation)"
    )
    return {
        "images": result["images"],
        "count": result["count"],
        "error": None,
        "token_usage": None,
    }


@router.post("/image/generate/mock", response_model=ImageGenerateResponse)
def generate_image_mock(
    imageGenerateRequest: ImageGenerateRequest, svc: ContentServiceDep
):
    print("Received mock image generation request:", imageGenerateRequest)

    result = svc.generate_image_mock(imageGenerateRequest)
    if "error" in result and result["error"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["error"],
        )

    logger.info(
        f"[IMAGE/GENERATE/MOCK] Images generated: count={result['count']}, model={imageGenerateRequest.model} (token_usage not available for image generation)"
    )
    return {
        "images": result["images"],
        "count": result["count"],
        "error": None,
        "token_usage": None,
    }


@router.post("/mindmap/generate")
def generateMindmap(
    mindmapGenerateRequest: MindmapGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: MindmapRagServiceDep,
):
    req = mindmapGenerateRequest
    print("Received mindmap generation request:", req)
    if req.grade is not None and req.subject is not None:
        try:
            result = svc_rag.generate_mindmap_with_rag(req)
        except ContentMismatchError as e:
            raise HTTPException(status_code=400, detail=str(e))
        token_usage = svc_rag.last_token_usage
    else:
        result = svc.generate_mindmap(req)
        token_usage = svc.last_token_usage
    logger.info(
        f"[MINDMAP/GENERATE] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
    )
    return GenerateResponse(data=result, token_usage=token_usage)


@router.post("/mindmap/generate/mock")
def generateMindmap_Mock(
    svc: ContentServiceDep,
    mindmapGenerateRequest: MindmapGenerateRequest,
):
    print("Received mock mindmap generation request:", mindmapGenerateRequest)
    result, token_usage = svc.generate_mindmap_mock(mindmapGenerateRequest)
    return GenerateResponse(data=result, token_usage=token_usage)


@router.post("/questions/generate-from-context", response_model=list[Question])
def generate_questions_from_context(
    request: GenerateQuestionsFromContextRequest, svc: ExamServiceDep
):
    """
    Generate questions from a specific context (reading passage or image).
    """
    logger.info(
        f"[QUESTIONS/GENERATE-FROM-CONTEXT] Received request, context_type: {request.context_type}, grade: {request.grade}"
    )

    try:
        result = svc.generate_questions_from_context(request)
        logger.info(
            f"[QUESTIONS/GENERATE-FROM-CONTEXT] Successfully generated {len(result)} questions"
        )
        return result
    except ValueError as e:
        logger.error(
            f"[QUESTIONS/GENERATE-FROM-CONTEXT] Validation error: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except FileNotFoundError as e:
        logger.error(
            f"[QUESTIONS/GENERATE-FROM-CONTEXT] File not found: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt template not found: {str(e)}",
        )
    except Exception as e:
        logger.error(f"[QUESTIONS/GENERATE-FROM-CONTEXT] Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate questions: {str(e)}",
        )


@router.post("/questions/generate", response_model=list[Question])
def generate_questions(
    request: GenerateQuestionsFromTopicRequest,
    svc: ExamServiceDep,
    svc_rag: ExamRagServiceDep,
):
    """
    Generate questions based on topic and requirements.

    If grade and subject are provided, uses RAG-enhanced generation.
    Otherwise uses standard generation.
    """
    logger.info(
        f"[QUESTIONS/GENERATE] Received request for topic: {request.topic}, grade: {request.grade}"
    )

    if request.grade is not None and request.subject is not None:
        try:
            result = svc_rag.generate_questions_with_rag(request)
            token_usage = svc_rag.last_token_usage
            logger.info(
                f"[QUESTIONS/GENERATE] Successfully generated {len(result)} questions (RAG). "
                f"Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, "
                f"total={token_usage.total_tokens}, model={token_usage.model}"
            )
            return result
        except ContentMismatchError as e:
            logger.error(f"[QUESTIONS/GENERATE] Content mismatch: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        except ValueError as e:
            logger.error(f"[QUESTIONS/GENERATE] Validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )
        except FileNotFoundError as e:
            logger.error(f"[QUESTIONS/GENERATE] File not found: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Prompt template not found: {str(e)}",
            )
        except Exception as e:
            logger.error(f"[QUESTIONS/GENERATE] Error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate questions: {str(e)}",
            )
    else:
        try:
            result = svc.generate_questions_from_topic(request)
            logger.info(
                f"[QUESTIONS/GENERATE] Successfully generated {len(result)} questions"
            )
            return result
        except ValueError as e:
            logger.error(f"[QUESTIONS/GENERATE] Validation error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )
        except FileNotFoundError as e:
            logger.error(f"[QUESTIONS/GENERATE] File not found: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Prompt template not found: {str(e)}",
            )
        except Exception as e:
            logger.error(f"[QUESTIONS/GENERATE] Error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate questions: {str(e)}",
            )


@router.post("/exams/matrix/generate", response_model=ExamMatrix)
def generate_exam_matrix(
    request: GenerateMatrixRequest, svc: ExamRagServiceDep
):
    """
    Generate a 3D exam matrix based on topics and prerequisites using RAG.
    """
    logger.info(
        f"[EXAM/MATRIX/GENERATE] Received request for matrix: {request.name}"
    )

    try:
        result = svc.generate_matrix_with_rag(request)
        token_usage = svc.last_token_usage
        logger.info(
            f"[EXAM/MATRIX/GENERATE] Successfully generated matrix. "
            f"Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, "
            f"total={token_usage.total_tokens}, model={token_usage.model}"
        )
        return result
    except ContentMismatchError as e:
        logger.error(f"[EXAM/MATRIX/GENERATE] Content mismatch: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        logger.error(f"[EXAM/MATRIX/GENERATE] Validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[EXAM/MATRIX/GENERATE] Error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate matrix: {str(e)}",
        )
