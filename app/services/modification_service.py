import json
import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from openai import APIError as OpenAIAPIError
from openai import (
    AuthenticationError,
    RateLimitError,
)

from app.core.config import settings
from app.core.exceptions import (
    AIAuthenticationError,
    AIRateLimitError,
    AIServiceError,
)
from app.llms.executor import LLMExecutor
from app.prompts.loader import PromptStore
from app.schemas.modification import (
    ExpandCombinedTextRequest,
    ExpandNodeRequest,
    RefineBranchRequest,
    RefineContentRequest,
    RefineElementTextRequest,
    RefineNodeRequest,
    TransformLayoutRequest,
)

logger = logging.getLogger("uvicorn.error")


class ModificationService:
    def __init__(self, llm_executor: LLMExecutor, prompt_store: PromptStore):
        self.llm_executor = llm_executor or LLMExecutor()
        self.prompt_store = prompt_store or PromptStore()

    def _render(self, key: str, vars: Dict[str, Any] | None) -> str:
        return self.prompt_store.render(key, vars)

    def _get_operation(
        self, instruction: str, operation: Optional[str] = None
    ) -> str:
        """Determine operation type from explicit parameter or instruction text."""
        if operation:
            return operation.lower()

        # Fallback: parse instruction text
        instruction_lower = instruction.lower()
        if "expand" in instruction_lower or "more detail" in instruction_lower:
            return "expand"
        elif "shorten" in instruction_lower or "concise" in instruction_lower:
            return "shorten"
        elif "grammar" in instruction_lower or "spelling" in instruction_lower:
            return "grammar"
        elif "formal" in instruction_lower:
            return "formal"

        return "expand"  # Default fallback

    def _extract_json(self, text: str) -> Any:
        """Extract JSON from LLM response, stripping markdown fences if present."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (```json or ```)
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
            # Remove closing fence
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        return json.loads(cleaned)

    def refine_content(self, request: RefineContentRequest) -> Dict[str, Any]:
        try:
            slide_type = ""
            if request.context and request.context.slideType:
                slide_type = request.context.slideType

            # Determine which prompt to use based on operation
            operation = self._get_operation(
                request.instruction, request.operation
            )
            prompt_key = f"modification.slide.{operation}"

            prompt = self._render(
                prompt_key,
                {
                    "context_json": json.dumps(
                        request.schema, ensure_ascii=False
                    ),
                    "instruction": request.instruction,
                    "slide_type": slide_type,
                },
            )

            text, usage = self.llm_executor.batch(
                provider=request.provider,
                model=request.model,
                messages=[HumanMessage(content=prompt)],
            )
            logger.info(
                "refine_content tokens: %s",
                usage.total_tokens if usage else "N/A",
            )

            parsed = self._extract_json(text)
            return {"schema": parsed}
        except AuthenticationError as e:
            raise AIAuthenticationError(
                f"OpenAI authentication failed: {str(e)}"
            )
        except RateLimitError as e:
            raise AIRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except OpenAIAPIError as e:
            raise AIServiceError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error in refine_content")
            raise AIServiceError(f"Failed to refine content: {str(e)}")

    def transform_layout(
        self, request: TransformLayoutRequest
    ) -> Dict[str, Any]:
        try:
            prompt = self._render(
                "modification.slide.layout",
                {
                    "source_json": json.dumps(
                        request.currentSchema, ensure_ascii=False
                    ),
                    "target_type": request.targetType,
                },
            )

            text, usage = self.llm_executor.batch(
                provider=request.provider,
                model=request.model,
                messages=[HumanMessage(content=prompt)],
            )
            logger.info(
                "transform_layout tokens: %s",
                usage.total_tokens if usage else "N/A",
            )

            parsed = self._extract_json(text)
            return {"schema": parsed}
        except AuthenticationError as e:
            raise AIAuthenticationError(
                f"AI service authentication failed: {str(e)}"
            )
        except RateLimitError as e:
            raise AIRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except OpenAIAPIError as e:
            raise AIServiceError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error in transform_layout")
            raise AIServiceError(f"Failed to transform layout: {str(e)}")

    def refine_element_text(
        self, request: RefineElementTextRequest
    ) -> Dict[str, Any]:
        """Refine text content of a specific element."""
        try:
            slide_context = ""
            if request.slideType:
                slide_context += f"Slide layout type: {request.slideType}. "
            if request.slideSchema:
                title = request.slideSchema.get("title", "")
                if title:
                    slide_context += f"Slide title: {title}. "

            # Determine which prompt to use based on operation
            operation = self._get_operation(
                request.instruction, request.operation
            )
            prompt_key = f"modification.element.{operation}"

            prompt = self._render(
                prompt_key,
                {
                    "current_text": request.currentText,
                    "slide_context": slide_context,
                },
            )

            text, usage = self.llm_executor.batch(
                provider=request.provider,
                model=request.model,
                messages=[HumanMessage(content=prompt)],
            )
            logger.info(
                "refine_element_text tokens: %s",
                usage.total_tokens if usage else "N/A",
            )

            return {"refinedText": text.strip()}
        except AuthenticationError as e:
            raise AIAuthenticationError(
                f"AI service authentication failed: {str(e)}"
            )
        except RateLimitError as e:
            raise AIRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except OpenAIAPIError as e:
            raise AIServiceError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error in refine_element_text")
            raise AIServiceError(f"Failed to refine text: {str(e)}")

    def expand_combined_text(
        self, request: ExpandCombinedTextRequest
    ) -> Dict[str, Any]:
        """Expand content of combined text items."""
        try:
            slide_context = ""
            if request.slideType:
                slide_context += f"Slide layout type: {request.slideType}. "
            if request.slideSchema:
                title = request.slideSchema.get("title", "")
                if title:
                    slide_context += f"Slide title: {title}. "

            # Convert items to JSON for the prompt
            items_json = json.dumps(request.items, ensure_ascii=False)

            # Determine which prompt to use based on operation
            operation = self._get_operation(
                request.instruction, request.operation
            )
            prompt_key = f"modification.combined_text.{operation}_items"

            prompt = self._render(
                prompt_key,
                {
                    "items_json": items_json,
                    "slide_context": slide_context,
                },
            )

            text, usage = self.llm_executor.batch(
                provider=request.provider,
                model=request.model,
                messages=[HumanMessage(content=prompt)],
            )
            logger.info(
                "refine_combined_text tokens: %s",
                usage.total_tokens if usage else "N/A",
            )

            # Parse the refined items from the response
            parsed = self._extract_json(text)
            return {"expandedItems": parsed}
        except AuthenticationError as e:
            raise AIAuthenticationError(
                f"AI service authentication failed: {str(e)}"
            )
        except RateLimitError as e:
            raise AIRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except OpenAIAPIError as e:
            raise AIServiceError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error in refine_combined_text")
            raise AIServiceError(f"Failed to refine combined text: {str(e)}")

    def refine_mindmap_node(
        self, request: RefineNodeRequest
    ) -> Dict[str, Any]:
        """Refine a mindmap node's content (expand, shorten, fix grammar, formalize)."""
        try:
            # Build tree context information
            tree_context = ""
            if request.context:
                # Main mindmap topic
                if request.context.mindmapTitle:
                    tree_context += (
                        f"Mindmap Topic: {request.context.mindmapTitle}. "
                    )

                # Hierarchy context
                if request.context.rootNodeContent:
                    tree_context += (
                        f"Root Concept: {request.context.rootNodeContent}. "
                    )

                if (
                    request.context.fullAncestryPath
                    and len(request.context.fullAncestryPath) > 0
                ):
                    ancestry = " → ".join(request.context.fullAncestryPath)
                    tree_context += f"Hierarchy Path: {ancestry}. "

                if request.context.parentContent:
                    tree_context += (
                        f"Parent Concept: {request.context.parentContent}. "
                    )

                # Sibling context for consistency
                if (
                    request.context.siblingContents
                    and len(request.context.siblingContents) > 0
                ):
                    siblings = ", ".join(
                        request.context.siblingContents[:8]
                    )  # Limit to 8
                    tree_context += f"Related Sibling Concepts: {siblings}. "

            # Determine which prompt to use based on operation
            operation = self._get_operation(
                request.instruction, request.operation
            )
            prompt_key = f"modification.mindmap.{operation}"

            # Prepare grade level text for prompt
            grade_level = ""

            prompt = self._render(
                prompt_key,
                {
                    "current_content": request.currentContent,
                    "tree_context": tree_context,
                    "instruction": request.instruction,
                    "grade_level": grade_level,
                },
            )

            text, usage = self.llm_executor.batch(
                provider=request.provider,
                model=request.model,
                messages=[HumanMessage(content=prompt)],
            )
            logger.info(
                "refine_mindmap_node tokens: %s",
                usage.total_tokens if usage else "N/A",
            )

            return {"refinedContent": text.strip()}
        except AuthenticationError as e:
            raise AIAuthenticationError(
                f"AI service authentication failed: {str(e)}"
            )
        except RateLimitError as e:
            raise AIRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except OpenAIAPIError as e:
            raise AIServiceError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error in refine_mindmap_node")
            raise AIServiceError(f"Failed to refine mindmap node: {str(e)}")

    def expand_mindmap_node(
        self, request: ExpandNodeRequest
    ) -> Dict[str, Any]:
        """Generate child nodes for a mindmap node with AI."""
        try:
            # Build tree context information
            tree_context = ""
            if request.context:
                # Main mindmap topic
                if request.context.mindmapTitle:
                    tree_context += (
                        f"Mindmap Topic: {request.context.mindmapTitle}. "
                    )

                # Hierarchy context
                if request.context.rootNodeContent:
                    tree_context += (
                        f"Root Concept: {request.context.rootNodeContent}. "
                    )

                if (
                    request.context.fullAncestryPath
                    and len(request.context.fullAncestryPath) > 0
                ):
                    ancestry = " → ".join(request.context.fullAncestryPath)
                    tree_context += f"Hierarchy Path: {ancestry}. "

                if request.context.parentContent:
                    tree_context += (
                        f"Parent Concept: {request.context.parentContent}. "
                    )

                # Sibling context for consistency
                if (
                    request.context.siblingContents
                    and len(request.context.siblingContents) > 0
                ):
                    siblings = ", ".join(
                        request.context.siblingContents[:8]
                    )  # Limit to 8
                    tree_context += f"Related Sibling Concepts: {siblings}. "

                # Existing children to avoid duplication
                if (
                    request.context.existingChildrenContents
                    and len(request.context.existingChildrenContents) > 0
                ):
                    existing = ", ".join(
                        request.context.existingChildrenContents[:10]
                    )  # Limit to 10
                    tree_context += f"Existing Children (DO NOT duplicate these): {existing}. "

                tree_context += (
                    f"Current Level: {request.context.currentLevel}. "
                )

            # Render system prompt that defines the JSON structure
            system_prompt = self._render(
                "mindmap.system",
                {
                    "maxDepth": str(request.maxDepth),
                    "maxBranchesPerNode": str(request.maxChildren),
                },
            )

            # Render user prompt with tree context
            user_prompt = self._render(
                "mindmap.user",
                {
                    "topic": request.nodeContent,
                    "tree_context": tree_context,
                    "maxDepth": str(request.maxDepth),
                    "maxBranchesPerNode": str(request.maxChildren),
                    "language": "",  # Empty - AI will auto-detect from content
                    "grade": "",  # Empty - not used
                    "subject": "",  # Empty - not used
                },
            )

            # Call LLM with BOTH system and user prompts
            text, usage = self.llm_executor.batch(
                provider=request.provider,
                model=request.model,
                messages=[
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ],
            )
            logger.info(
                "expand_mindmap_node tokens: %s",
                usage.total_tokens if usage else "N/A",
            )

            # Parse the hierarchical children structure
            parsed = self._extract_json(text)
            return {"children": parsed.get("children", [])}
        except AuthenticationError as e:
            raise AIAuthenticationError(
                f"AI service authentication failed: {str(e)}"
            )
        except RateLimitError as e:
            raise AIRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except OpenAIAPIError as e:
            raise AIServiceError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error in expand_mindmap_node")
            raise AIServiceError(f"Failed to expand mindmap node: {str(e)}")

    def refine_mindmap_branch(
        self, request: RefineBranchRequest
    ) -> Dict[str, Any]:
        """Refine multiple nodes in a mindmap branch together."""
        try:
            # Build tree context information
            tree_context = ""
            if request.context:
                # Main mindmap topic
                if request.context.mindmapTitle:
                    tree_context += (
                        f"Mindmap Topic: {request.context.mindmapTitle}. "
                    )

                # Hierarchy context
                if request.context.rootNodeContent:
                    tree_context += (
                        f"Root Concept: {request.context.rootNodeContent}. "
                    )

                if (
                    request.context.fullAncestryPath
                    and len(request.context.fullAncestryPath) > 0
                ):
                    ancestry = " → ".join(request.context.fullAncestryPath)
                    tree_context += f"Hierarchy Path: {ancestry}. "

                if request.context.parentContent:
                    tree_context += (
                        f"Parent Concept: {request.context.parentContent}. "
                    )

                tree_context += (
                    f"Current Level: {request.context.currentLevel}. "
                )

            # Convert nodes to JSON for the prompt
            nodes_json = json.dumps(
                [
                    {
                        "nodeId": n.nodeId,
                        "content": n.content,
                        "level": n.level,
                    }
                    for n in request.nodes
                ],
                ensure_ascii=False,
            )

            # Determine which prompt to use based on operation
            operation = self._get_operation(
                request.instruction, request.operation
            )
            prompt_key = f"modification.mindmap.{operation}_branch"

            prompt = self._render(
                prompt_key,
                {
                    "nodes_json": nodes_json,
                    "tree_context": tree_context,
                    "instruction": request.instruction,
                    "grade_level": "",
                },
            )

            text, usage = self.llm_executor.batch(
                provider=request.provider,
                model=request.model,
                messages=[HumanMessage(content=prompt)],
            )
            logger.info(
                "refine_mindmap_branch tokens: %s",
                usage.total_tokens if usage else "N/A",
            )

            # Parse refined nodes from response
            parsed = self._extract_json(text)
            return {"refinedNodes": parsed}
        except AuthenticationError as e:
            raise AIAuthenticationError(
                f"AI service authentication failed: {str(e)}"
            )
        except RateLimitError as e:
            raise AIRateLimitError(f"OpenAI rate limit exceeded: {str(e)}")
        except OpenAIAPIError as e:
            raise AIServiceError(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.exception("Unexpected error in refine_mindmap_branch")
            raise AIServiceError(f"Failed to refine mindmap branch: {str(e)}")
