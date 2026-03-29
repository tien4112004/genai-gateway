import base64
import logging
import os
import random
from asyncio import sleep
from typing import Any, Dict, Generator, List, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from app.llms.executor import LLMExecutor
from app.prompts.loader import PromptStore
from app.schemas.image_content import ImageGenerateRequest
from app.schemas.mindmap_content import MindmapGenerateRequest
from app.schemas.slide_content import (
    OutlineGenerateRequest,
    PresentationGenerateRequest,
)
from app.schemas.slide_generation import GenerateSlidesRequest
from app.schemas.token_usage import TokenUsage
from app.utils.audience_context import get_audience_context
from app.utils.teacher_context import build_system_with_teacher_prompt

logger = logging.getLogger(__name__)


class ContentService:
    def __init__(self, llm_executor: LLMExecutor, prompt_store: PromptStore):
        self.llm_executor = llm_executor or LLMExecutor()
        self.prompt_store = prompt_store or PromptStore()
        self.last_token_usage = None

    def _system(self, key: str, vars: Dict[str, Any] | None) -> str:
        base = self.prompt_store.render(key, vars)
        return build_system_with_teacher_prompt(base)

    def _build_messages_with_files(
        self, sys_msg: str, usr_msg: str, file_urls: List[str], provider: str
    ) -> List:
        """Build LangChain messages injecting uploaded file content."""
        from app.utils.file_extractor import extract_from_urls

        logger.info(
            f"[FILE-GEN] Building messages with {len(file_urls)} file(s), provider={provider}"
        )
        for url in file_urls:
            logger.info(f"[FILE-GEN] File URL: {url}")

        file_contents = extract_from_urls(file_urls)

        file_preamble = (
            "The user has provided one or more files as the primary content source. "
            "Base your response on the content of the attached file(s). "
            "If no topic is explicitly specified, derive the topic directly from the file content.\n\n"
        )
        content_parts = [{"type": "text", "text": file_preamble + usr_msg}]

        for i, fc in enumerate(file_contents):
            if fc.file_type == "image":
                # Image: send as vision content part (works for Gemini + OpenAI)
                b64 = base64.b64encode(fc.raw_bytes).decode()
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{fc.mime_type};base64,{b64}"
                        },
                    }
                )
                logger.info(
                    f"[FILE-GEN] File[{i}] → image part mime={fc.mime_type} ({len(fc.raw_bytes)} bytes)"
                )
            elif fc.file_type == "pdf" and provider == "google":
                # Gemini native PDF: handles scanned + digital PDFs
                b64 = base64.b64encode(fc.raw_bytes).decode()
                content_parts.append(
                    {
                        "type": "media",
                        "mime_type": "application/pdf",
                        "data": b64,
                    }
                )
                logger.info(
                    f"[FILE-GEN] File[{i}] → multimodal PDF part ({len(fc.raw_bytes)} bytes) sent to Gemini"
                )
            else:
                # Text fallback for DOCX/TXT, or non-Gemini providers with PDF
                if fc.extracted_text.strip():
                    content_parts[0]["text"] += (
                        "\n\n---\nREFERENCE DOCUMENT:\n" + fc.extracted_text
                    )
                    logger.info(
                        f"[FILE-GEN] File[{i}] type={fc.file_type} → text injection ({len(fc.extracted_text)} chars)"
                    )
                else:
                    logger.warning(
                        f"[FILE-GEN] File[{i}] type={fc.file_type} → no text extracted, skipped"
                    )

        logger.info(
            f"[FILE-GEN] Final message has {len(content_parts)} content part(s) "
            f"(1 text + {len(content_parts) - 1} file part(s))"
        )

        return [
            SystemMessage(content=sys_msg),
            HumanMessage(content=content_parts),
        ]

    # Presentation Generation
    def make_presentation_stream(self, request: PresentationGenerateRequest):
        """Generate slide content using LLM and save result.
        Args:
            request (PresentationGenerateRequest): Request object containing parameters for slide generation.
        Returns:
            Tuple: (chunks, token_usage) - list of content chunks and token usage data.
        """
        sys_msg = self._system(
            "presentation.system",
            {
                "audience_context": get_audience_context(
                    request.subject, request.grade
                )
            },
        )

        usr_msg = self._system(
            "presentation.user",
            request.to_dict(),
        )

        if request.file_urls:
            messages = self._build_messages_with_files(
                sys_msg, usr_msg, request.file_urls, request.provider
            )
        else:
            messages = [
                SystemMessage(content=sys_msg),
                HumanMessage(content=usr_msg),
            ]

        chunks, token_usage = self.llm_executor.stream(
            provider=request.provider,
            model=request.model,
            messages=messages,
        )

        # Filter out token_usage objects (only check last chunk for efficiency)
        import json

        filtered_chunks = chunks[:-1] if chunks else []

        # Only parse the last chunk if it exists
        if chunks:
            last_chunk = chunks[-1]
            if not (
                last_chunk.startswith('{"token_usage"')
                or last_chunk.startswith('{"type":"token_usage"')
            ):
                filtered_chunks.append(last_chunk)

        # Store token usage for later access
        self.last_token_usage = token_usage
        return filtered_chunks, token_usage

    def make_presentation(self, request: PresentationGenerateRequest):
        """
        Generate slide content using LLM and save result.
        Args:
            request (PresentationGenerateRequest): Request object containing parameters for slide generation.
        Returns:
            Dict: A dictionary containing the generated slide content.
        """
        sys_msg = self._system(
            "presentation.system",
            {
                "audience_context": get_audience_context(
                    request.subject, request.grade
                )
            },
        )

        usr_msg = self._system(
            "presentation.user",
            request.to_dict(),
        )

        if request.file_urls:
            messages = self._build_messages_with_files(
                sys_msg, usr_msg, request.file_urls, request.provider
            )
        else:
            messages = [
                SystemMessage(content=sys_msg),
                HumanMessage(content=usr_msg),
            ]

        result, token_usage = self.llm_executor.batch(
            provider=request.provider,
            model=request.model,
            messages=messages,
        )

        # Store token usage for later access
        self.last_token_usage = token_usage
        return result

    # Slide Generation (in-editor, batch mode)
    def generate_slides(self, request: GenerateSlidesRequest) -> str:
        """Generate a small set of slides for insertion into an existing presentation.

        Uses batch mode (not streaming) - returns all slides at once as NDJSON.
        """
        sys_msg = self._system(
            "slide_generation.system",
            None,
        )

        usr_msg = self._system(
            "slide_generation.user",
            request.to_dict(),
        )

        messages = [
            SystemMessage(content=sys_msg),
            HumanMessage(content=usr_msg),
        ]

        result, token_usage = self.llm_executor.batch(
            provider=request.provider,
            model=request.model,
            messages=messages,
        )

        self.last_token_usage = token_usage
        return result

    # Outline Generation
    def make_outline_stream(self, request: OutlineGenerateRequest):
        """Generate outline using LLM and save result.
        Args:
            request (OutlineGenerateRequest): Request object containing parameters for outline generation.
        Returns:
            Tuple: (chunks, token_usage) - list of content chunks and token usage data.
        """
        sys_msg = self._system(
            "outline.system",
            {
                "audience_context": get_audience_context(
                    request.subject, request.grade
                )
            },
        )

        usr_msg = self._system(
            "outline.user",
            request.to_dict(),
        )

        if request.file_urls:
            messages = self._build_messages_with_files(
                sys_msg, usr_msg, request.file_urls, request.provider
            )
        else:
            messages = [
                SystemMessage(content=sys_msg),
                HumanMessage(content=usr_msg),
            ]

        chunks, token_usage = self.llm_executor.stream(
            provider=request.provider,
            model=request.model,
            messages=messages,
        )

        # Store token usage for later access
        self.last_token_usage = token_usage
        return chunks, token_usage

    def make_outline(self, request: OutlineGenerateRequest):
        """Generate outline using LLM and save result.
        Args:
            request (OutlineGenerateRequest): Request object containing parameters for outline generation.
        Returns:
            Dict: A dictionary containing the generated outline.
        """
        sys_msg = self._system(
            "outline.system",
            {
                "audience_context": get_audience_context(
                    request.subject, request.grade
                )
            },
        )

        usr_msg = self._system(
            "outline.user",
            request.to_dict(),
        )

        if request.file_urls:
            messages = self._build_messages_with_files(
                sys_msg, usr_msg, request.file_urls, request.provider
            )
        else:
            messages = [
                SystemMessage(content=sys_msg),
                HumanMessage(content=usr_msg),
            ]

        result, token_usage = self.llm_executor.batch(
            provider=request.provider,
            model=request.model,
            messages=messages,
        )

        # Store token usage for later access
        self.last_token_usage = token_usage
        return result

    def make_presentation_mock(
        self, request: PresentationGenerateRequest
    ) -> Tuple[str, TokenUsage]:
        """Generate mock slide content for testing purposes.
        Returns:
            Tuple: (result, token_usage) - mock slide content and zero token usage.
        """

        sys_msg = self._system(
            "presentation.system",
            request.to_dict(),
        )
        print("System Prompt:", sys_msg)  # Debug print

        result = '```json\n{\n  "slides": [\n    {\n      "type": "main_image",\n      "data": {\n        "image": "Children looking excitedly at an old map of Vietnam with a river highlighted",\n        "content": "Giới thiệu: Một Cuộc Phiêu Lưu Lịch Sử Về Sông Bạch Đằng!"\n      }\n    },\n    {\n      "type": "two_column_with_image",\n      "title": "Ai Đã Xâm Lược Nước Ta?",\n      "data": {\n        "items": [\n          "Quân địch đến từ nước Nam Hán.",\n          "Họ muốn chiếm đất nước ta.",\n          "Nhân dân ta không muốn bị mất nước."\n        ],\n        "image": "Illustration of ancient Chinese warships sailing towards Vietnamese shores"\n      }\n    },\n    {\n      "type": "two_column_with_image",\n      "title": "\\"Bẫy\\" Trên Sông: Ý Tưởng Của Ngô Quyền!",\n      "data": {\n        "items": [\n          "Ngô Quyền cho cắm cọc nhọn dưới sông.",\n          "Cọc ẩn dưới nước lúc triều lên.",\n          "Nhô lên đâm thủng thuyền địch khi nước rút."\n        ],\n        "image": "Illustration of a wooden stake hidden underwater in a river with a boat approaching"\n      }\n    },\n    {\n      "type": "two_column_with_image",\n      "title": "Trận Chiến Rực Lửa Trên Sông!",\n      "data": {\n        "items": [\n          "Thuyền địch mắc bẫy, bị đâm thủng.",\n          "Quân ta tấn công từ hai bên bờ.",\n          "Chiến thắng vang dội cho dân tộc!"\n        ],\n        "image": "Illustration of Vietnamese soldiers attacking enemy ships from the riverbanks during a battle"\n      }\n    },\n    {\n      "type": "main_image",\n      "data": {\n        "image": "Illustration of a proud Vietnamese flag waving over a peaceful landscape",\n        "content": "Chiến thắng Bạch Đằng giúp đất nước ta mãi mãi tự do!"\n      }\n    }\n  ]\n}\n```'

        # Create zero token usage for mock
        mock_usage = TokenUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            model="mock",
            provider="mock",
        )
        self.last_token_usage = mock_usage

        return result, mock_usage

    def generate_image(self, request: ImageGenerateRequest):
        """Generate image based on text description"""

        usr_msg = self.prompt_store.render(
            "image.user", {"prompt": request.prompt}
        )

        result = self.llm_executor.generate_image(
            provider=request.provider,
            model=request.model,
            message=usr_msg,
            number_of_images=request.number_of_images,
            aspect_ratio=request.aspect_ratio,
            safety_filter_level=request.safety_filter_level,
            person_generation=request.person_generation,
            seed=request.seed,
            negative_prompt=request.negative_prompt,
        )
        return result

    def generate_image_mock(self, request: ImageGenerateRequest):
        """Generate mock image data for testing purposes."""
        sleep(random.uniform(0.3, 1.5))  # Simulate some processing delay
        with open("app/services/image_mock.png", "rb") as f:
            mock_image_data = base64.b64encode(f.read()).decode("utf-8")

        images = [mock_image_data for _ in range(request.number_of_images)]
        return {
            "images": images,
            "count": request.number_of_images,
            "error": None,
        }

    def generate_mindmap(self, request: MindmapGenerateRequest):
        mindmap_vars = {
            **request.to_dict(),
            "audience_context": get_audience_context(
                request.subject, request.grade
            ),
        }
        sys_msg = self._system(
            "mindmap.system",
            mindmap_vars,
        )

        usr_msg = self._system(
            "mindmap.user",
            request.to_dict(),
        )

        if request.file_urls:
            messages = self._build_messages_with_files(
                sys_msg, usr_msg, request.file_urls, request.provider
            )
        else:
            messages = [
                SystemMessage(content=sys_msg),
                HumanMessage(content=usr_msg),
            ]

        result, token_usage = self.llm_executor.batch(
            provider=request.provider,
            model=request.model,
            messages=messages,
        )

        # Store token usage for later access
        self.last_token_usage = token_usage
        return result

    # ============ RAG ============
    def make_outline_with_rag(self, request: OutlineGenerateRequest):
        """Generate outline using LLM and save result.
        Args:
            request (OutlineGenerateRequest): Request object containing parameters for outline generation.
        Returns:
            Dict: A dictionary containing the generated outline.
        """
        sys_msg = self._system(
            "outline.system.rag",
            None,
        )

        usr_msg = self._system(
            "outline.user",
            request.to_dict(),
        )

        # Build filters for document search
        # Note: Use subject_code (e.g., 'TV', 'T', 'TA') instead of subject name
        filters = {}
        if request.subject:
            filters["subject_code"] = request.subject
        if request.grade:
            # Convert grade to integer if it's numeric (metadata stores it as int)
            try:
                filters["grade"] = int(request.grade)
            except (ValueError, TypeError):
                filters["grade"] = request.grade

        print(f"[DEBUG] RAG filters being applied: {filters}")
        print(
            f"[DEBUG] Request - subject: {request.subject}, grade: {request.grade} (type: {type(request.grade).__name__})"
        )

        result, token_usage = self.llm_executor.rag_batch(
            provider=request.provider,
            model=request.model,
            query=usr_msg,
            system_prompt=sys_msg,
            return_source_documents=True,
            filters=filters if filters else None,
            custom_prompt=None,
            verbose=False,
        )

        # Store token usage for later access
        self.last_token_usage = token_usage
        return result

    def make_presentation_with_rag(self, request: PresentationGenerateRequest):
        sys_msg = self._system(
            "presentation.system.rag",
            None,
        )

        usr_msg = self._system(
            "presentation.user",
            request.to_dict(),
        )

        filters = {}
        if request.subject:
            filters["subject_code"] = request.subject
        if request.grade:
            try:
                filters["grade"] = int(request.grade)
            except (ValueError, TypeError):
                filters["grade"] = request.grade

        print(f"[DEBUG] RAG filters being applied: {filters}")
        print(
            f"[DEBUG] Request - subject: {request.subject}, grade: {request.grade} (type: {type(request.grade).__name__})"
        )

        result, token_usage = self.llm_executor.rag_batch(
            provider=request.provider,
            model=request.model,
            query=usr_msg,
            system_prompt=sys_msg,
            return_source_documents=True,
            filters=filters if filters else None,
            custom_prompt=None,
            verbose=False,
        )

        self.last_token_usage = token_usage
        return result

    def generate_mindmap_with_rag(self, request: MindmapGenerateRequest):
        sys_msg = self._system(
            "mindmap.system.rag",
            None,
        )

        usr_msg = self._system(
            "mindmap.user",
            request.to_dict(),
        )

        filters = {}
        if request.subject:
            filters["subject_code"] = request.subject
        if request.grade:
            try:
                filters["grade"] = int(request.grade)
            except (ValueError, TypeError):
                filters["grade"] = request.grade

        print(f"[DEBUG] RAG filters being applied: {filters}")
        print(
            f"[DEBUG] Request - subject: {request.subject}, grade: {request.grade} (type: {type(request.grade).__name__})"
        )

        result, token_usage = self.llm_executor.rag_batch(
            provider=request.provider,
            model=request.model,
            query=usr_msg,
            system_prompt=sys_msg,
            return_source_documents=True,
            filters=filters if filters else None,
            custom_prompt=None,
            verbose=False,
        )

        self.last_token_usage = token_usage
        return result

    # ============ RAG Stream ============
    def make_outline_rag_stream(
        self, request: OutlineGenerateRequest
    ) -> Tuple[List[str], TokenUsage]:
        result = self.make_outline_with_rag(request)
        return [result["answer"]], self.last_token_usage

    def make_presentation_rag_stream(
        self, request: PresentationGenerateRequest
    ) -> Tuple[List[str], TokenUsage]:
        result = self.make_presentation_with_rag(request)
        return [result["answer"]], self.last_token_usage

    def generate_mindmap_rag_stream(
        self, request: MindmapGenerateRequest
    ) -> Tuple[List[str], TokenUsage]:
        result = self.generate_mindmap_with_rag(request)
        return [result["answer"]], self.last_token_usage
