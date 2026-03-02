from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RefineContext(BaseModel):
    slideId: Optional[str] = None
    slideType: Optional[str] = None


class RefineContentRequest(BaseModel):
    schema: Dict[str, Any]
    instruction: str
    context: Optional[RefineContext] = None
    operation: Optional[str] = None  # "expand", "shorten", "grammar", "formal"
    model: str = Field(..., description="The model to use for modification")
    provider: str = Field(..., description="The provider of the model")


class TransformLayoutRequest(BaseModel):
    currentSchema: Dict[str, Any]
    targetType: str
    model: str = Field(..., description="The model to use for modification")
    provider: str = Field(..., description="The provider of the model")


class RefineElementTextRequest(BaseModel):
    slideId: str
    elementId: str
    currentText: str
    instruction: str
    slideSchema: Optional[Dict[str, Any]] = None
    slideType: Optional[str] = None
    operation: Optional[str] = None  # "expand", "shorten", "grammar", "formal"
    model: str = Field(..., description="The model to use for modification")
    provider: str = Field(..., description="The provider of the model")


class ReplaceElementImageRequest(BaseModel):
    slideId: str
    elementId: str
    description: str
    style: str
    themeDescription: Optional[str] = None
    artDescription: Optional[str] = None
    slideSchema: Optional[Dict[str, Any]] = None
    slideType: Optional[str] = None
    model: str = Field(..., description="The model to use for text generation")
    provider: str = Field(..., description="The provider for text generation")


class ExpandCombinedTextRequest(BaseModel):
    slideId: str
    items: List[Any]  # Can be strings or dicts
    instruction: str
    slideSchema: Optional[Dict[str, Any]] = None
    slideType: Optional[str] = None
    operation: Optional[str] = None  # "expand", "shorten", "grammar", "formal"
    model: str = Field(..., description="The model to use for expansion")
    provider: str = Field(..., description="The provider of the model")


# Mindmap-specific schemas
class TreeContext(BaseModel):
    mindmapId: Optional[str] = None
    rootNodeId: Optional[str] = None
    currentLevel: Optional[int] = None
    parentContent: Optional[str] = None
    siblingContents: Optional[List[str]] = None
    # Enhanced context for better AI responses
    mindmapTitle: Optional[str] = None
    rootNodeContent: Optional[str] = None
    fullAncestryPath: Optional[List[str]] = (
        None  # Ordered from root to immediate parent
    )
    existingChildrenContents: Optional[List[str]] = (
        None  # Current children of the node being expanded
    )


class RefineNodeRequest(BaseModel):
    nodeId: str
    currentContent: str
    instruction: str
    operation: Optional[str] = None  # "expand", "shorten", "grammar", "formal"
    context: Optional[TreeContext] = None
    model: str = Field(..., description="The model to use for modification")
    provider: str = Field(..., description="The provider of the model")


class ExpandNodeRequest(BaseModel):
    nodeId: str
    nodeContent: str
    maxChildren: int = Field(
        default=5, description="Maximum number of children to generate"
    )
    maxDepth: int = Field(
        default=2, description="Maximum depth for generated subtree"
    )
    context: Optional[TreeContext] = (
        None  # Tree context for generating relevant children
    )
    model: str = Field(..., description="The model to use for generation")
    provider: str = Field(..., description="The provider of the model")


class NodeContentItem(BaseModel):
    nodeId: str
    content: str
    level: int


class RefineBranchRequest(BaseModel):
    nodes: List[NodeContentItem]
    instruction: str
    operation: Optional[str] = None  # "expand", "shorten", "grammar", "formal"
    context: Optional[TreeContext] = None
    model: str = Field(..., description="The model to use for modification")
    provider: str = Field(..., description="The provider of the model")


# Generic Response Wrapper
class AIModificationResponse(BaseModel):
    success: bool
    data: Any
    message: Optional[str] = None
