"""
Chrome Extension Auto-Update Endpoints.

Routes:
- GET /api/extension/update.xml?id=<extId>   — Chrome polls every ~5h for new versions
- GET /api/extension/download.crx?v=<ver>    — Serves the signed CRX binary
- GET /api/extension/latest-version          — Public JSON (used by frontend install page)
- GET /api/extension/version-stats           — Admin only (version distribution across recruiters)
- POST /api/extension/checkin                — Extension calls this on startup to register its version

No authentication needed on update.xml and download.crx (Chrome's update service can't auth).
CRX files are safe to serve publicly — they're signed by our private key, so anyone can download
but only we can publish updates.
"""
import logging
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

from utils.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/extension", tags=["Extension Auto-Update"])

# Where CRX builder writes its output — resolved at import time with dev+prod fallback
def _resolve_extensions_dir() -> Path:
    env = os.environ.get("EXTENSIONS_DIR")
    if env:
        return Path(env)
    backend_dir = Path(__file__).resolve().parent.parent
    for p in [Path("/app/backend/static/extensions"), backend_dir / "static" / "extensions"]:
        if p.exists():
            return p
    # Default (may not exist yet on first build)
    return backend_dir / "static" / "extensions"

EXTENSIONS_DIR = _resolve_extensions_dir()


def _locate_manifest() -> Optional[Path]:
    """Find the browser-extension manifest across dev + prod layouts."""
    env_override = os.environ.get("BROWSER_EXTENSION_DIR")
    if env_override:
        p = Path(env_override) / "manifest.json"
        if p.exists():
            return p
    # Candidate locations — dev container first, then EC2 prod, then relative discovery
    backend_dir = Path(__file__).resolve().parent.parent  # /.../backend
    project_root = backend_dir.parent                      # /.../vhc-platform or /app
    candidates = [
        Path("/app/browser-extension/manifest.json"),
        project_root / "browser-extension" / "manifest.json",
        backend_dir.parent / "browser-extension" / "manifest.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


async def get_db():
    from config import db
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Public endpoints (called by Chrome + extension itself)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/update.xml", include_in_schema=False)
async def extension_update_xml():
    """Google Omaha v3 update manifest — Chrome polls this every ~5 hours."""
    xml_path = EXTENSIONS_DIR / "update.xml"
    if not xml_path.exists():
        # Graceful empty response — no update available
        body = (
            "<?xml version='1.0' encoding='UTF-8'?>\n"
            "<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'></gupdate>\n"
        )
        return Response(content=body, media_type="application/xml")
    return FileResponse(xml_path, media_type="application/xml")


@router.get("/download.crx", include_in_schema=False)
async def extension_download_crx(v: Optional[str] = Query(None)):
    """Serve the signed CRX file. Chrome calls this after reading update.xml.
    Falls back to 'latest' if no specific version requested.
    """
    if v:
        path = EXTENSIONS_DIR / f"vhc-naukri-extension-v{v}.crx"
        if path.exists():
            return FileResponse(
                path,
                media_type="application/x-chrome-extension",
                filename=path.name,
            )
    latest = EXTENSIONS_DIR / "vhc-naukri-extension-latest.crx"
    if latest.exists():
        return FileResponse(
            latest,
            media_type="application/x-chrome-extension",
            filename="vhc-naukri-extension.crx",
        )
    raise HTTPException(status_code=404, detail="No CRX file built yet. Run scripts/build_extension_crx.py")


@router.get("/download-webstore-zip", include_in_schema=False)
async def extension_download_webstore_zip(user=Depends(get_current_user)):
    """Serve the Chrome Web Store-ready ZIP. Admin-authenticated only — this is
    the artifact you upload at chrome.google.com/webstore/devconsole/.
    Stripped of update_url and <all_urls> by build_webstore_zip.py.
    """
    role = (user.get("role") or "").lower() if user else ""
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    # Pick the freshest webstore zip by mtime
    candidates = sorted(
        EXTENSIONS_DIR.glob("vhc-naukri-extension-webstore-v*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="No Web Store zip built yet. Run scripts/build_webstore_zip.py first.",
        )
    return FileResponse(
        candidates[0],
        media_type="application/zip",
        filename=candidates[0].name,
    )


@router.get("/install-policy.reg", include_in_schema=False)
async def extension_install_policy_reg():
    """Windows Registry file that whitelists this extension for force-install.

    Recruiters download this, double-click it, restart Chrome — after which
    drag-drop CRX install works AND Chrome auto-updates silently.

    Background: since 2018, Chrome blocks drag-drop install of self-hosted CRX
    ('CRX_REQUIRED_PROOF_MISSING') unless an enterprise policy explicitly trusts
    the extension. ExtensionInstallForcelist does exactly that.
    """
    # Resolve the extension ID at request time (may change across rebuilds)
    ext_id_file = EXTENSIONS_DIR / "extension_id.txt"
    if not ext_id_file.exists():
        raise HTTPException(status_code=404, detail="Extension not built yet")
    ext_id = ext_id_file.read_text().strip()

    # Derive the update.xml URL from request headers (so dev + prod both work)
    # Falls back to api.ventureshrd.com for the installed production default.
    update_url = "https://api.ventureshrd.com/api/extension/update.xml"

    # Windows Registry format — ONE key per line, escaped for REGEDIT4
    reg_content = f"""Windows Registry Editor Version 5.00

; VHC Talent OS — Chrome Extension Install Policy v2
; Makes the machine's Chrome trust + auto-install our self-hosted extension.
; After importing, RESTART CHROME COMPLETELY (close all windows + tray).
;
; Policies set:
;  - ExtensionInstallForcelist : force-install + auto-update our extension
;  - ExtensionInstallSources   : allow drag-drop install from our domains
;  - ExtensionAllowedTypes     : allow 'extension' type (not just themes/apps)
;  - BlockExternalExtensions   : 0 = allow externally-hosted CRX
;  - ExtensionSettings         : override Web Store-only restriction per extension

[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Google\\Chrome]
"BlockExternalExtensions"=dword:00000000

[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Google\\Chrome\\ExtensionInstallForcelist]
"1"="{ext_id};{update_url}"

[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Google\\Chrome\\ExtensionInstallSources]
"1"="https://api.ventureshrd.com/*"
"2"="https://ventureshrd.com/*"

[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Google\\Chrome\\ExtensionAllowedTypes]
"1"="extension"

; ExtensionSettings is the modern way (Chrome 75+) — explicitly trusts our ext ID
; and overrides the "Web Store only" default for personal Windows machines.
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Google\\Chrome\\ExtensionSettings\\{ext_id}]
"installation_mode"="force_installed"
"update_url"="{update_url}"
"override_update_url"=dword:00000001
"""
    return Response(
        content=reg_content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": 'attachment; filename="vhc-extension-install-policy.reg"'},
    )


@router.get("/install-policy.json", include_in_schema=False)
async def extension_install_policy_json():
    """Machine-readable version of the install policy for admin dashboards."""
    ext_id_file = EXTENSIONS_DIR / "extension_id.txt"
    if not ext_id_file.exists():
        raise HTTPException(status_code=404, detail="Extension not built yet")
    return {
        "extension_id": ext_id_file.read_text().strip(),
        "update_url": "https://api.ventureshrd.com/api/extension/update.xml",
        "download_url": "https://api.ventureshrd.com/api/extension/install-policy.reg",
        "note": "Windows: download .reg file, double-click, restart Chrome. Mac: see /api/extension/install-policy-mac (coming soon).",
    }


@router.get("/latest-version")
async def latest_version():
    """Public JSON read by the frontend install page."""
    manifest_path = _locate_manifest()
    if not manifest_path or not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Extension manifest not found")
    import json
    m = json.loads(manifest_path.read_text())
    crx_exists = (EXTENSIONS_DIR / "vhc-naukri-extension-latest.crx").exists()
    ext_id_file = EXTENSIONS_DIR / "extension_id.txt"
    ext_id = ext_id_file.read_text().strip() if ext_id_file.exists() else None
    return {
        "version": m.get("version"),
        "name": m.get("name"),
        "crx_available": crx_exists,
        "crx_url": "/api/extension/download.crx" if crx_exists else None,
        "zip_url": "/api/download/naukri-extension",  # legacy unpacked install — still works
        "extension_id": ext_id,
        "update_url": m.get("update_url"),
    }


@router.post("/checkin")
async def extension_checkin(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Extension sends {version, install_type} on startup. We record it so
    admins can see version distribution. Cheap: one upsert per user.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}
    version = (body.get("version") or "unknown").strip()[:32]
    install_type = (body.get("install_type") or "unknown").strip()[:32]
    ua = request.headers.get("user-agent", "")[:200]
    now = datetime.now(timezone.utc).isoformat()

    await db.extension_checkins.update_one(
        {"user_id": current_user["id"]},
        {
            "$set": {
                "user_id": current_user["id"],
                "user_email": current_user.get("email"),
                "user_name": current_user.get("name"),
                "user_role": current_user.get("role"),
                "version": version,
                "install_type": install_type,
                "user_agent": ua,
                "last_seen": now,
            },
            "$setOnInsert": {"first_seen": now},
        },
        upsert=True,
    )
    # Backend can tell extension "please upgrade" by returning this flag.
    # For now we never force-upgrade — customer said: don't break existing users.
    manifest_path = _locate_manifest()
    latest = None
    if manifest_path and manifest_path.exists():
        import json
        try: latest = json.loads(manifest_path.read_text()).get("version")
        except: pass
    return {
        "ok": True,
        "latest_version": latest,
        "upgrade_required": False,
        "your_version": version,
    }


@router.get("/my-version-status")
async def my_version_status(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Used by the web app's login banner.
    Returns whether the logged-in user's installed extension is behind the
    latest published version. 'ever_installed' tells the frontend not to
    nag users who never installed the extension at all.
    """
    # Latest version from source manifest
    import json as _json
    manifest_path = _locate_manifest()
    latest_version = None
    if manifest_path and manifest_path.exists():
        try:
            latest_version = _json.loads(manifest_path.read_text()).get("version")
        except Exception:
            pass

    checkin = await db.extension_checkins.find_one(
        {"user_id": current_user["id"]},
        {"_id": 0, "version": 1, "last_seen": 1, "install_type": 1},
    )
    your_version = (checkin or {}).get("version") or None
    ever_installed = your_version is not None

    def _parse(v):
        try:
            return tuple(int(x) for x in (v or "0").split("."))
        except Exception:
            return (0,)

    is_stale = bool(
        ever_installed
        and latest_version
        and _parse(your_version) < _parse(latest_version)
    )

    return {
        "your_version": your_version,
        "latest_version": latest_version,
        "is_stale": is_stale,
        "ever_installed": ever_installed,
        "last_seen": (checkin or {}).get("last_seen"),
        "install_type": (checkin or {}).get("install_type"),
        "download_url": "/api/download/naukri-extension",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Admin version-distribution
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/version-stats")
async def version_stats(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Admin-only: who's on which version, last-seen timestamps."""
    if (current_user.get("role") or "").lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    # Rows
    users = await db.extension_checkins.find({}, {"_id": 0}).sort("last_seen", -1).to_list(500)

    # Bucket by version
    buckets = {}
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    stale = 0
    for u in users:
        v = u.get("version") or "unknown"
        buckets[v] = buckets.get(v, 0) + 1
        if (u.get("last_seen") or "") < stale_cutoff:
            stale += 1

    # Latest
    manifest_path = _locate_manifest()
    latest_version = None
    if manifest_path and manifest_path.exists():
        import json
        try: latest_version = json.loads(manifest_path.read_text()).get("version")
        except: pass

    return {
        "total_recruiters": len(users),
        "latest_version": latest_version,
        "by_version": [{"version": k, "count": v} for k, v in sorted(buckets.items(), key=lambda x: -x[1])],
        "stale_over_7d": stale,
        "users": users,
    }
