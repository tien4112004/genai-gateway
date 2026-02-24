import uuid
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# Subject code to name mapping
SUBJECT_NAME_MAP = {
    "T": "Math",
    "TV": "Vietnamese",
    "TA": "English",
}


# Request and Response models for outline generation
class OutlineGenerateRequest(BaseModel):
    topic: str = Field(..., description="The topic for the presentation")
    model: str = Field(..., description="The model to use for generation")
    provider: str = Field(..., description="The provider of the model")
    language: str = Field(..., description="The language for the presentation")
    slide_count: int = Field(
        ..., description="The number of slides to generate"
    )
    grade: Optional[int] = Field(
        None, description="The grade level for the content"
    )
    subject: Optional[str] = Field(
        None, max_length=100, description="The subject area for the content"
    )

    def to_dict(self):
        result = {
            "topic": self.topic,
            "model": self.model,
            "provider": self.provider,
            "language": self.language,
            "slide_count": self.slide_count,
            "grade": self.grade or "",
            "subject_name": SUBJECT_NAME_MAP.get(
                self.subject, self.subject or ""
            ),
        }
        if self.subject:
            result["subject"] = self.subject
        return result


# Request and Response models for presentation generation
class PresentationGenerateRequest(BaseModel):
    model: str = Field(..., description="The model to use for generation")
    provider: str = Field(..., description="The provider of the model")
    language: str = Field(..., description="The language for the presentation")
    slide_count: int = Field(
        ..., description="The number of slides to generate"
    )
    outline: str = Field(..., description="The outline for the presentation")
    meta_data: dict | None = Field(
        None, description="Additional metadata for the presentation"
    )
    grade: Optional[int] = Field(
        None, description="The grade level for the content"
    )
    subject: Optional[str] = Field(
        None, max_length=100, description="The subject area for the content"
    )

    def to_dict(self):
        result = {
            "model": self.model,
            "provider": self.provider,
            "language": self.language,
            "slide_count": self.slide_count,
            "outline": self.outline,
            "meta_data": self.meta_data,
        }
        if self.grade:
            result["grade"] = self.grade
        if self.subject:
            result["subject"] = self.subject
            result["subject_name"] = SUBJECT_NAME_MAP.get(
                self.subject, self.subject
            )
        return result
