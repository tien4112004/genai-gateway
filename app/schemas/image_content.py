from typing import List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal

from app.schemas.token_usage import TokenUsage


class ImageGenerateRequest(BaseModel):
    prompt: str
    model: str
    provider: str
    number_of_images: int = Field(
        default=1, description="Number of images to generate"
    )
    aspect_ratio: Literal["1:1", "9:16", "16:9", "4:3", "3:4"] = Field(
        default="1:1",
        description="Desired image dimensions, format: WIDTHxHEIGHT",
    )
    safety_filter_level: Optional[
        Literal["block_most", "block_some", "block_few", "block_fewest"]
    ] = Field(
        default="block_few",
        description="Safety filter level: block_most, block_some, block_few, block_fewest",
    )
    person_generation: (
        Literal["dont_allow", "allow_adult", "allow_all"] | None
    ) = Field(
        default="allow_all",
        description="Person generation: dont_allow, allow_adult, allow_all",
    )
    seed: Optional[int] = Field(
        default=None, description="Random seed for reproducible generation"
    )
    negative_prompt: Optional[str] = Field(
        default=(
            "weapons, knives, guns, swords, firearms, explosives, "
            "alcohol, cigarettes, drugs, needles, syringes, "
            "blood, gore, violence, injury, death, "
            "fire hazards, electrical hazards, sharp objects, "
            "toxic substances, poisonous items, dangerous chemicals"
        ),
        description="Negative prompt to avoid certain elements in the image",
    )

    def to_dict(self):
        return {
            "prompt": self.prompt,
            "safety_filter_level": self.safety_filter_level,
            "person_generation": self.person_generation,
        }


class ImageGenerateResponse(BaseModel):
    images: List[str] = Field(
        description="Base64 encoded images data (without mime prefix)"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if image generation failed"
    )
    count: int = Field(default=1, description="Number of Images")
    token_usage: Optional[TokenUsage] = Field(
        default=None,
        description="Token usage information (None for image generation as Google API does not expose token counts)",
    )
