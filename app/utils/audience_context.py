from pathlib import Path
from typing import Optional, Union

_PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts" / "common"
_EDUCATION_PATH = _PROMPTS_ROOT / "education_audience.st"
_GENERAL_PATH = _PROMPTS_ROOT / "general_audience.st"


def get_audience_context(
    subject: Optional[str], grade: Optional[Union[str, int]]
) -> str:
    """Return the audience context text based on whether education mode is active.

    Education mode is active when both subject and grade are provided.
    General mode returns a safe, all-ages content framing.
    """
    is_education = bool(subject and grade)
    path = _EDUCATION_PATH if is_education else _GENERAL_PATH
    return path.read_text(encoding="utf-8").strip()
