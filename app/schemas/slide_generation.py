import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class GenerateSlidesRequest(BaseModel):
    """Request model for generating slides within an existing presentation."""

    prompt: str = Field(..., description="User instruction for slide content")
    slide_count: int = Field(
        ..., ge=1, le=10, description="Number of slides to generate"
    )
    model: str = Field(..., description="LLM model to use")
    provider: str = Field(..., description="LLM provider")
    art_style: Optional[str] = Field(
        None, description="Art style for image prompts"
    )
    image_model: Optional[str] = Field(
        None, description="Image generation model"
    )
    image_provider: Optional[str] = Field(
        None, description="Image generation provider"
    )
    negative_prompt: Optional[str] = Field(
        default=(
            "weapons, knives, guns, swords, firearms, explosives, "
            "alcohol, cigarettes, drugs, needles, syringes, "
            "blood, gore, violence, injury, death, "
            "fire hazards, electrical hazards, sharp objects, "
            "toxic substances, poisonous items, dangerous chemicals"
        ),
        description="Negative prompt for images",
    )
    context: Optional[Dict[str, Any]] = Field(
        None, description="Dynamic context object from the presentation"
    )
    language: str = Field("vi", description="Language for generated content")

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "prompt": self.prompt,
            "slide_count": str(self.slide_count),
            "language": self.language,
        }
        if self.context:
            result["context"] = json.dumps(
                self.context, ensure_ascii=False, indent=2
            )
        else:
            result["context"] = "No additional context provided."
        return result
