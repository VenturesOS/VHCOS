#!/usr/bin/env python3
"""
Build a Chrome Web Store-ready ZIP from /app/browser-extension.

Differences vs. the dev / load-unpacked install:
  • Strips `update_url` from manifest.json (Web Store handles updates)
  • Removes the `<all_urls>` host_permission (Web Store reviewers reject it)
  • Removes preview-only domains (*.emergentagent.com, *.emergent.host)
  • Excludes legacy `content.v*.js` files, .pem, READMEs, and dotfiles
  • Output is a single .zip ready for upload at chrome.google.com/webstore/devconsole

Usage:
    python3 backend/scripts/build_webstore_zip.py \
        --source /app/browser-extension \
        --out   /app/backend/static/extensions

The script prints the final zip path. Upload that file to the Web Store.
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# Hosts that should NOT ship in a public Web Store listing
PRIVATE_HOST_PATTERNS = [
    re.compile(r"emergentagent\.com"),
    re.compile(r"emergent\.host"),
]

# Hosts allowed in the production listing
PROD_HOSTS = [
    "https://www.naukri.com/*",
    "https://naukri.com/*",
    "https://*.naukri.com/*",
    "https://www.linkedin.com/*",
    "https://linkedin.com/*",
    "https://www.foundit.in/*",
    "https://foundit.in/*",
    "https://*.foundit.in/*",
    "https://www.foundit.sg/*",
    "https://*.foundit.sg/*",
    "https://www.foundit.my/*",
    "https://*.foundit.my/*",
    "https://www.monster.com/*",
    "https://*.monster.com/*",
    "https://*.vhc.in/*",
    "https://*.ventureshrd.com/*",
]

EXCLUDE_FILE_PATTERNS = [
    re.compile(r"^content\.v\d.*\.js$"),  # legacy versions
    re.compile(r"\.pem$"),
    re.compile(r"^README"),
    re.compile(r"^\."),
    re.compile(r".*\.bak$"),
]


def _scrub_manifest(src: dict) -> dict:
    out = dict(src)
    out.pop("update_url", None)  # Web Store provides its own update URL

    # host_permissions: keep only PROD_HOSTS, drop <all_urls> + preview domains
    if "host_permissions" in out:
        cleaned = []
        for h in PROD_HOSTS:
            if h not in cleaned:
                cleaned.append(h)
        out["host_permissions"] = cleaned

    # web_accessible_resources: strip private domains in matches
    if "web_accessible_resources" in out:
        for war in out["web_accessible_resources"]:
            if "matches" in war:
                war["matches"] = [
                    m for m in war["matches"]
                    if not any(p.search(m) for p in PRIVATE_HOST_PATTERNS)
                ]

    # content_scripts: drop any matcher that points at a preview domain
    for cs in out.get("content_scripts", []):
        cs["matches"] = [
            m for m in cs.get("matches", [])
            if not any(p.search(m) for p in PRIVATE_HOST_PATTERNS)
        ]
    return out


def _should_exclude(path: Path) -> bool:
    name = path.name
    if any(p.search(name) for p in EXCLUDE_FILE_PATTERNS):
        return True
    if "__pycache__" in path.parts or "node_modules" in path.parts:
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="/app/browser-extension")
    ap.add_argument("--out", default="/app/backend/static/extensions")
    args = ap.parse_args()

    src = Path(args.source).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not (src / "manifest.json").exists():
        print(f"ERROR: {src}/manifest.json not found", file=sys.stderr)
        sys.exit(1)

    # 1. Load + scrub manifest
    manifest_src = json.loads((src / "manifest.json").read_text())
    manifest_clean = _scrub_manifest(manifest_src)
    version = manifest_clean.get("version", "0.0.0")

    # 2. Stage in a temp dir
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for entry in src.rglob("*"):
            if not entry.is_file() or _should_exclude(entry):
                continue
            if entry.name == "manifest.json":
                continue  # we'll write the scrubbed copy
            rel = entry.relative_to(src)
            dst = tmp_path / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, dst)

        (tmp_path / "manifest.json").write_text(
            json.dumps(manifest_clean, indent=2)
        )

        # 3. Zip
        zip_path = out_dir / f"vhc-naukri-extension-webstore-v{version}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in tmp_path.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(tmp_path))

    print(f"\n✅ Web Store zip built: {zip_path}")
    print(f"   Version: {version}")
    print(f"   Size:    {zip_path.stat().st_size / 1024:.1f} KB")
    print(f"\nUpload this file at: https://chrome.google.com/webstore/devconsole/")


if __name__ == "__main__":
    main()
