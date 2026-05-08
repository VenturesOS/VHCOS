#!/usr/bin/env python3
"""
Build + sign a CRX3 Chrome extension package from the /app/browser-extension source.

Usage:
    python scripts/build_extension_crx.py \
        --source /app/browser-extension \
        --key /home/ubuntu/vhc-platform/backend/secrets/extension_key.pem \
        --out /app/backend/static/extensions \
        --version auto

- `--version auto` reads the current manifest.json
- If the key file doesn't exist, one is generated (ONLY run this once — re-generating changes
  the extension ID and breaks auto-update for all installed users!)

Outputs:
- <out>/vhc-naukri-extension-v<VERSION>.crx
- <out>/update.xml (auto-updated to point to latest)
- <out>/extension_id.txt (stable ID — show this in the frontend install instructions)
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path


def get_or_create_key(key_path: Path) -> bytes:
    """Load private key from disk. If it doesn't exist, generate & save one.
    The public-key hash becomes the extension's permanent Chrome ID — NEVER regenerate.
    """
    from crx3 import creator, key_util
    if key_path.exists():
        return key_path.read_bytes()
    print(f"[build-crx] ⚠️  Generating NEW private key at {key_path} — this is a one-time operation")
    print(f"[build-crx] ⚠️  The extension ID will be derived from this key. BACK IT UP SECURELY.")
    key_path.parent.mkdir(parents=True, exist_ok=True)
    creator.create_private_key_file(str(key_path))
    os.chmod(key_path, 0o600)
    return key_path.read_bytes()


def get_extension_id(key_pem: bytes) -> str:
    """Compute the 32-char Chrome extension ID from the public key."""
    from crx3 import key_util, id_util
    priv = key_util.load_private_key_from_pem(key_pem)
    pub = key_util.extract_public_key_from_private_key(priv)
    pub_der = key_util.get_public_key_data(pub)
    hex_id = id_util.calc_crx_id_by_public_key(pub_der)
    # crx3 v0.0.4 returns raw bytes — normalise to hex string
    if isinstance(hex_id, (bytes, bytearray)):
        hex_id = hex_id.hex()
    return id_util.convert_hex_crx_id_to_alphabet(hex_id)


def zip_source(source_dir: Path, output_zip: Path):
    """Zip the extension source, excluding hidden files + the private key if colocated."""
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in source_dir.rglob("*"):
            if not file_path.is_file():
                continue
            name = file_path.name
            # Exclude hidden, backups, caches, and the key itself
            if name.startswith(".") or name.endswith(".pem") or name.endswith(".bak"):
                continue
            if "__pycache__" in file_path.parts or "node_modules" in file_path.parts:
                continue
            zf.write(file_path, file_path.relative_to(source_dir))


def build_crx(zip_path: Path, key_path: Path, crx_path: Path):
    from crx3 import creator
    creator.create_crx_file(str(zip_path), str(key_path), str(crx_path))


def update_manifest_update_url(source_dir: Path, update_xml_url: str):
    """Patch manifest.json to set update_url → enables Chrome auto-update."""
    mpath = source_dir / "manifest.json"
    m = json.loads(mpath.read_text())
    if m.get("update_url") != update_xml_url:
        m["update_url"] = update_xml_url
        mpath.write_text(json.dumps(m, indent=2))
        print(f"[build-crx] Patched manifest.update_url → {update_xml_url}")


def write_update_xml(out_dir: Path, ext_id: str, version: str, crx_url: str):
    """Write a Google Chrome Extension Update XML (Omaha v3 minimal) with sha256 hash."""
    crx_file = out_dir / f"vhc-naukri-extension-v{version}.crx"
    sha256 = hashlib.sha256(crx_file.read_bytes()).hexdigest()
    xml = f"""<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='{ext_id}'>
    <updatecheck codebase='{crx_url}' version='{version}' hash_sha256='{sha256}' />
  </app>
</gupdate>
"""
    (out_dir / "update.xml").write_text(xml)
    print(f"[build-crx] Wrote update.xml for ext_id={ext_id} version={version}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="/app/browser-extension")
    parser.add_argument("--key", required=True, help="Path to private-key PEM (created if absent — DO NOT regenerate)")
    parser.add_argument("--out", default="/app/backend/static/extensions")
    parser.add_argument("--version", default="auto", help="Override manifest version, or 'auto'")
    parser.add_argument("--update-url", default=None,
                        help="Public URL Chrome will poll for updates (e.g. https://vhc.in/api/extension/update.xml). "
                             "Patches manifest.json.")
    parser.add_argument("--crx-base-url", default=None,
                        help="Public URL prefix where the .crx file will be served "
                             "(e.g. https://vhc.in/api/extension/download.crx).")
    parser.add_argument("--skip-manifest-patch", action="store_true",
                        help="Don't modify manifest.json's update_url (for CI re-runs)")
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    key_path = Path(args.key)

    # 1. Read manifest version
    manifest = json.loads((source / "manifest.json").read_text())
    version = manifest["version"] if args.version == "auto" else args.version

    # 2. Patch update_url in manifest (idempotent)
    if args.update_url and not args.skip_manifest_patch:
        update_manifest_update_url(source, args.update_url)

    # 3. Get/generate private key and derive extension ID
    key_pem = get_or_create_key(key_path)
    ext_id = get_extension_id(key_pem)
    print(f"[build-crx] Extension ID (stable): {ext_id}")

    # 4. Zip the source (temp)
    tmp_zip = out / f"_build_{version}.zip"
    zip_source(source, tmp_zip)

    # 5. Build CRX
    crx_path = out / f"vhc-naukri-extension-v{version}.crx"
    build_crx(tmp_zip, key_path, crx_path)
    tmp_zip.unlink()
    print(f"[build-crx] Built {crx_path.name} ({crx_path.stat().st_size} bytes)")

    # 6. Copy to 'latest' symlink so /download.crx always serves newest
    latest = out / "vhc-naukri-extension-latest.crx"
    if latest.exists():
        latest.unlink()
    shutil.copy2(crx_path, latest)

    # 7. Write update.xml
    crx_url = f"{args.crx_base_url}?v={version}" if args.crx_base_url else f"/api/extension/download.crx?v={version}"
    write_update_xml(out, ext_id, version, crx_url)

    # 8. Record extension ID
    (out / "extension_id.txt").write_text(ext_id)

    print(f"[build-crx] ✅ Done. Version {version}, ID {ext_id}")
    print(f"[build-crx]    CRX:        {crx_path}")
    print(f"[build-crx]    Latest:     {latest}")
    print(f"[build-crx]    update.xml: {out / 'update.xml'}")


if __name__ == "__main__":
    main()
