from typing import List, Optional

from pydantic import BaseModel, Field
from typing_extensions import Literal


class MindmapGenerateRequest(BaseModel):
    topic: str
    language: str
    maxDepth: int = Field(
        default=4, description="Maximum depth of the mindmap"
    )
    maxBranchesPerNode: int = Field(
        default=3, description="Maximum branches per node"
    )
    provider: str
    model: str
    grade: Optional[int] = Field(
        None, description="The grade level for the content"
    )
    subject: Optional[str] = Field(
        None, max_length=100, description="The subject area for the content"
    )
    file_urls: Optional[List[str]] = Field(
        None, description="URLs of uploaded files to use as source material"
    )

    def to_dict(self):
        result = {
            "topic": self.topic,
            "language": self.language,
            "maxDepth": self.maxDepth,
            "maxBranchesPerNode": self.maxBranchesPerNode,
        }
        if self.grade:
            result["grade"] = self.grade
        if self.subject:
            result["subject"] = self.subject
        return result
