"""Build an unpacked extension ZIP for Emergent testing, without editing source.

Usage: python backend/scripts/build_test_extension.py --out /path/to/outputs
Optional: --backend-url https://your-preview.example (base origin, no /api).
Artifacts use a TEST name, no update URL and explicit preview login.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse
import zipfile

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "tools" / "extension-test-kit"
PRODUCTION = ("ventureshrd.com", "vhc.in", "talent-relay.siddharth-ab8.workers.dev")


def backend_origin(value):
    if not value:
        return ""
    url = urlparse(value)
    host = url.hostname or ""
    if any(host == item or host.endswith("." + item) for item in PRODUCTION):
        raise ValueError("Use a preview URL, not a production portal")
    if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
        raise ValueError("Provide a base URL with no credentials, path, query or /api")
    if url.scheme != "https" and not (url.scheme == "http" and host in ("localhost", "127.0.0.1")):
        raise ValueError("Use HTTPS, or HTTP on localhost")
    if not host:
        raise ValueError("Preview hostname required")
    return f"{url.scheme}://{url.netloc}"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Source changed; review test packaging transformation: " + old[:75])
    return text.replace(old, new, 1)


def build(out_dir, backend_url=""):
    origin = backend_origin(backend_url)
    source = ROOT / "browser-extension"
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    version = manifest["version"]
    manifest.update(name="VHC Identity TEST - Emergent", version_name=version + " test",
                    description="Preview-only identity matching and capture test with local performance report.",
                    options_page="test-report.html", background={"service_worker": "test-worker.js"})
    manifest.pop("update_url", None)
    manifest.pop("key", None)
    manifest["host_permissions"] = [entry for entry in manifest["host_permissions"]
                                    if entry != "<all_urls>" and not any(host in entry for host in PRODUCTION)]
    for entry in ["https://*.emergentagent.com/*", "https://*.emergent.host/*",
                  "https://*.emergent.sh/*", "http://localhost/*", "http://127.0.0.1/*"]:
        if entry not in manifest["host_permissions"]:
            manifest["host_permissions"].append(entry)
    if origin and origin + "/*" not in manifest["host_permissions"]:
        manifest["host_permissions"].append(origin + "/*")
    manifest["action"]["default_title"] = "VHC Identity TEST"
    files = {}
    for name in ("background.js", "content.js", "content.css", "hover-preview.js", "bg-visibility-shim.js", "popup.html", "popup.js"):
        files[name] = (source / name).read_bytes()
    for directory in ("icons", "vendor"):
        for file in (source / directory).rglob("*"):
            if file.is_file() and file.suffix.lower() in (".png", ".svg", ".js"):
                files[file.relative_to(source).as_posix()] = file.read_bytes()
    background = files["background.js"].decode("utf-8")
    background = replace_once(background, "autoCapture: true,", "autoCapture: false,")
    background = replace_once(background, "if (wasContextMenu || isBackground) {", "if (wasContextMenu) { // Test build: deliberate captures only.")
    files["background.js"] = background.encode("utf-8")
    content = files["content.js"].decode("utf-8")
    if "autoCapture: true" not in content:
        raise ValueError("Review test package auto-capture defaults")
    files["content.js"] = content.replace("autoCapture: true", "autoCapture: false").encode("utf-8")
    popup = files["popup.html"].decode("utf-8")
    popup, count = re.subn(r'<input type="url" id="apiUrl"[^>]*>',
        '<input type="url" id="apiUrl" placeholder="Enter your Emergent preview URL" value="' + html.escape(origin, quote=True) + '">', popup)
    if count != 1:
        raise ValueError("Preview login input not found")
    popup = replace_once(popup, "<h1>Ventures HRD</h1>", "<h1>VHC Identity TEST</h1>")
    popup = replace_once(popup, "<p>Naukri Auto Capture</p>", "<p>Emergent preview · manual capture</p>")
    popup = re.sub(r'(<span class="version-badge">)[^<]*(</span>)', r'\g<1>' + version + ' TEST' + r'\g<2>', popup)
    popup = replace_once(popup, '<script src="popup.js"></script>',
        '<p style="padding:12px;text-align:center"><a href="test-report.html" target="_blank">Open test performance report</a></p>\n'
        '<script src="test-config.js"></script><script src="test-runtime.js"></script><script src="popup.js"></script>')
    files["popup.html"] = popup.encode("utf-8")
    popup_js = files["popup.js"].decode("utf-8")
    popup_js = replace_once(popup_js, "checkForExtensionUpdate().catch(() => {});", "// Test package: production update checks disabled.")
    popup_js = replace_once(popup_js,
        "if (!apiUrl || !email || !password) { showLoginError('Please fill in all fields'); return; }",
        "if (!apiUrl || !email || !password) { showLoginError('Please fill in all fields'); return; }\n"
        "    if (!vhcTestBackendAllowed(apiUrl)) { showLoginError('Enter your Emergent preview URL; production is blocked in this test build.'); return; }")
    files["popup.js"] = popup_js.encode("utf-8")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    config = {"commit": commit, "backendOrigin": origin, "test_build": True, "version": version}
    files["test-config.js"] = ("globalThis.VHC_TEST_CONFIG = Object.freeze(" + json.dumps(config) + ");\n").encode()
    files["test-worker.js"] = b"importScripts('test-config.js', 'test-runtime.js', 'background.js', 'test-instrumentation.js');\n"
    for name in ("test-runtime.js", "test-instrumentation.js", "test-report.html", "test-report.js", "START-HERE.txt"):
        files[name] = (ASSETS / name).read_bytes()
    files["manifest.json"] = json.dumps(manifest, indent=2).encode()
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files["BUILD-CONTENTS.json"] = json.dumps({"config": config, "sha256": hashes}, indent=2).encode()
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / f"VHC-Identity-Test-{version}.zip"
    # Never silently replace a previous test build/report.
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(files.items()):
            bundle.writestr(name, data)
    return archive


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--backend-url", default="")
    args = parser.parse_args()
    archive = build(args.out, args.backend_url)
    print(json.dumps({"archive": str(archive), "bytes": archive.stat().st_size,
                      "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}, indent=2))
