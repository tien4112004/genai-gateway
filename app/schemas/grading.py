"""Schemas for question grading."""

from typing import Optional

from pydantic import BaseModel, Field


class GradeQuestionRequest(BaseModel):
    """Request to grade an open-ended question."""

    questionContent: str = Field(
        ..., description="The main question/prompt"
    )
    questionExplaination: Optional[str] = Field(
        default="", description="Additional explanation or context for the question"
    )
    answerData: str = Field(
        ..., description="The student's answer to grade"
    )
    context: Optional[str] = Field(
        default="", description="A reading passage or related context (may be empty)"
    )
    maxScore: float = Field(
        ..., gt=0, description="Maximum possible score for this question"
    )
    grade: int = Field(
        ..., ge=1, le=5, description="Student's grade level (1-5)"
    )
    chapter: Optional[str] = Field(
        default="", description="Chapter or topic of the question"
    )
    expectedAnswer: Optional[str] = Field(
        default="", description="The expected/reference answer for comparison"
    )
    subject: Optional[str] = Field(
        default="", description="Subject of the question (e.g., Math, English, Science)"
    )


class GradeQuestionResponse(BaseModel):
    """Response containing the grading result."""

    totalScore: float = Field(
        ..., description="The score awarded (0 to maxScore)"
    )
    feedback: str = Field(
        ..., description="Feedback for the student"
    )
