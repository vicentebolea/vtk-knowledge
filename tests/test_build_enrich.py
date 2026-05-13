"""Tests for vtk_knowledge.build.enrich (LLM-free parts)."""

import pytest

from vtk_knowledge.build.enrich import _is_enriched, enrich_records


class TestIsEnriched:
    def test_fully_enriched(self):
        r = {
            "synopsis": "Renders geometry.",
            "action_phrase": "scene rendering",
            "visibility_score": 0.9,
        }
        assert _is_enriched(r) is True

    def test_missing_synopsis(self):
        r = {"synopsis": "", "action_phrase": "scene rendering", "visibility_score": 0.9}
        assert _is_enriched(r) is False

    def test_none_synopsis(self):
        r = {"synopsis": None, "action_phrase": "scene rendering", "visibility_score": 0.9}
        assert _is_enriched(r) is False

    def test_zero_visibility_score(self):
        r = {"synopsis": "Something.", "action_phrase": "doing x", "visibility_score": 0.0}
        assert _is_enriched(r) is False

    def test_missing_all_fields(self):
        assert _is_enriched({}) is False


class TestEnrichRecords:
    def test_raises_without_model(self):
        import os

        env_backup = os.environ.pop("LLM_MODEL", None)
        try:
            with pytest.raises(ValueError, match="LLM model not specified"):
                enrich_records([{"class_name": "vtkFoo"}], model="")
        finally:
            if env_backup is not None:
                os.environ["LLM_MODEL"] = env_backup
