import logging
import time
from typing import Optional

from app.repositories.teacher_system_prompt_repository import (
    TeacherSystemPromptRepository,
)

logger = logging.getLogger(__name__)

# TTL for in-memory cache entries (seconds)
_CACHE_TTL_SECONDS = 60


class TeacherSystemPromptService:
    """Service for retrieving teacher system prompts with in-memory TTL caching."""

    def __init__(self, repo: TeacherSystemPromptRepository):
        self._repo = repo
        # Cache: teacher_id -> (prompt_or_None, timestamp)
        self._cache: dict[str, tuple[Optional[str], float]] = {}

    def get_prompt(self, teacher_id: Optional[str]) -> Optional[str]:
        """Return the active system prompt for the given teacher_id, using cache."""
        if not teacher_id:
            return None

        now = time.monotonic()
        cached = self._cache.get(teacher_id)
        if cached is not None:
            prompt, cached_at = cached
            if now - cached_at < _CACHE_TTL_SECONDS:
                return prompt

        prompt = self._repo.get_prompt(teacher_id)
        self._cache[teacher_id] = (prompt, now)
        logger.debug(
            f"[TeacherSystemPromptService] Fetched prompt for teacher={teacher_id}, found={prompt is not None}"
        )
        return prompt
