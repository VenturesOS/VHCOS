"""Offline archive verification; no application config or live requests."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("extension_test_builder", ROOT / "backend/scripts/build_test_extension.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.mark.parametrize("url", ["https://api.ventureshrd.com", "https://vhc.in", "https://talent-relay.siddharth-ab8.workers.dev",
                                 "https://preview.test/api", "https://user:secret@preview.test", "http://preview.test"])
def test_rejects_production_or_invalid_preview(url):
    with pytest.raises(ValueError):
        builder.backend_origin(url)


def test_archive_is_loadable_separate_from_production_and_reproducibly_auditable(tmp_path):
    source = ROOT / "browser-extension"
    before = {name: (source / name).read_bytes() for name in ("manifest.json", "background.js", "content.js", "popup.html", "popup.js")}
    archive = builder.build(tmp_path)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["name"] == "VHC Identity TEST - Emergent"
        assert "update_url" not in manifest and "key" not in manifest
        assert "<all_urls>" not in manifest["host_permissions"]
        assert not any(host in str(manifest["host_permissions"]) for host in builder.PRODUCTION)
        references = [manifest["background"]["service_worker"], manifest["action"]["default_popup"], manifest["options_page"]]
        references.extend(manifest["icons"].values())
        for entry in manifest["content_scripts"]:
            references.extend(entry.get("js", []) + entry.get("css", []))
        for name in references:
            assert name in bundle.namelist(), name
        for page in ("popup.html", "test-report.html"):
            for script in re.findall(r'<script src="([^"]+)"', bundle.read(page).decode()):
                assert script in bundle.namelist(), script
        assert 'id="apiUrl" placeholder="Enter your Emergent preview URL" value=""' in bundle.read("popup.html").decode()
        assert "checkForExtensionUpdate().catch" not in bundle.read("popup.js").decode()
        assert "autoCapture: true" not in bundle.read("content.js").decode()
        assert "if (wasContextMenu || isBackground)" not in bundle.read("background.js").decode()
        contents = json.loads(bundle.read("BUILD-CONTENTS.json"))
        for name, digest in contents["sha256"].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == digest
        assert not any(name.endswith((".pem", ".env")) or "/tests/" in name for name in bundle.namelist())
    assert before == {name: (source / name).read_bytes() for name in before}
    with pytest.raises(FileExistsError):
        builder.build(tmp_path)


def test_custom_preview_is_added_to_configuration_and_permissions(tmp_path):
    archive = builder.build(tmp_path, "https://stage.example.test")
    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        assert "https://stage.example.test/*" in manifest["host_permissions"]
        assert 'value="https://stage.example.test"' in bundle.read("popup.html").decode()
