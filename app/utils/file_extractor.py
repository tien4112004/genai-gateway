"""Utility for downloading and extracting text from uploaded files (PDF, DOCX, TXT)."""

import logging
from dataclasses import dataclass
from typing import List

import httpx

logger = logging.getLogger(__name__)


@dataclass
class FileContent:
    file_type: str  # "pdf" | "docx" | "txt"
    raw_bytes: bytes  # original bytes (for Gemini multimodal PDF)
    extracted_text: str  # text fallback (DOCX/TXT, or PDF text layer)
    mime_type: str


def _detect_type(url: str, raw_bytes: bytes) -> str:
    """Detect file type from URL suffix first, then magic bytes."""
    lower = url.lower().split("?")[0]  # strip query params
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith(".docx"):
        return "docx"
    if lower.endswith(".doc"):
        return "docx"
    if lower.endswith(".txt"):
        return "txt"

    # Magic bytes fallback
    if raw_bytes[:4] == b"%PDF":
        return "pdf"
    if raw_bytes[:2] == b"PK":  # ZIP-based (DOCX)
        return "docx"

    return "txt"


def _extract_pdf_text(raw_bytes: bytes) -> str:
    try:
        import io

        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(raw_bytes))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"[file_extractor] pypdf text extraction failed: {e}")
        return ""


def _extract_docx_text(raw_bytes: bytes) -> str:
    try:
        import io

        from docx import Document

        doc = Document(io.BytesIO(raw_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        logger.warning(f"[file_extractor] python-docx extraction failed: {e}")
        return ""


def fetch_and_extract(url: str) -> FileContent:
    """Download a file from a URL and extract its content."""
    logger.info(f"[file_extractor] Fetching: {url}")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        raw_bytes = resp.content

    file_type = _detect_type(url, raw_bytes)

    if file_type == "pdf":
        extracted_text = _extract_pdf_text(raw_bytes)
        mime_type = "application/pdf"
    elif file_type == "docx":
        extracted_text = _extract_docx_text(raw_bytes)
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        raw_bytes = b""  # not needed for DOCX
    else:
        extracted_text = raw_bytes.decode("utf-8", errors="ignore")
        mime_type = "text/plain"
        raw_bytes = b""

    logger.info(
        f"[file_extractor] type={file_type}, text_len={len(extracted_text)}, raw_bytes={len(raw_bytes)}"
    )
    return FileContent(
        file_type=file_type,
        raw_bytes=raw_bytes,
        extracted_text=extracted_text,
        mime_type=mime_type,
    )


def extract_from_urls(file_urls: List[str]) -> List[FileContent]:
    """Download and extract content from a list of URLs."""
    results = []
    for url in file_urls:
        try:
            results.append(fetch_and_extract(url))
        except Exception as e:
            logger.error(f"[file_extractor] Failed to fetch {url}: {e}")
    return results
