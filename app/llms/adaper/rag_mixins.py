"""RAG Adapter Mixin for adding RAG capabilities to text models."""

from typing import Any, Dict, Iterator, List, Optional, Tuple

from langgraph.prebuilt.chat_agent_executor import create_tool_calling_executor

from app.llms.tool.agent_tools import tools
from app.schemas.token_usage import TokenUsage


class RAGAdapterMixin:
    """Mixin to add RAG capabilities to LLM adapters."""

    def run_rag(
        self,
        query: str,
        system_prompt: str,
        return_source_documents: bool = True,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Tuple[Dict[str, Any], TokenUsage]:
        """
        Run RAG pipeline using a tool-calling agent.

        Args:
            query: User query
            system_prompt: System prompt for the agent
            return_source_documents: Whether to return source documents
            filters: Optional filters for document search
            **kwargs: Additional parameters

        Returns:
            Tuple of (result dictionary, token usage)
        """
        from langchain_core.messages import HumanMessage

        from app.llms.tool.agent_tools import (
            clear_search_filters,
            set_search_filters,
        )

        if not hasattr(self, "client"):
            raise ValueError(
                "Adapter must have 'client' attribute to use RAGMixin"
            )

        try:
            # Set filters in context-local storage (thread-safe)
            if filters:
                set_search_filters(filters)

            # Define agent
            agent = create_tool_calling_executor(
                self.client,
                tools,
                prompt=system_prompt,
            )

            # Execute
            response = agent.invoke(
                input={"messages": [HumanMessage(content=query)]}
            )

            # Extract the final AI message
            messages = response.get("messages", [])
            final_message = messages[-1] if messages else None

            # Ensure content is always a string
            content = ""
            if final_message:
                content = self._extract_text_content(final_message.content)

            result = {
                "answer": content,
                "query": query,
            }

            # Note: structured context requires custom state in LangGraph
            if (
                response is not None
                and return_source_documents
                and "context" in response
            ):
                result["source_documents"] = self._format_source_documents(
                    response["context"]
                )
                result["num_sources"] = len(response["context"])

            # Extract token usage from the final message
            token_usage = self._extract_token_usage(final_message)

            return result, token_usage

        finally:
            # Always clear filters from context
            clear_search_filters()

    def stream_rag(
        self,
        query: str,
        system_prompt: str,
        filters: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Iterator:
        """
        Stream RAG pipeline responses.

        Yields str content chunks followed by a final TokenUsage object.
        """
        from langchain_core.messages import AIMessageChunk, HumanMessage

        from app.llms.tool.agent_tools import (
            clear_search_filters,
            set_search_filters,
        )

        if not hasattr(self, "client"):
            raise ValueError(
                "Adapter must have 'client' attribute to use RAGMixin"
            )

        try:
            if filters:
                set_search_filters(filters)

            agent = create_tool_calling_executor(
                self.client,
                tools,
                prompt=system_prompt,
            )

            total_usage = {"input": 0, "output": 0}

            for chunk, metadata in agent.stream(
                {"messages": [HumanMessage(content=query)]},
                stream_mode="messages",
            ):
                if not isinstance(chunk, AIMessageChunk):
                    continue

                # Accumulate usage from metadata
                usage = getattr(chunk, "usage_metadata", None) or {}
                if usage:
                    total_usage["input"] = usage.get(
                        "input_tokens", total_usage["input"]
                    )
                    total_usage["output"] = usage.get(
                        "output_tokens", total_usage["output"]
                    )
                else:
                    # Fallback for provider-specific metadata
                    rm = getattr(chunk, "response_metadata", None) or {}
                    um = rm.get("usage_metadata", {})
                    if um:
                        total_usage["input"] = um.get(
                            "prompt_token_count", total_usage["input"]
                        )
                        total_usage["output"] = um.get(
                            "candidates_token_count", total_usage["output"]
                        )

                # Skip tool-calling chunks
                if chunk.tool_calls:
                    continue

                text = self._extract_text_content(chunk.content)
                if text:
                    yield text

            # Final token usage yield
            yield TokenUsage(
                input_tokens=total_usage["input"],
                output_tokens=total_usage["output"],
                total_tokens=total_usage["input"] + total_usage["output"],
                model=getattr(self, "model_name", "unknown"),
                provider=getattr(self, "provider", "unknown"),
            )

        finally:
            clear_search_filters()

    @staticmethod
    def _extract_text_content(content) -> str:
        """Extract plain text from an AIMessage content value.

        Handles three forms returned by LangChain providers:
        - str: returned as-is
        - list: each item is either a dict block or a raw string.
          Dict blocks with ``type == "text"`` contribute their ``text`` value;
          thinking/signature blocks (``type != "text"``) are skipped.
        - anything else: coerced with str()
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type", "text") == "text":
                        parts.append(block.get("text", ""))
                else:
                    parts.append(str(block))
            return "".join(parts)
        return str(content) if content else ""

    def _format_source_documents(
        self, source_documents: List[Any]
    ) -> List[Dict[str, Any]]:
        """Format source documents for response."""
        return [
            {
                "page_content": doc.page_content,
                "metadata": doc.metadata,
            }
            for doc in source_documents
        ]

    def _extract_token_usage(self, message: Any) -> TokenUsage:
        """Extract token usage from AI message.

        Checks two sources in order:
        1. Standardized ``usage_metadata`` attribute (LangChain 0.2+, set by
           LangGraph on the AIMessage directly).
        2. Provider-specific ``response_metadata`` (Gemini keys).
        """
        if not message:
            return TokenUsage(
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                model=getattr(self, "model_name", "unknown"),
                provider=getattr(self, "provider", "unknown"),
            )

        # 1. Standardized usage_metadata attribute (LangChain 0.2+)
        usage = getattr(message, "usage_metadata", None) or {}
        if usage.get("input_tokens") or usage.get("output_tokens"):
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            return TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=usage.get(
                    "total_tokens", input_tokens + output_tokens
                ),
                model=getattr(self, "model_name", "unknown"),
                provider=getattr(self, "provider", "unknown"),
            )

        # 2. Gemini-specific response_metadata
        if hasattr(message, "response_metadata"):
            metadata = message.response_metadata or {}
            usage_metadata = metadata.get("usage_metadata", {})

            input_tokens = usage_metadata.get("prompt_token_count", 0)
            output_tokens = usage_metadata.get("candidates_token_count", 0)
            total_tokens = usage_metadata.get(
                "total_token_count", input_tokens + output_tokens
            )

            return TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                model=getattr(self, "model_name", "unknown"),
                provider=getattr(self, "provider", "unknown"),
            )

        return TokenUsage(
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            model=getattr(self, "model_name", "unknown"),
            provider=getattr(self, "provider", "unknown"),
        )
