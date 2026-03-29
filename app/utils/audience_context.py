from pathlib import Path
from typing import Optional, Union

_PROMPTS_ROOT = Path(__file__).resolve().parent.parent / "prompts" / "common"
_EDUCATION_PATH = _PROMPTS_ROOT / "education_audience.st"
_GENERAL_PATH = _PROMPTS_ROOT / "general_audience.st"

# Read once at module load — these files never change at runtime.
# Fail fast with a clear message if the deployment is missing the files.
try:
    _EDUCATION_CONTEXT = _EDUCATION_PATH.read_text(encoding="utf-8").strip()
    _GENERAL_CONTEXT = _GENERAL_PATH.read_text(encoding="utf-8").strip()
except FileNotFoundError as e:
    raise RuntimeError(
        f"Audience context prompt file not found: {e.filename}. "
        "Ensure app/prompts/common/education_audience.st and general_audience.st exist."
    ) from e


def get_audience_context(
    subject: Optional[str], grade: Optional[Union[str, int]]
) -> str:
    """Return the audience context text based on whether education mode is active.

    Education mode is active when both subject and grade are explicitly provided
    (i.e. neither is None). Uses `is not None` to correctly handle grade=0.
    General mode returns a safe, all-ages content framing.
    """
    is_education = subject is not None and grade is not None
    return _EDUCATION_CONTEXT if is_education else _GENERAL_CONTEXT
