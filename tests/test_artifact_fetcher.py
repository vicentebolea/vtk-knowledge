"""Tests for vtk_knowledge.artifact.fetcher."""

import io
import json
import tarfile
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vtk_knowledge.artifact.fetcher import fetch_knowledge_artifact
from vtk_knowledge.index.api_index import VTKAPIIndex
from vtk_knowledge.schema.records import VTKDocRecord


class TestFetchKnowledgeArtifact:
    def test_returns_cached_file_without_download(self, tmp_path):
        cached = tmp_path / "vtk-knowledge-9.3.0.jsonl"
        cached.write_text('{"class_name": "vtkFoo", "module_name": "m"}\n')

        with patch("urllib.request.urlretrieve") as mock_dl:
            result = fetch_knowledge_artifact("9.3.0", cache_dir=tmp_path)
            mock_dl.assert_not_called()

        assert result == cached

    def test_downloads_when_not_cached(self, tmp_path):
        def fake_download(url, path):
            Path(path).write_text("{}\n")

        with patch("urllib.request.urlretrieve", side_effect=fake_download):
            result = fetch_knowledge_artifact("9.3.0", cache_dir=tmp_path)

        assert result.exists()
        assert result.name == "vtk-knowledge-9.3.0.jsonl"

    def test_raises_runtime_error_on_download_failure(self, tmp_path):
        with patch(
            "urllib.request.urlretrieve",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            with pytest.raises(RuntimeError, match="Failed to download"):
                fetch_knowledge_artifact("9.3.0", cache_dir=tmp_path)

    def test_creates_cache_dir(self, tmp_path):
        cache_dir = tmp_path / "new_cache_dir"
        assert not cache_dir.exists()

        def fake_download(url, path):
            Path(path).write_text("{}\n")

        with patch("urllib.request.urlretrieve", side_effect=fake_download):
            fetch_knowledge_artifact("9.3.0", cache_dir=cache_dir)

        assert cache_dir.exists()


def _layer_blob(*class_names: str, **fields) -> bytes:
    content = "\n".join(
        VTKDocRecord(class_name=n, module_name="m", **fields).model_dump_json() for n in class_names
    ).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="vtk-knowledge.jsonl")
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))
    return buf.getvalue()


def _urlopen_side_effect(blob: bytes):
    responses = iter(
        [
            json.dumps({"token": "t"}).encode(),
            json.dumps({"layers": [{"digest": "sha256:x"}]}).encode(),
            blob,
        ]
    )

    def _open(req_or_url, **_kw):
        data = next(responses)
        cm = MagicMock()
        cm.__enter__ = lambda s: MagicMock(read=lambda: data)
        cm.__exit__ = MagicMock(return_value=False)
        return cm

    return _open


class TestFromArtifact:
    def test_uses_ghcr_on_first_call(self, tmp_path):
        blob = _layer_blob("vtkActor", "vtkSphereSource")
        with patch(
            "vtk_knowledge.artifact.fetcher.urllib.request.urlopen",
            side_effect=_urlopen_side_effect(blob),
        ):
            idx = VTKAPIIndex.from_artifact("9.6.1", cache_dir=tmp_path)

        assert idx.has_class("vtkActor")
        assert idx.has_class("vtkSphereSource")
        assert len(idx.classes) == 2

    def test_serves_from_cache_without_network(self, tmp_path):
        record = VTKDocRecord(class_name="vtkCached", module_name="m")
        (tmp_path / "vtk-knowledge-9.6.1.jsonl").write_text(record.model_dump_json())

        with patch("vtk_knowledge.artifact.fetcher.urllib.request.urlopen") as mock_open:
            idx = VTKAPIIndex.from_artifact("9.6.1", cache_dir=tmp_path)
            mock_open.assert_not_called()

        assert idx.has_class("vtkCached")

    def test_cache_dir_arg_is_respected(self, tmp_path):
        custom = tmp_path / "custom_cache"
        blob = _layer_blob("vtkFoo")
        with patch(
            "vtk_knowledge.artifact.fetcher.urllib.request.urlopen",
            side_effect=_urlopen_side_effect(blob),
        ):
            VTKAPIIndex.from_artifact("9.6.1", cache_dir=custom)

        assert (custom / "vtk-knowledge-9.6.1.jsonl").exists()

    def test_default_cache_dir_is_home_cache(self, tmp_path):
        from vtk_knowledge.artifact.fetcher import _CACHE_DIR

        assert _CACHE_DIR == Path.home() / ".cache" / "vtk-knowledge"

    def test_enriched_fields_survive_round_trip(self, tmp_path):
        blob = _layer_blob(
            "vtkSphereSource",
            vtk_version="9.6.1",
            role="source",
            synopsis="Create a sphere.",
            action_phrase="sphere generation",
            visibility_score=0.85,
        )
        with patch(
            "vtk_knowledge.artifact.fetcher.urllib.request.urlopen",
            side_effect=_urlopen_side_effect(blob),
        ):
            idx = VTKAPIIndex.from_artifact("9.6.1", cache_dir=tmp_path)

        r = idx.get_class("vtkSphereSource")
        assert r.synopsis == "Create a sphere."
        assert r.action_phrase == "sphere generation"
        assert r.visibility_score == 0.85
        assert r.role.value == "source"
        assert idx.vtk_version == "9.6.1"

    def test_second_call_returns_same_path(self, tmp_path):
        blob = _layer_blob("vtkFoo")
        with patch(
            "vtk_knowledge.artifact.fetcher.urllib.request.urlopen",
            side_effect=_urlopen_side_effect(blob),
        ):
            idx1 = VTKAPIIndex.from_artifact("9.6.1", cache_dir=tmp_path)

        # second call — network is not available, must hit cache
        with patch(
            "vtk_knowledge.artifact.fetcher.urllib.request.urlopen",
            side_effect=RuntimeError("should not be called"),
        ):
            idx2 = VTKAPIIndex.from_artifact("9.6.1", cache_dir=tmp_path)

        assert set(idx1.classes) == set(idx2.classes)
