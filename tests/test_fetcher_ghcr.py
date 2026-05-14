"""Tests for fetch_from_ghcr."""

import io
import json
import tarfile
from unittest.mock import MagicMock, patch

import pytest

from vtk_knowledge.artifact.fetcher import fetch_from_ghcr
from vtk_knowledge.schema.records import VTKDocRecord


def _make_layer_blob(filename: str, content: bytes) -> bytes:
    """Return a gzipped tar containing one file."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name=filename)
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _jsonl_bytes(*class_names: str) -> bytes:
    lines = [VTKDocRecord(class_name=n, module_name="vtkTest").model_dump_json() for n in class_names]
    return "\n".join(lines).encode()


def _mock_urlopen(token_resp: dict, manifest_resp: dict, blob: bytes):
    """Return a context-manager mock for urllib.request.urlopen."""
    responses = [
        json.dumps(token_resp).encode(),
        json.dumps(manifest_resp).encode(),
        blob,
    ]
    calls = iter(responses)

    def _open(req_or_url, **_kwargs):
        data = next(calls)
        cm = MagicMock()
        cm.__enter__ = lambda s: MagicMock(read=lambda: data)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    return _open


MANIFEST = {
    "schemaVersion": 2,
    "layers": [{"digest": "sha256:abc123", "size": 0, "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"}],
}


class TestFetchFromGhcr:
    def test_downloads_and_extracts_jsonl(self, tmp_path):
        blob = _make_layer_blob("vtk-knowledge.jsonl", _jsonl_bytes("vtkFoo", "vtkBar"))

        with patch(
            "vtk_knowledge.artifact.fetcher.urllib.request.urlopen",
            side_effect=_mock_urlopen({"token": "tok"}, MANIFEST, blob),
        ):
            path = fetch_from_ghcr("9.6.1", cache_dir=tmp_path)

        assert path.exists()
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        assert len(lines) == 2
        assert json.loads(lines[0])["class_name"] == "vtkFoo"

    def test_cached_file_skips_network(self, tmp_path):
        cached = tmp_path / "vtk-knowledge-9.6.1.jsonl"
        cached.write_text(VTKDocRecord(class_name="vtkCached", module_name="m").model_dump_json())

        with patch("vtk_knowledge.artifact.fetcher.urllib.request.urlopen") as mock_open:
            path = fetch_from_ghcr("9.6.1", cache_dir=tmp_path)
            mock_open.assert_not_called()

        assert path == cached

    def test_raises_on_network_error(self, tmp_path):
        with patch(
            "vtk_knowledge.artifact.fetcher.urllib.request.urlopen",
            side_effect=OSError("connection refused"),
        ):
            with pytest.raises(RuntimeError, match="Failed to pull"):
                fetch_from_ghcr("9.6.1", cache_dir=tmp_path)

    def test_raises_when_no_jsonl_in_layer(self, tmp_path):
        blob = _make_layer_blob("not-a-jsonl.txt", b"hello")

        with patch(
            "vtk_knowledge.artifact.fetcher.urllib.request.urlopen",
            side_effect=_mock_urlopen({"token": "tok"}, MANIFEST, blob),
        ):
            with pytest.raises(RuntimeError):
                fetch_from_ghcr("9.6.1", cache_dir=tmp_path)

    def test_custom_repository(self, tmp_path):
        blob = _make_layer_blob("vtk-knowledge.jsonl", _jsonl_bytes("vtkX"))
        captured_urls = []

        def _open(req_or_url, **_kwargs):
            url = req_or_url if isinstance(req_or_url, str) else req_or_url.full_url
            captured_urls.append(url)
            responses = [
                json.dumps({"token": "tok"}).encode(),
                json.dumps(MANIFEST).encode(),
                blob,
            ]
            data = responses[len(captured_urls) - 1]
            cm = MagicMock()
            cm.__enter__ = lambda s: MagicMock(read=lambda: data)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        with patch("vtk_knowledge.artifact.fetcher.urllib.request.urlopen", side_effect=_open):
            fetch_from_ghcr("9.6.1", repository="myorg/vtk-knowledge", cache_dir=tmp_path)

        assert "myorg/vtk-knowledge" in captured_urls[0]
        assert "myorg/vtk-knowledge" in captured_urls[1]
