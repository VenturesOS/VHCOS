"""
Robust DOC/DOCX text extraction utility.
Handles both legacy .doc (binary OLE) and modern .docx (OpenXML) formats
with multiple fallback strategies.
"""
import io
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text_from_word(content: bytes, filename: str = "file.doc") -> str:
    """Extract text from DOC or DOCX file content using multiple strategies.

    Args:
        content: Raw file bytes
        filename: Original filename (used for extension detection)

    Returns:
        Extracted text string

    Raises:
        ValueError: If no text could be extracted from the file
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    errors = []

    # Strategy 1: python-docx (works for .docx and some .doc that are actually .docx)
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if text.strip():
            logger.info(f"[DOC EXTRACT] Success via python-docx ({len(text)} chars)")
            return text
        errors.append("python-docx: no text found")
    except Exception as e:
        errors.append(f"python-docx: {e}")

    # Strategy 2: docx2txt (handles some edge cases python-docx doesn't)
    try:
        import docx2txt
        text = docx2txt.process(io.BytesIO(content))
        if text and text.strip():
            logger.info(f"[DOC EXTRACT] Success via docx2txt ({len(text)} chars)")
            return text
        errors.append("docx2txt: no text found")
    except Exception as e:
        errors.append(f"docx2txt: {e}")

    # Strategy 3: antiword (handles legacy binary .doc files)
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            result = subprocess.run(
                ["antiword", tmp.name],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                text = result.stdout.strip()
                logger.info(f"[DOC EXTRACT] Success via antiword ({len(text)} chars)")
                return text
            errors.append(f"antiword: exit {result.returncode}, stderr={result.stderr[:100]}")
    except FileNotFoundError:
        errors.append("antiword: not installed")
    except Exception as e:
        errors.append(f"antiword: {e}")

    # Strategy 4: olefile — extract raw text from OLE streams (binary .doc)
    try:
        import olefile
        if olefile.isOleFile(io.BytesIO(content)):
            ole = olefile.OleFileIO(io.BytesIO(content))
            if ole.exists("WordDocument"):
                # Try to extract from the Word Document stream
                text_parts = []
                for stream_name in ole.listdir():
                    stream_path = "/".join(stream_name)
                    try:
                        data = ole.openstream(stream_path).read()
                        # Extract printable ASCII/UTF-8 text
                        decoded = data.decode("utf-8", errors="ignore")
                        printable = "".join(c for c in decoded if c.isprintable() or c in "\n\r\t")
                        if len(printable) > 20:
                            text_parts.append(printable)
                    except Exception:
                        pass
                ole.close()
                if text_parts:
                    text = "\n".join(text_parts)
                    logger.info(f"[DOC EXTRACT] Success via olefile ({len(text)} chars)")
                    return text
            errors.append("olefile: no usable text in OLE streams")
        else:
            errors.append("olefile: not an OLE file")
    except Exception as e:
        errors.append(f"olefile: {e}")

    # Strategy 5: Raw text extraction (last resort — grab printable chars)
    try:
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                decoded = content.decode(encoding, errors="ignore")
                printable = "".join(c for c in decoded if c.isprintable() or c in "\n\r\t")
                # Filter out very short or garbage-heavy content
                lines = [l.strip() for l in printable.split("\n") if len(l.strip()) > 5]
                if len(lines) > 3:
                    text = "\n".join(lines)
                    logger.info(f"[DOC EXTRACT] Success via raw text ({encoding}, {len(text)} chars)")
                    return text
            except Exception:
                pass
        errors.append("raw text: not enough readable content")
    except Exception as e:
        errors.append(f"raw text: {e}")

    error_detail = "; ".join(errors)
    raise ValueError(
        f"Could not extract text from '{filename}'. "
        f"The file may be corrupted or in an unsupported format. "
        f"Try converting to .docx or .pdf first. Strategies tried: {error_detail}"
    )
