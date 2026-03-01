"""Utility for downloading and extracting text from uploaded files (PDF, DOCX, TXT, images)."""

import logging
from dataclasses import dataclass
from typing import List

import httpx

logger = logging.getLogger(__name__)


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


@dataclass
class FileContent:
    file_type: str  # "pdf" | "docx" | "txt" | "image"
    raw_bytes: bytes  # original bytes (PDF multimodal / image)
    extracted_text: str  # text fallback (DOCX/TXT, or PDF text layer)
    mime_type: str


def _detect_type(url: str, raw_bytes: bytes) -> tuple[str, str]:
    """Detect file type and MIME type. Returns (file_type, mime_type)."""
    path = url.lower().split("?")[0]  # strip query params

    # URL extension detection
    for ext in _IMAGE_EXTENSIONS:
        if path.endswith(ext):
            return "image", _IMAGE_MIME[ext]
    if path.endswith(".pdf"):
        return "pdf", "application/pdf"
    if path.endswith(".docx") or path.endswith(".doc"):
        return (
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if path.endswith(".txt"):
        return "txt", "text/plain"

    # Magic bytes fallback
    if raw_bytes[:4] == b"%PDF":
        return "pdf", "application/pdf"
    if raw_bytes[:2] == b"PK":
        return (
            "docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    if raw_bytes[:3] == b"\xff\xd8\xff":
        return "image", "image/jpeg"
    if raw_bytes[:4] == b"\x89PNG":
        return "image", "image/png"
    if raw_bytes[:4] in (b"GIF8", b"GIF9"):
        return "image", "image/gif"
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "image", "image/webp"

    return "txt", "text/plain"


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

    file_type, mime_type = _detect_type(url, raw_bytes)

    if file_type == "image":
        extracted_text = ""  # images are sent as vision parts, not text
    elif file_type == "pdf":
        extracted_text = _extract_pdf_text(raw_bytes)
    elif file_type == "docx":
        extracted_text = _extract_docx_text(raw_bytes)
        raw_bytes = b""  # not needed for DOCX
    else:
        extracted_text = raw_bytes.decode("utf-8", errors="ignore")
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
