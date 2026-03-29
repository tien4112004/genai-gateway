from typing import Any, Dict, Generator

from app.llms.executor import LLMExecutor
from app.prompts.loader import PromptStore
from app.prompts.subject_prompt_router import get_subject_grade_prompt_key
from app.schemas.token_usage import TokenUsage
from app.utils.audience_context import get_audience_context
from app.utils.teacher_context import build_system_with_teacher_prompt


class ContentMismatchError(Exception):
    """Raised when retrieved documents do not match the requested topic/subject/grade."""

    pass


class BaseRagService:
    """Base service for RAG operations with shared functionality.

    Provides common methods for prompt rendering, content validation,
    filter construction, and streaming operations used across all RAG services.
    """

    def __init__(self, llm_executor: LLMExecutor, prompt_store: PromptStore):
        self.llm_executor = llm_executor or LLMExecutor()
        self.prompt_store = prompt_store or PromptStore()
        self.last_token_usage = None

    def _system(self, key: str, vars: Dict[str, Any] | None) -> str:
        """Render a system prompt template.

        Args:
            key: The prompt key to render
            vars: Variables for template substitution

        Returns:
            Rendered prompt string
        """
        base = self.prompt_store.render(key, vars)
        return build_system_with_teacher_prompt(base)

    def _system_with_subject_grade(
        self,
        key: str,
        vars: Dict[str, Any] | None,
        subject_code: str | None,
        grade: str | None,
    ) -> str:
        """Render system prompt with subject-grade specific prompt injected via placeholder.

        Args:
            key: The base prompt key to render
            vars: Variables for template substitution
            subject_code: Optional subject code (e.g., 'T', 'TV', 'TA')
            grade: Optional grade level (e.g., '1', '2', '3', '4', '5')

        Returns:
            System prompt with subject-grade prompt injected if applicable
        """
        # Initialize vars dict if None
        if vars is None:
            vars = {}
        else:
            # Make a copy to avoid mutating the input
            vars = vars.copy()

        # Get subject-grade prompt if both subject and grade are provided
        subject_grade_prompt = ""
        subject_grade_key = get_subject_grade_prompt_key(subject_code, grade)
        if subject_grade_key:
            try:
                subject_grade_prompt = self.prompt_store.render(
                    subject_grade_key, None
                )
            except KeyError:
                print(
                    f"[WARNING] Subject-grade prompt key '{subject_grade_key}' not found in registry"
                )

        # Inject audience context and subject-grade prompt into the template variables
        vars["audience_context"] = get_audience_context(subject_code, grade)
        vars["subject_grade_prompt"] = subject_grade_prompt

        # Render the base template with the injected subject-grade prompt
        result = self.prompt_store.render(key, vars)
        return build_system_with_teacher_prompt(result)

    @staticmethod
    def _check_content_mismatch(result: dict) -> None:
        """Check if RAG result indicates a content mismatch.

        Args:
            result: Dictionary containing the RAG result with 'answer' key

        Raises:
            ContentMismatchError: If the result indicates content mismatch
        """
        answer = result.get("answer", "")
        if isinstance(answer, str):
            answer = answer.strip()
            if answer.startswith("CONTENT_MISMATCH:"):
                message = answer[len("CONTENT_MISMATCH:") :].strip()
                raise ContentMismatchError(message)

    def _checked_rag_stream(
        self,
        provider: str,
        model: str,
        query: str,
        system_prompt: str,
        filters,
    ) -> Generator:
        """Start a RAG stream with eager CONTENT_MISMATCH detection.

        Prefetches enough of the stream to check for CONTENT_MISMATCH before
        any chunks are yielded, so the caller can still raise an HTTP 400
        before the SSE response begins. Returns a generator that replays the
        prefetched chunks then continues with the rest of the stream.

        Args:
            provider: LLM provider name
            model: Model name
            query: User query/prompt
            system_prompt: System prompt
            filters: Metadata filters for document search

        Returns:
            Generator yielding stream chunks and final TokenUsage

        Raises:
            ContentMismatchError: If CONTENT_MISMATCH detected in early chunks
        """
        stream = self.llm_executor.rag_stream(
            provider=provider,
            model=model,
            query=query,
            system_prompt=system_prompt,
            filters=filters,
        )

        # Eagerly consume enough to detect CONTENT_MISMATCH
        buffer = ""
        prefetch: list = []
        for item in stream:
            if isinstance(item, TokenUsage):
                self.last_token_usage = item
                prefetch.append(item)
                break
            buffer += item
            prefetch.append(item)
            if len(buffer) >= 100:
                break

        if buffer.startswith("CONTENT_MISMATCH:"):
            raise ContentMismatchError(
                buffer[len("CONTENT_MISMATCH:") :].strip()
            )

        def _gen():
            yield from prefetch
            for item in stream:
                if isinstance(item, TokenUsage):
                    self.last_token_usage = item
                yield item

        return _gen()

    def _build_filters(
        self, subject: str | None, grade: str | None
    ) -> Dict[str, Any]:
        """Build metadata filters for RAG document search.

        Args:
            subject: Subject code (e.g., 'T', 'TV', 'TA')
            grade: Grade level (e.g., '1', '2', '3', '4', '5')

        Returns:
            Dictionary of filters for document metadata matching
        """
        filters = {}
        if subject:
            filters["subject_code"] = subject
        if grade:
            # Convert grade to integer if it's numeric (metadata stores it as int)
            try:
                filters["grade"] = int(grade)
            except (ValueError, TypeError):
                filters["grade"] = grade
        return filters

    def _log_filters(
        self, filters: Dict[str, Any], subject: str | None, grade: str | None
    ) -> None:
        """Log filter information for debugging.

        Args:
            filters: The constructed filters dictionary
            subject: Subject code
            grade: Grade level
        """
        print(f"[DEBUG] RAG filters being applied: {filters}")
        print(
            f"[DEBUG] Request - subject: {subject}, grade: {grade} (type: {type(grade).__name__})"
        )

    def _rag_batch_call(
        self,
        provider: str,
        model: str,
        query: str,
        system_prompt: str,
        filters: Dict[str, Any] | None,
    ) -> tuple[dict, Any]:
        """Execute a RAG batch call and check for content mismatch.

        Args:
            provider: LLM provider name
            model: Model name
            query: User query/prompt
            system_prompt: System prompt
            filters: Metadata filters for document search

        Returns:
            Tuple of (result dictionary, token_usage)

        Raises:
            ContentMismatchError: If content mismatch detected
        """
        result, token_usage = self.llm_executor.rag_batch(
            provider=provider,
            model=model,
            query=query,
            system_prompt=system_prompt,
            return_source_documents=True,
            filters=filters if filters else None,
            custom_prompt=None,
            verbose=False,
        )

        self.last_token_usage = token_usage
        self._check_content_mismatch(result)
        return result, token_usage
