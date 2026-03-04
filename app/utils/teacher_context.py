from contextvars import ContextVar
from typing import Optional

_teacher_system_prompt: ContextVar[Optional[str]] = ContextVar(
    "teacher_system_prompt", default=None
)


def set_teacher_prompt(prompt: Optional[str]):
    """Set the teacher system prompt for the current request context.

    Returns the token that can be used to reset the context variable.
    """
    return _teacher_system_prompt.set(prompt)


def get_teacher_prompt() -> Optional[str]:
    """Get the teacher system prompt for the current request context."""
    return _teacher_system_prompt.get()


def build_system_with_teacher_prompt(base_prompt: str) -> str:
    """Prepend teacher system prompt to base system prompt if present.

    Teacher prompt is injected AFTER template rendering to avoid
    string.Template substitution issues with special characters (e.g. $, ${...})
    that may appear in Vietnamese text.
    """
    teacher_prompt = get_teacher_prompt()
    if not teacher_prompt:
        return base_prompt
    return (
        f"[Teacher Instructions]\n"
        f"{teacher_prompt}\n\n"
        f"[System Instructions]\n"
        f"{base_prompt}"
    )
