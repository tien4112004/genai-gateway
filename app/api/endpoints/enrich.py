"""
TEMPORARY - Enrichment API for generating questions with images.

This file is temporary and should be REMOVED after the database enrichment is complete.
To disable: remove the import from app/api/router.py.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.fastapi_depends import ExamServiceDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["temp-enrich"])

# ---------------------------------------------------------------------------
# Request / Response schemas (kept in this file for easy deletion)
# ---------------------------------------------------------------------------

SUBJECT_NAMES = {
    "T": "Toán (Mathematics)",
    "TV": "Tiếng Việt (Vietnamese Language)",
    "TA": "Tiếng Anh (English)",
}


class GenerateVisualQuestionsRequest(BaseModel):
    """Request to generate questions whose answers are images."""

    grade: str = Field(..., description="Grade level: K, 1, 2, 3, 4, 5")
    subject: str = Field(..., description="Subject code: T, TV, TA")
    chapter: str = Field(..., description="Topic / chapter name")
    questions_per_difficulty: Dict[str, int] = Field(
        default={"KNOWLEDGE": 3, "COMPREHENSION": 2},
        description="Number of questions per difficulty: KNOWLEDGE, COMPREHENSION, APPLICATION",
    )
    question_types: Optional[List[str]] = Field(
        default=["MULTIPLE_CHOICE"],
        description="Question types: MULTIPLE_CHOICE, MATCHING",
    )
    prompt: Optional[str] = Field(
        None,
        description="Extra instructions for the LLM",
    )
    provider: Optional[str] = Field(
        default="google", description="LLM provider"
    )
    model: Optional[str] = Field(
        default="gemini-2.5-flash", description="LLM model"
    )


class QuestionWithOptionImagePrompts(BaseModel):
    """A generated question whose answer options each carry an imagePrompt.

    The backend will iterate over each option/pair, call the image-generation API,
    upload the result, and set imageUrl (or leftImageUrl) before saving to the database.
    Questions where no image could be generated are discarded entirely.
    """

    type: str
    difficulty: str
    title: str
    titleImageUrl: Optional[str] = None
    explanation: Optional[str] = None
    grade: str
    chapter: str
    subject: str
    contextId: Optional[str] = None
    data: Any
    point: float = 1.0


# ---------------------------------------------------------------------------
# Inline LLM prompt (no template file — simpler to delete)
# ---------------------------------------------------------------------------

_VISUAL_QUESTION_SYSTEM_PROMPT = """\
You are an expert Vietnamese elementary school teacher creating image-based exam questions.

Every question you create MUST:
1. Ask students to look at images to answer — the question title should reference images
   (e.g. "Nhìn vào các hình ảnh dưới đây và trả lời:" or "Look at the pictures and choose:").
2. Each answer option carries its OWN image:
   - MULTIPLE_CHOICE: every option has an "imagePrompt" field — a clear, detailed,
     child-friendly English description of the image for that specific option.
   - MATCHING: every pair's left item has a "leftImagePrompt" field describing the image
     to show on the left side; the right side is text only.
   The backend generates one image per option/pair from these prompts.

## Supported question types

### MULTIPLE_CHOICE — every option has its own imagePrompt
{{
  "type": "MULTIPLE_CHOICE",
  "difficulty": "KNOWLEDGE",
  "title": "Nhìn vào các hình ảnh. Đây là con gì?",
  "explanation": "Đây là con mèo...",
  "grade": "2",
  "chapter": "Động vật",
  "subject": "TV",
  "data": {{
    "options": [
      {{"text": "Con chó",  "imageUrl": null, "isCorrect": false, "imagePrompt": "A friendly golden retriever dog sitting, simple white background, educational cartoon style for children"}},
      {{"text": "Con mèo",  "imageUrl": null, "isCorrect": true,  "imagePrompt": "A cute orange tabby cat sitting, simple white background, educational cartoon style for children"}},
      {{"text": "Con thỏ",  "imageUrl": null, "isCorrect": false, "imagePrompt": "A white fluffy rabbit sitting upright, simple white background, educational cartoon style for children"}},
      {{"text": "Con bò",   "imageUrl": null, "isCorrect": false, "imagePrompt": "A black and white dairy cow standing, simple white background, educational cartoon style for children"}}
    ],
    "shuffleOptions": true
  }},
  "point": 1.0
}}

### MATCHING — left side shows image (leftImagePrompt), right side is text label
{{
  "type": "MATCHING",
  "difficulty": "KNOWLEDGE",
  "title": "Nối hình ảnh với tên đúng.",
  "explanation": "...",
  "grade": "2",
  "chapter": "Động vật",
  "subject": "TV",
  "data": {{
    "pairs": [
      {{"left": "?", "leftImageUrl": null, "right": "Con mèo", "rightImageUrl": null, "leftImagePrompt": "A cute cartoon cat sitting, simple white background, educational style for children"}},
      {{"left": "?", "leftImageUrl": null, "right": "Con chó", "rightImageUrl": null, "leftImagePrompt": "A friendly cartoon dog sitting, simple white background, educational style for children"}},
      {{"left": "?", "leftImageUrl": null, "right": "Con thỏ", "rightImageUrl": null, "leftImagePrompt": "A cute cartoon rabbit, simple white background, educational style for children"}},
      {{"left": "?", "leftImageUrl": null, "right": "Con bò",  "rightImageUrl": null, "leftImagePrompt": "A cartoon cow standing, simple white background, educational style for children"}}
    ],
    "shufflePairs": true
  }},
  "point": 1.0
}}

## Output rules
- Return ONLY a valid JSON array — no markdown, no extra text.
- Use Vietnamese for subject T and TV; English for TA.
- Do NOT include an "id" field.
- "titleImageUrl" must be null.
- difficulty: KNOWLEDGE | COMPREHENSION | APPLICATION (never use question format values here).
- type: MULTIPLE_CHOICE | MATCHING (never use difficulty values here).
- MULTIPLE_CHOICE: exactly 4 options, exactly 1 isCorrect=true, ALL options MUST have a non-empty "imagePrompt".
- MATCHING: 4–6 pairs, ALL left items MUST have a non-empty "leftImagePrompt"; set "left" to "?".
"""


def _build_user_message(request: GenerateVisualQuestionsRequest) -> str:
    subject_name = SUBJECT_NAMES.get(request.subject, request.subject)
    total = sum(request.questions_per_difficulty.values())
    difficulty_lines = "\n".join(
        f"  - {diff}: {count} question(s)"
        for diff, count in request.questions_per_difficulty.items()
    )
    types_str = ", ".join(request.question_types or ["MULTIPLE_CHOICE"])
    extra = f"\nExtra instructions: {request.prompt}" if request.prompt else ""

    return f"""\
Generate {total} image-based exam questions with these specifications:

- Grade: {request.grade}
- Subject: {subject_name} ({request.subject})
- Chapter / Topic: {request.chapter}
- Difficulty distribution:
{difficulty_lines}
- Allowed question types: {types_str}
{extra}

Important:
- The question title should instruct students to look at the images and answer.
- MULTIPLE_CHOICE: every option must have a rich "imagePrompt" in English describing that option's image.
- MATCHING: every pair's left item must have a "leftImagePrompt" in English; set "left" to "?".
- Return ONLY a valid JSON array of {total} question objects.
"""


def _extract_json(raw: str) -> str:
    """Strip optional markdown code block wrapping from LLM output."""
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        # Drop first (```json or ```) and last (```) lines
        raw = "\n".join(
            lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        )
    return raw.strip()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/temp/questions/generate-visual",
    response_model=List[QuestionWithOptionImagePrompts],
    summary="[TEMP] Generate visual questions with per-option image prompts",
    description=(
        "Generates questions whose answer options each carry an imagePrompt. "
        "The backend generates one image per option/pair, uploads it, and sets "
        "imageUrl (or leftImageUrl) before saving. Questions with zero images are discarded."
    ),
)
def generate_visual_questions(
    request: GenerateVisualQuestionsRequest,
    svc: ExamServiceDep,
):
    logger.info(
        "[TEMP/ENRICH] Generating visual questions: grade=%s, subject=%s, chapter=%s, total=%d",
        request.grade,
        request.subject,
        request.chapter,
        sum(request.questions_per_difficulty.values()),
    )

    sys_msg = _VISUAL_QUESTION_SYSTEM_PROMPT
    usr_msg = _build_user_message(request)

    try:
        raw, _token_usage = svc.llm_executor.batch(
            provider=request.provider,
            model=request.model,
            messages=[
                SystemMessage(content=sys_msg),
                HumanMessage(content=usr_msg),
            ],
        )
    except Exception as e:
        logger.error("[TEMP/ENRICH] LLM call failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM generation failed: {e}",
        )

    try:
        json_text = _extract_json(raw)
        questions_raw: List[Dict[str, Any]] = json.loads(json_text)
    except Exception as e:
        logger.error(
            "[TEMP/ENRICH] Failed to parse LLM response: %s\nRaw (first 500): %.500s",
            e,
            raw,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse LLM response: {e}",
        )

    # Validate and parse into response model
    result: List[QuestionWithOptionImagePrompts] = []
    for i, q in enumerate(questions_raw):
        try:
            result.append(QuestionWithOptionImagePrompts(**q))
        except Exception as e:
            logger.warning("[TEMP/ENRICH] Skipping question %d: %s", i, e)

    logger.info(
        "[TEMP/ENRICH] Successfully generated %d visual questions", len(result)
    )
    return result
