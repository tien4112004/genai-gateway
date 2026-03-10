from typing import List, Tuple

from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from app.llms.adaper.rag_mixins import RAGAdapterMixin
from app.schemas.token_usage import TokenUsage


class GeminiAdapter(RAGAdapterMixin):
    def __init__(self, model_name: str, **params):
        # REQUIRES: GOOGLE_API_KEY in env
        self.model_name = model_name
        self.provider = "google"
        # Extract json_mode flag (not a LangChain param)
        json_mode = params.pop("json_mode", False)
        model_kwargs = (
            {"response_mime_type": "application/json"} if json_mode else {}
        )
        self.client = ChatGoogleGenerativeAI(
            model=model_name,
            **params,
            convert_system_message_to_human=True,
            model_kwargs=model_kwargs,
        )

    def run(
        self, model: str, messages: List[BaseMessage], **params
    ) -> Tuple[str, TokenUsage]:
        resp = self.client.invoke(input=messages, **params)
        content = resp.content

        if isinstance(content, list):
            content = " ".join(str(item) for item in content)

        # Extract token usage
        usage = TokenUsage()
        if hasattr(resp, "usage_metadata") and resp.usage_metadata:
            usage = TokenUsage(
                input_tokens=resp.usage_metadata.get("input_tokens", 0),
                output_tokens=resp.usage_metadata.get("output_tokens", 0),
                total_tokens=resp.usage_metadata.get("input_tokens", 0)
                + resp.usage_metadata.get("output_tokens", 0),
                model=model,
                provider="google",
            )

        return content, usage

    def stream(
        self, model: str, messages: List[BaseMessage], **params
    ) -> Tuple[List[str], TokenUsage]:
        """Stream response and collect token usage.

        Returns a tuple of (chunks, token_usage) where chunks is a list of content chunks.
        """
        chunks = []
        total_input_tokens = 0
        total_output_tokens = 0

        resp_stream = self.client.stream(input=messages, **params)

        for chunk in resp_stream:
            if chunk.content:
                chunks.append(chunk.content)
            # Sum token usage from each chunk
            if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                total_input_tokens += chunk.usage_metadata.get(
                    "input_tokens", 0
                )
                total_output_tokens += chunk.usage_metadata.get(
                    "output_tokens", 0
                )

        total = total_input_tokens + total_output_tokens
        usage = TokenUsage(
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            total_tokens=total,
            model=model,
            provider="google",
        )

        return chunks, usage
