import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.core.fastapi_depends import (
    ContentServiceDep,
    ExamRagServiceDep,
    ExamServiceDep,
    MindmapRagServiceDep,
    SlideRagServiceDep,
    TeacherSystemPromptServiceDep,
)
from app.schemas.exam_content import (
    ExamMatrix,
    GenerateMatrixRequest,
    GenerateQuestionsByTopicRequest,
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
from app.schemas.slide_generation import GenerateSlidesRequest
from app.schemas.token_usage import TokenUsage
from app.services.base_rag_service import ContentMismatchError
from app.utils.server_sent_event import sse_json_by_json, sse_word_by_word
from app.utils.teacher_context import (
    _teacher_system_prompt,
    set_teacher_prompt,
)

logger = logging.getLogger(__name__)


class GenerateResponse(BaseModel):
    """Generic response wrapper with token usage."""

    data: Any
    token_usage: TokenUsage | None = None


router = APIRouter(tags=["generate"])


@router.post("/outline/generate")
def generateOutline(
    http_request: Request,
    outlineGenerateRequest: OutlineGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: SlideRagServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        req = outlineGenerateRequest
        if (
            req.grade is not None
            and req.subject is not None
            and not req.file_urls
        ):
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
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/outline/generate/stream")
def generateOutline_Stream(
    request: Request,
    outlineGenerateRequest: OutlineGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: SlideRagServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    teacher_id = request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        req = outlineGenerateRequest
        if (
            req.grade is not None
            and req.subject is not None
            and not req.file_urls
        ):
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
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/presentations/generate")
def generatePresentation(
    http_request: Request,
    presentationGenerateRequest: PresentationGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: SlideRagServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        req = presentationGenerateRequest
        if (
            req.grade is not None
            and req.subject is not None
            and not req.file_urls
        ):
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
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/presentations/generate/stream")
def generatePresentation_Stream(
    request: Request,
    presentationGenerateRequest: PresentationGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: SlideRagServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    teacher_id = request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        req = presentationGenerateRequest
        print("Received presentation stream request:", req)
        if (
            req.grade is not None
            and req.subject is not None
            and not req.file_urls
        ):
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
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/slides/generate")
def generate_slides(
    request: GenerateSlidesRequest,
    svc: ContentServiceDep,
):
    """Generate slides for insertion into an existing presentation (batch mode)."""
    logger.info(
        f"[SLIDES/GENERATE] Generating {request.slide_count} slides, "
        f"model={request.model}, provider={request.provider}"
    )

    result = svc.generate_slides(request)
    token_usage = svc.last_token_usage
    logger.info(
        f"[SLIDES/GENERATE] Token Usage: input={token_usage.input_tokens}, "
        f"output={token_usage.output_tokens}, total={token_usage.total_tokens}, "
        f"model={token_usage.model}"
    )

    # Parse JSON array of slide schemas
    schemas = []
    raw = result.strip()
    # Remove markdown code fences if present
    if raw.startswith("```"):
        first_newline = raw.index("\n") if "\n" in raw else len(raw)
        raw = raw[first_newline + 1 :]
    if raw.endswith("```"):
        raw = raw[: raw.rfind("```")].strip()

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            schemas = parsed
        elif isinstance(parsed, dict):
            schemas = [parsed]
        else:
            logger.warning(
                f"[SLIDES/GENERATE] Unexpected JSON type: {type(parsed)}"
            )
    except json.JSONDecodeError:
        logger.warning(
            f"[SLIDES/GENERATE] Failed to parse response as JSON: {raw[:200]}"
        )

    return GenerateResponse(data={"schemas": schemas}, token_usage=token_usage)


# Mock endpoints for testing without LLM calls
@router.post("/outline/generate/mock")
def generateOutline_Mock(
    http_request: Request,
    svc: ContentServiceDep,
    outlineGenerateRequest: OutlineGenerateRequest,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    print("Received mock outline request:", outlineGenerateRequest)
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        result, token_usage = svc.make_outline_mock(outlineGenerateRequest)
        logger.info(
            f"[OUTLINE/GENERATE/MOCK] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
        )
        return GenerateResponse(data=result, token_usage=token_usage)
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/outline/generate/stream/mock")
async def generateOutline_Mock_Stream(
    request: Request,
    outlineGenerateRequest: OutlineGenerateRequest,
    svc: ContentServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    print("Received mock outline stream request:", outlineGenerateRequest)
    teacher_id = request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        chunks, token_usage = svc.make_outline_stream_mock()
        logger.info(
            f"[OUTLINE/GENERATE/STREAM/MOCK] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
        )

        async def event_stream():
            for chunk in chunks:
                if await request.is_disconnected():
                    break
                yield {
                    "data": base64.b64encode(chunk.encode("utf-8")).decode(
                        "ascii"
                    )
                }

        return EventSourceResponse(
            sse_word_by_word(request, chunks, token_usage),
            media_type="text/event-stream",
        )
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/presentations/generate/mock")
def generatePresentation_Mock(
    http_request: Request,
    svc: ContentServiceDep,
    presentationGenerateRequest: PresentationGenerateRequest,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    print("Received mock presentation request:", presentationGenerateRequest)
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        result, token_usage = svc.make_presentation_mock(
            presentationGenerateRequest
        )
        logger.info(
            f"[PRESENTATIONS/GENERATE/MOCK] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
        )
        return GenerateResponse(data=result, token_usage=token_usage)
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/presentations/generate/stream/mock")
async def generatePresentation_Mock_Stream(
    request: Request,
    presentationGenerateRequest: PresentationGenerateRequest,
    svc: ContentServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    print(
        "Received mock presentation stream request:",
        presentationGenerateRequest,
    )
    teacher_id = request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        slides, token_usage = await svc.make_presentation_stream_mock()
        logger.info(
            f"[PRESENTATIONS/GENERATE/STREAM/MOCK] Token Usage: input={token_usage.input_tokens}, output={token_usage.output_tokens}, total={token_usage.total_tokens}, model={token_usage.model}"
        )

        # Convert slide dicts to JSON strings for sse_json_by_json
        slide_strings = [
            json.dumps(slide, ensure_ascii=False) for slide in slides
        ]

        return EventSourceResponse(
            sse_json_by_json(request, slide_strings, token_usage),
            media_type="text/event-stream",
        )
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/image/generate", response_model=ImageGenerateResponse)
def generate_image(
    imageGenerateRequest: ImageGenerateRequest,
    svc: ContentServiceDep,
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
    imageGenerateRequest: ImageGenerateRequest,
    svc: ContentServiceDep,
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
    http_request: Request,
    mindmapGenerateRequest: MindmapGenerateRequest,
    svc: ContentServiceDep,
    svc_rag: MindmapRagServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        req = mindmapGenerateRequest
        print("Received mindmap generation request:", req)
        if (
            req.grade is not None
            and req.subject is not None
            and not req.file_urls
        ):
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
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/mindmap/generate/mock")
def generateMindmap_Mock(
    http_request: Request,
    svc: ContentServiceDep,
    mindmapGenerateRequest: MindmapGenerateRequest,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    print("Received mock mindmap generation request:", mindmapGenerateRequest)
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        result, token_usage = svc.generate_mindmap_mock(mindmapGenerateRequest)
        return GenerateResponse(data=result, token_usage=token_usage)
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/questions/generate-from-context", response_model=list[Question])
def generate_questions_from_context(
    http_request: Request,
    request: GenerateQuestionsFromContextRequest,
    svc: ExamServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    """
    Generate questions from a specific context (reading passage or image).
    """
    logger.info(
        f"[QUESTIONS/GENERATE-FROM-CONTEXT] Received request, context_type: {request.context_type}, grade: {request.grade}"
    )
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
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
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/questions/generate", response_model=list[Question])
def generate_questions(
    http_request: Request,
    request: GenerateQuestionsFromTopicRequest,
    svc: ExamServiceDep,
    svc_rag: ExamRagServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    """
    Generate questions based on topic and requirements.

    If grade and subject are provided, uses RAG-enhanced generation.
    Otherwise uses standard generation.
    """
    logger.info(
        f"[QUESTIONS/GENERATE] Received request for topic: {request.topic}, grade: {request.grade}"
    )
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
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
                logger.error(
                    f"[QUESTIONS/GENERATE] Content mismatch: {str(e)}"
                )
                raise HTTPException(status_code=400, detail=str(e))
            except ValueError as e:
                logger.error(
                    f"[QUESTIONS/GENERATE] Validation error: {str(e)}"
                )
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
                logger.error(
                    f"[QUESTIONS/GENERATE] Error: {str(e)}", exc_info=True
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to generate questions: {str(e)}",
                )
        else:
            if request.grade is None or request.subject is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="grade and subject are required for question generation",
                )
            try:
                result = svc.generate_questions_from_topic(request)
                logger.info(
                    f"[QUESTIONS/GENERATE] Successfully generated {len(result)} questions"
                )
                return result
            except ValueError as e:
                logger.error(
                    f"[QUESTIONS/GENERATE] Validation error: {str(e)}"
                )
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
                logger.error(
                    f"[QUESTIONS/GENERATE] Error: {str(e)}", exc_info=True
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to generate questions: {str(e)}",
                )
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/questions/generate-by-topic", response_class=JSONResponse)
def generate_questions_by_topic(
    http_request: Request,
    request: GenerateQuestionsByTopicRequest,
    svc: ExamRagServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    """
    Generate questions for a single topic from the assignment matrix.

    CONTEXT groups use the provided reading passage directly.
    NORMAL groups use RAG to retrieve curriculum materials (if available).
    Uses JSON mode — returns raw JSON array, no markdown wrapping.

    Each question in the response has a `group` field (0-based index) that the
    backend uses to assign contextId to context-based questions.
    """
    logger.info(
        f"[QUESTIONS/GENERATE-BY-TOPIC] topic: {request.topic_name}, "
        f"grade: {request.grade}, groups: {len(request.groups)}"
    )
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
    try:
        raw_json = svc.generate_questions_by_topic(request)
        parsed = json.loads(raw_json)
        logger.info(
            f"[QUESTIONS/GENERATE-BY-TOPIC] Generated {len(parsed) if isinstance(parsed, list) else '?'} questions"
        )
        return JSONResponse(content=parsed)
    except ValueError as e:
        logger.error(
            f"[QUESTIONS/GENERATE-BY-TOPIC] Validation error: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    except Exception as e:
        logger.error(f"[QUESTIONS/GENERATE-BY-TOPIC] Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate questions: {str(e)}",
        )
    finally:
        _teacher_system_prompt.reset(token)


@router.post("/exams/matrix/generate", response_model=ExamMatrix)
def generate_exam_matrix(
    http_request: Request,
    request: GenerateMatrixRequest,
    svc: ExamRagServiceDep,
    teacher_svc: TeacherSystemPromptServiceDep,
):
    """
    Generate a 3D exam matrix based on topics and prerequisites using RAG.
    """
    logger.info(
        f"[EXAM/MATRIX/GENERATE] Received request for matrix: {request.name}"
    )
    teacher_id = http_request.headers.get("X-User-ID")
    token = set_teacher_prompt(teacher_svc.get_prompt(teacher_id))
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
    finally:
        _teacher_system_prompt.reset(token)
