from __future__ import annotations

import json
from typing import Any, Dict

from .errors import OpenAIResponseParseException, WorkoutGenerationError


def extract_output_text_from_responses_payload(response_payload: Dict[str, Any]) -> str:
    """
    Extract the `output_text` from the OpenAI Responses API payload.

    The schema-based output is typically carried in an `output_text` content block.
    """
    for out in response_payload.get("output", []):
        if out.get("type") != "message":
            continue
        for content in out.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "") or ""

    # Fallback: search any output_text.
    for out in response_payload.get("output", []):
        for content in out.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "") or ""

    return ""


def _extract_json_block(text: str) -> str:
    """
    Extract a JSON object from an LLM response text.

    Even with strict JSON modes, this makes the parser robust to accidental markdown.
    """
    if not text:
        return ""

    stripped = text.strip()

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    # Remove common markdown fences.
    if "```" in stripped:
        chunks = stripped.split("```")
        for chunk in chunks:
            candidate = chunk.strip()
            if candidate.lower().startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]

    return stripped


def parse_json_from_output_text(*, output_text: str) -> Dict[str, Any]:
    """
    Parse JSON from OpenAI `output_text`, raising structured errors on failure.
    """
    json_text = _extract_json_block(output_text)
    if not json_text:
        raise OpenAIResponseParseException(
            WorkoutGenerationError(kind="openai_json_parse", message="OpenAI output did not contain JSON text.")
        )

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise OpenAIResponseParseException(
            WorkoutGenerationError(
                kind="openai_json_parse",
                message="OpenAI output_text was not valid JSON.",
                details={"error": str(e), "prefix": output_text[:200]},
            )
        ) from e

    if not isinstance(parsed, dict):
        raise OpenAIResponseParseException(
            WorkoutGenerationError(kind="openai_json_parse", message="OpenAI JSON root must be an object.")
        )

    return parsed

