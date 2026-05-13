"""Tests for vtk_knowledge.artifact.fetcher."""

import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from vtk_knowledge.artifact.fetcher import fetch_knowledge_artifact


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
