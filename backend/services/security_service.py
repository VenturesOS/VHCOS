"""
VHC Talent OS — Security Service
File validation, content scanning, ClamAV integration, security event logging, Turnstile verification.
"""
import uuid
import struct
import socket
import logging
import asyncio
import zipfile
import io
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from config import db

logger = logging.getLogger(__name__)

# ─── Allowed file types ───
ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
PARSE_TIMEOUT = 15  # seconds

# ─── ClamAV Configuration ───
CLAMAV_HOST = os.environ.get("CLAMAV_HOST", "")
CLAMAV_PORT = int(os.environ.get("CLAMAV_PORT", "3310"))
CLAMAV_ENABLED = os.environ.get("CLAMAV_ENABLED", "false").lower() == "true"

# Magic byte signatures for file type validation
MAGIC_BYTES = {
    ".pdf": [b"%PDF"],
    ".doc": [b"\xd0\xcf\x11\xe0"],  # OLE2 compound format
    ".docx": [b"PK\x03\x04", b"PK\x05\x06"],  # ZIP (OOXML)
}

# Suspicious patterns in file content
SUSPICIOUS_PATTERNS = [
    b"<script", b"javascript:", b"eval(", b"document.cookie",
    b"onerror=", b"onload=", b"<iframe", b"<object",
    b"/Launch", b"/JavaScript", b"/JS ", b"/OpenAction",  # PDF-specific
]


def validate_file_extension(filename: str) -> tuple:
    """Check if file extension is allowed. Returns (valid, extension)."""
    if not filename:
        return False, ""
    ext = Path(filename).suffix.lower()
    return ext in ALLOWED_EXTENSIONS, ext


def validate_file_size(content: bytes) -> bool:
    """Check if file is within size limit."""
    return len(content) <= MAX_FILE_SIZE


def validate_magic_bytes(content: bytes, expected_ext: str) -> bool:
    """Verify file content matches its claimed extension via magic bytes."""
    if not content or len(content) < 8:
        return False
    signatures = MAGIC_BYTES.get(expected_ext, [])
    if not signatures:
        return False
    for sig in signatures:
        if content[:len(sig)] == sig:
            return True
    return False


def scan_for_threats(content: bytes, filename: str) -> list:
    """Scan file content for suspicious patterns. Returns list of threats found."""
    threats = []
    content_lower = content[:50000].lower()  # scan first 50KB

    for pattern in SUSPICIOUS_PATTERNS:
        if pattern.lower() in content_lower:
            threats.append(f"suspicious_pattern:{pattern.decode('utf-8', errors='ignore')}")

    ext = Path(filename).suffix.lower()

    # DOCX-specific: check for macros
    if ext == ".docx":
        try:
            zf = zipfile.ZipFile(io.BytesIO(content))
            names = zf.namelist()
            if any("vbaProject" in n or "macro" in n.lower() for n in names):
                threats.append("macro_detected")
            zf.close()
        except Exception:
            pass

    # Check for embedded executables
    exe_sigs = [b"MZ", b"\x7fELF"]  # PE and ELF
    for sig in exe_sigs:
        if sig in content[:100000]:
            threats.append("embedded_executable")
            break

    return threats


async def scan_with_clamav(content: bytes, filename: str) -> dict:
    """
    Scan file content using ClamAV daemon via INSTREAM protocol.
    Returns {"clean": bool, "result": str, "available": bool}
    """
    if not CLAMAV_ENABLED or not CLAMAV_HOST:
        return {"clean": True, "result": "scanner_not_configured", "available": False}

    try:
        loop = asyncio.get_event_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, _clamav_instream, content),
            timeout=30
        )
        return result
    except asyncio.TimeoutError:
        await log_security_event("clamav_timeout", "system", "MEDIUM",
                                 f"ClamAV scan timed out for {filename}")
        return {"clean": True, "result": "scan_timeout", "available": True}
    except Exception as e:
        await log_security_event("clamav_error", "system", "MEDIUM",
                                 f"ClamAV error: {str(e)[:200]}", {"filename": filename})
        return {"clean": True, "result": f"scan_error: {str(e)[:100]}", "available": False}


def _clamav_instream(content: bytes) -> dict:
    """Synchronous ClamAV INSTREAM scan via socket."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect((CLAMAV_HOST, CLAMAV_PORT))

        # INSTREAM protocol: send zINSTREAM\0, then chunks, then zero-length chunk
        sock.send(b"zINSTREAM\0")

        # Send content in chunks (max 2048 bytes each)
        chunk_size = 2048
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            sock.send(struct.pack("!L", len(chunk)) + chunk)

        # End with zero-length chunk
        sock.send(struct.pack("!L", 0))

        # Read response
        response = b""
        while True:
            data = sock.recv(4096)
            if not data:
                break
            response += data

        sock.close()
        response_str = response.decode("utf-8", errors="ignore").strip()

        if "OK" in response_str and "FOUND" not in response_str:
            return {"clean": True, "result": "clean", "available": True}
        elif "FOUND" in response_str:
            return {"clean": False, "result": response_str, "available": True}
        else:
            return {"clean": True, "result": response_str, "available": True}

    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        return {"clean": True, "result": f"daemon_unavailable: {str(e)[:100]}", "available": False}


async def check_clamav_health() -> dict:
    """Check if ClamAV daemon is reachable. For health monitoring."""
    if not CLAMAV_ENABLED or not CLAMAV_HOST:
        return {"status": "disabled", "available": False}
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _clamav_ping)
        return result
    except Exception as e:
        return {"status": "error", "available": False, "error": str(e)[:200]}


def _clamav_ping() -> dict:
    """Ping ClamAV daemon."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((CLAMAV_HOST, CLAMAV_PORT))
        sock.send(b"zPING\0")
        response = sock.recv(1024).decode("utf-8", errors="ignore").strip()
        sock.close()
        if "PONG" in response:
            return {"status": "healthy", "available": True}
        return {"status": "warning", "available": True, "response": response}
    except (ConnectionRefusedError, socket.timeout, OSError) as e:
        return {"status": "unavailable", "available": False, "error": str(e)[:100]}


def sanitize_text(text: str) -> str:
    """Sanitize extracted CV text to prevent XSS."""
    if not text:
        return ""
    import html
    sanitized = html.escape(text)
    # Remove any remaining script-like patterns
    import re
    sanitized = re.sub(r'(?i)<\s*script[^>]*>.*?<\s*/\s*script\s*>', '', sanitized)
    sanitized = re.sub(r'(?i)javascript\s*:', '', sanitized)
    sanitized = re.sub(r'(?i)on\w+\s*=', '', sanitized)
    return sanitized


async def validate_upload(content: bytes, filename: str, client_ip: str) -> dict:
    """
    Full upload validation pipeline.
    Returns {"valid": bool, "reason": str, "threats": list}
    """
    # 1. Extension check
    ext_valid, ext = validate_file_extension(filename)
    if not ext_valid:
        await log_security_event("invalid_file_type", client_ip, "HIGH",
                                 f"Rejected file type: {ext or 'none'}", {"filename": filename})
        return {"valid": False, "reason": f"File type '{ext}' not allowed. Only PDF, DOC, DOCX accepted.", "threats": []}

    # 2. Size check
    if not validate_file_size(content):
        size_mb = round(len(content) / 1048576, 1)
        await log_security_event("file_too_large", client_ip, "MEDIUM",
                                 f"File too large: {size_mb}MB", {"filename": filename, "size_mb": size_mb})
        return {"valid": False, "reason": f"File too large ({size_mb}MB). Maximum is 5MB.", "threats": []}

    # 3. Magic byte validation
    if not validate_magic_bytes(content, ext):
        await log_security_event("file_type_mismatch", client_ip, "HIGH",
                                 f"File content doesn't match extension {ext}", {"filename": filename})
        return {"valid": False, "reason": "File content doesn't match its extension. Upload rejected.", "threats": []}

    # 4. Pattern-based threat scan
    threats = scan_for_threats(content, filename)
    if threats:
        await log_security_event("malware_detected", client_ip, "CRITICAL",
                                 f"Threats found: {', '.join(threats[:5])}", {"filename": filename, "threats": threats})
        return {"valid": False, "reason": "File contains suspicious content and has been rejected.", "threats": threats}

    # 5. ClamAV virus scan (optional — graceful fallback)
    clam_result = await scan_with_clamav(content, filename)
    if not clam_result["available"] and CLAMAV_ENABLED:
        await log_security_event("clamav_unavailable", client_ip, "MEDIUM",
                                 f"ClamAV scanner unavailable for upload: {filename}",
                                 {"filename": filename, "result": clam_result["result"]})
    if not clam_result["clean"]:
        await log_security_event("virus_detected", client_ip, "CRITICAL",
                                 f"ClamAV virus detected: {clam_result['result'][:200]}",
                                 {"filename": filename, "scan_result": clam_result["result"]})
        return {"valid": False, "reason": "File flagged by virus scanner. Upload rejected.", "threats": [clam_result["result"]]}

    return {"valid": True, "reason": "", "threats": []}


async def safe_parse_with_timeout(parse_fn, *args, timeout=PARSE_TIMEOUT):
    """Run parser with timeout and memory protection."""
    try:
        result = await asyncio.wait_for(parse_fn(*args), timeout=timeout)
        return result
    except asyncio.TimeoutError:
        await log_security_event("parser_timeout", "system", "MEDIUM",
                                 f"CV parser exceeded {timeout}s timeout")
        return None
    except MemoryError:
        await log_security_event("parser_memory", "system", "HIGH", "CV parser ran out of memory")
        return None
    except Exception as e:
        await log_security_event("parser_crash", "system", "MEDIUM",
                                 f"CV parser crashed: {str(e)[:200]}")
        return None


# ─── Cloudflare Turnstile ───
import os
import httpx

TURNSTILE_SECRET = os.environ.get("TURNSTILE_SECRET_KEY", "")
TURNSTILE_ENABLED = bool(TURNSTILE_SECRET)


async def verify_turnstile(token: str, client_ip: str) -> bool:
    """Verify Cloudflare Turnstile CAPTCHA token."""
    if not TURNSTILE_ENABLED:
        return True  # Skip if not configured
    if not token:
        await log_security_event("captcha_missing", client_ip, "MEDIUM", "Turnstile token missing")
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://challenges.cloudflare.com/turnstile/v0/siteverify", data={
                "secret": TURNSTILE_SECRET,
                "response": token,
                "remoteip": client_ip,
            }, timeout=5)
            data = resp.json()
            if not data.get("success"):
                await log_security_event("captcha_failed", client_ip, "MEDIUM",
                                         "Turnstile verification failed", {"errors": data.get("error-codes", [])})
                return False
            return True
    except Exception as e:
        logger.error(f"[SECURITY] Turnstile verification error: {e}")
        return True  # Fail open to not block legitimate users


# ─── Security Event Logger ───

async def log_security_event(event_type: str, ip_address: str, severity: str,
                             detail: str, metadata: dict = None):
    """Log a security event for monitoring."""
    try:
        doc = {
            "id": str(uuid.uuid4()),
            "event_type": event_type,
            "ip_address": ip_address,
            "severity": severity,
            "detail": detail[:500],
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await db.security_events.insert_one(doc)
    except Exception as e:
        logger.error(f"[SECURITY] Failed to log event: {e}")


async def get_security_summary(hours=24):
    """Get security event summary for dashboard."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": {"type": "$event_type", "severity": "$severity"}, "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    results = await db.security_events.aggregate(pipeline).to_list(50)
    total = sum(r["count"] for r in results)
    critical = sum(r["count"] for r in results if r["_id"]["severity"] == "CRITICAL")
    high = sum(r["count"] for r in results if r["_id"]["severity"] == "HIGH")
    by_type = {}
    for r in results:
        t = r["_id"]["type"]
        by_type[t] = by_type.get(t, 0) + r["count"]
    return {"total": total, "critical": critical, "high": high, "by_type": by_type}
