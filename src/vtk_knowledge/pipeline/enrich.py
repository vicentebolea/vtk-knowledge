"""LLM-based enrichment of extracted VTK records.

Reads an extracted JSONL and populates synopsis, action_phrase, and
visibility_score via LiteLLM. Idempotent: records that already have all
three fields are skipped.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_ENRICH_FIELDS = ("synopsis", "action_phrase", "visibility_score")

CLASSIFY_PROMPT = """\
You are classifying VTK (Visualization Toolkit) classes for documentation.

Given a VTK class name and its documentation, return a JSON object with:

1. "synopsis": One sentence (max 20 words) summarizing what the class does.
   Start directly with the action, not the class name.

2. "action_phrase": Noun-phrase (max 5 words) for the primary action.
   Examples: "mesh smoothing", "file reading", "color mapping".

3. "visibility_score": Float 0.0–1.0 indicating how likely users mention this class.
   1.0 = always used directly (vtkActor), 0.0 = internal/base class only.

Return only valid JSON. No markdown fences.
"""


def _is_enriched(record: dict[str, Any]) -> bool:
    return all(record.get(f) not in (None, "", 0.0) for f in _ENRICH_FIELDS)


async def _enrich_one(class_name: str, class_doc: str, model: str) -> dict[str, Any]:
    """Call LiteLLM to enrich a single record."""
    try:
        import litellm

        doc_preview = class_doc[:500] if class_doc else "(no documentation)"
        messages = [
            {"role": "system", "content": CLASSIFY_PROMPT},
            {
                "role": "user",
                "content": f"Class: {class_name}\n\nDocumentation:\n{doc_preview}",
            },
        ]
        response = await litellm.acompletion(model=model, messages=messages)
        content = response.choices[0].message.content.strip()
        # Strip markdown fences that some models wrap around JSON
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip().rstrip("`").strip()
        return json.loads(content)
    except Exception as exc:
        logger.warning("Enrichment failed for %s: %s", class_name, exc)
        return {}


async def _enrich_batch(
    records: list[dict[str, Any]],
    model: str,
    max_concurrent: int = 10,
) -> None:
    """Enrich records in-place, skipping already-enriched ones."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process(record: dict[str, Any]) -> None:
        if _is_enriched(record):
            return
        async with semaphore:
            result = await _enrich_one(record.get("class_name", ""), record.get("class_doc", ""), model)
        record.update({k: v for k, v in result.items() if k in _ENRICH_FIELDS})

    await asyncio.gather(*[process(r) for r in records])


def enrich_records(
    records: list[dict[str, Any]],
    model: str = "",
    max_concurrent: int = 10,
) -> list[dict[str, Any]]:
    """Enrich records with LLM-generated fields (in-place).

    Args:
        records: List of extracted record dicts.
        model: LiteLLM model identifier. Falls back to ``LLM_MODEL`` env var.
        max_concurrent: Max parallel LLM requests.

    Returns:
        The same list with enrichment fields populated where possible.
    """
    effective_model = model or os.getenv("LLM_MODEL", "")
    if not effective_model:
        raise ValueError("LLM model not specified. Set LLM_MODEL env var or pass --model.")
    asyncio.run(_enrich_batch(records, effective_model, max_concurrent))
    return records


def enrich_jsonl(
    input_path: Path,
    output_path: Path,
    model: str = "",
    max_concurrent: int = 10,
) -> None:
    """Read *input_path*, enrich, write to *output_path*."""
    records: list[dict[str, Any]] = []
    with open(input_path) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))

    skipped = sum(1 for r in records if _is_enriched(r))
    logger.info(
        "Enriching %d records (%d already complete, %d to process)",
        len(records),
        skipped,
        len(records) - skipped,
    )

    enrich_records(records, model=model, max_concurrent=max_concurrent)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("Wrote enriched records to %s", output_path)
