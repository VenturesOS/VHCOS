"""
VHC Talent OS — File Upload Validator
Server-side file validation with magic byte detection to block malware uploads.
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Magic bytes for allowed file types
MAGIC_BYTES = {
    "pdf": [(0, b"%PDF")],
    "docx": [(0, b"PK\x03\x04")],  # ZIP-based (OOXML)
    "doc": [(0, b"\xd0\xcf\x11\xe0")],  # OLE compound
    "xlsx": [(0, b"PK\x03\x04")],
    "xls": [(0, b"\xd0\xcf\x11\xe0")],
    "csv": [],  # Text — validated by content check
    "txt": [],  # Text
    "png": [(0, b"\x89PNG\r\n\x1a\n")],
    "jpg": [(0, b"\xff\xd8\xff")],
    "jpeg": [(0, b"\xff\xd8\xff")],
    "gif": [(0, b"GIF8")],
    "webp": [(8, b"WEBP")],
}

# Dangerous magic bytes — block regardless of extension
DANGEROUS_MAGIC = [
    (b"MZ", "PE executable (EXE/DLL)"),
    (b"\x7fELF", "ELF executable (Linux binary)"),
    (b"#!", "Shell script"),
    (b"\xca\xfe\xba\xbe", "Mach-O executable (macOS)"),
    (b"\xfe\xed\xfa", "Mach-O executable (macOS)"),
    (b"\xcf\xfa\xed\xfe", "Mach-O executable (macOS 64-bit)"),
]

# Blocked file extensions
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".msi", ".scr", ".dll", ".com", ".pif",
    ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".ps1", ".psm1",
    ".sh", ".bash", ".csh", ".ksh", ".app", ".action", ".command",
    ".inf", ".reg", ".lnk", ".hta", ".cpl", ".msc", ".jar",
}

# Allowed extensions for resume/document uploads
ALLOWED_RESUME_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ALLOWED_BULK_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".xlsx", ".xls", ".csv", ".zip"}

# Max file sizes (in bytes)
MAX_RESUME_SIZE = 10 * 1024 * 1024  # 10MB
MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5MB
MAX_BULK_SIZE = 50 * 1024 * 1024   # 50MB


def _get_extension(filename: str) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def _check_dangerous_magic(header: bytes) -> Optional[str]:
    """Check if file header matches known dangerous patterns."""
    for magic, desc in DANGEROUS_MAGIC:
        if header.startswith(magic):
            return desc
    return None


def _check_valid_magic(header: bytes, ext: str) -> bool:
    """Check if file header matches expected magic bytes for the extension."""
    clean_ext = ext.lstrip(".")
    if clean_ext not in MAGIC_BYTES:
        return True  # Unknown extension — allow (blocked ext check handles dangerous ones)
    patterns = MAGIC_BYTES[clean_ext]
    if not patterns:
        return True  # Text files have no magic bytes
    for offset, magic in patterns:
        if len(header) > offset and header[offset:offset + len(magic)] == magic:
            return True
    return False


async def validate_upload(
    file_content: bytes,
    filename: str,
    allowed_extensions: set = None,
    max_size: int = MAX_RESUME_SIZE,
) -> Tuple[bool, Optional[str]]:
    """
    Validate an uploaded file.
    Returns (is_valid, error_message).
    """
    if allowed_extensions is None:
        allowed_extensions = ALLOWED_RESUME_EXTENSIONS

    # 1. Check file size
    if len(file_content) > max_size:
        return False, f"File too large: {len(file_content) // (1024*1024)}MB exceeds {max_size // (1024*1024)}MB limit"

    # 2. Check extension
    ext = _get_extension(filename)
    if ext in BLOCKED_EXTENSIONS:
        logger.warning(f"[FILE_SECURITY] Blocked dangerous extension: {filename}")
        return False, f"File type '{ext}' is not allowed for security reasons"

    if ext not in allowed_extensions:
        return False, f"File type '{ext}' not accepted. Allowed: {', '.join(sorted(allowed_extensions))}"

    # 3. Check for dangerous magic bytes (catches renamed executables)
    header = file_content[:16] if len(file_content) >= 16 else file_content
    danger = _check_dangerous_magic(header)
    if danger:
        logger.warning(f"[FILE_SECURITY] Blocked malware upload: {filename} detected as {danger}")
        return False, f"File rejected: detected as {danger}. Only documents are allowed."

    # 4. Validate magic bytes match claimed extension
    if not _check_valid_magic(header, ext):
        logger.warning(f"[FILE_SECURITY] Magic byte mismatch: {filename} (ext={ext})")
        return False, f"File content doesn't match '{ext}' format. File may be corrupted or mislabeled."

    # 5. Check for empty files
    if len(file_content) == 0:
        return False, "Empty file uploaded"

    return True, None
