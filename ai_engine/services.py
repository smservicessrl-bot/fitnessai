"""
LLM integration layer (MVP).

Goal:
- Take a deterministic workout proposal (from `workouts.services`)
- Ask OpenAI to *refine/personalize* it
- Enforce constraints:
  - Use approved exercise slugs only (no invented exercises)
  - Return structured JSON matching a strict schema
  - Validate AI output before using it
  - Fall back to deterministic output if AI fails/returns invalid output

This module should be the only place with external LLM API logic.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from ai_engine.workout_generation.generator import (
    OpenAIWorkoutGenerationRequest,
    generate_validated_one_session_workout_plan_openai,
)


@dataclass(frozen=True)
class OpenAIModelConfig:
    model: str
    api_key: str


def build_openai_context(
    *,
    member: Any,
    active_restrictions: Iterable[Any],
    session_params: Any,
    recent_workout_history: Optional[Iterable[Any]],
    available_exercises_context: Iterable[dict[str, Any]],
    deterministic_proposal: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a compact context object suitable for prompt + validation.

    Notes:
    - `available_exercises_context` should contain *only approved data*
      (usually derived from exercises included in the deterministic candidate pool).
    - The deterministic proposal is included so the model must refine within
      the existing structure and exercise slugs.
    """

    member_context = {
        "full_name": getattr(member, "full_name", None),
        "age": getattr(member, "age", None),
        "sex": getattr(member, "sex", None),
        "training_level": getattr(member, "training_level", None),
        "primary_goal": getattr(member, "primary_goal", None),
        # These are helpful for personalization but should not be treated as medical advice.
        "preferred_session_duration": getattr(member, "preferred_session_duration", None),
        "notes": getattr(member, "notes", "")[:500] if getattr(member, "notes", None) else "",
    }

    restrictions = []
    for r in active_restrictions:
        if not getattr(r, "active", True):
            continue
        restrictions.append(
            {
                "restriction_type": getattr(r, "restriction_type", None),
                "body_area": getattr(r, "body_area", None),
                "description": getattr(r, "description", "")[:300] if getattr(r, "description", None) else "",
            }
        )

    def infer_language_preference(notes: str) -> str | None:
        raw = (notes or "").lower()
        if "hungarian" in raw or "magyar" in raw:
            return "Hungarian"
        if "english" in raw:
            return "English"
        return None

    notes_text = getattr(session_params, "notes", "") or ""

    session = {
        "session_type": getattr(session_params, "session_type", None),
        "goal": getattr(session_params, "goal", None),
        "available_time": getattr(session_params, "available_time", None),
        "energy_level": getattr(session_params, "energy_level", None),
        "soreness_level": getattr(session_params, "soreness_level", None),
        "notes": notes_text[:300] if notes_text else "",
        "language_preference": infer_language_preference(notes_text) or "Hungarian",
    }

    history = []
    if recent_workout_history:
        # MVP: keep history minimal (e.g., last few plans). Avoid dumping lots of data.
        for item in recent_workout_history:
            history.append(
                {
                    "id": getattr(item, "id", None),
                    "created_at": str(getattr(item, "created_at", ""))[:25] if getattr(item, "created_at", None) else None,
                    "ai_generated": getattr(item, "ai_generated", None),
                    "goal": getattr(item, "goal", None),
                    "energy_level": getattr(item, "energy_level", None),
                    "soreness_level": getattr(item, "soreness_level", None),
                }
            )

    approved_exercises = []
    for ex in available_exercises_context:
        # Each entry should contain at least slug; optionally name + equipment/difficulty metadata.
        approved_exercises.append(
            {
                "exercise_slug": ex.get("exercise_slug") or ex.get("slug"),
                "name": ex.get("name"),
                "equipment": ex.get("equipment"),
                "difficulty": ex.get("difficulty"),
                "category": ex.get("category"),
            }
        )

    # Deterministic proposal includes warmup/main/accessory/cooldown arrays.
    # Keep only the structure needed for refinement.
    deterministic = deterministic_proposal

    return {
        "member": member_context,
        "restrictions": restrictions,
        "session": session,
        "recent_history": history,
        "approved_exercises": approved_exercises,
        "deterministic_proposal": deterministic,
    }


def build_openai_prompt(*, context: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Build an OpenAI Responses API input payload.

    The prompt enforces:
    - only refine within the provided structure
    - only use exercise slugs present in the deterministic proposal / approved list
    - return STRICT JSON matching schema
    """

    system_text = (
        "You are a gym workout planner assistant. "
        "Refine a deterministic one-day workout plan for an MVP gym workout app. "
        "You must NOT invent new exercises. "
        "You must ONLY select or modify exercises that already exist in the deterministic proposal "
        "and/or are present in the approved_exercises list. "
        "Output ONLY valid JSON that matches the provided schema."
    )

    user_text = (
        "Refine the deterministic workout proposal using the following context. "
        "Keep the same warmup/main/accessory/cooldown exercise slugs and counts. "
        "You may adjust prescription values (sets/reps/rest/tempo) and safety notes, "
        "and you may add short personalization to title/objective. \n\n"
        f"CONTEXT_JSON:\n{json.dumps(context, ensure_ascii=False)}"
    )

    # Responses API expects `input` to be a list of role/content items.
    return [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_text}],
        },
        {
            "role": "user",
            "content": [{"type": "input_text", "text": user_text}],
        },
    ]


def _build_proposal_json_schema() -> dict[str, Any]:
    """
    Shared JSON schema for refinement output across providers.
    """
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "objective",
            "estimated_duration_minutes",
            "warmup_items",
            "main_block",
            "accessory_block",
            "cooldown_items",
        ],
        "properties": {
            "title": {"type": "string"},
            "objective": {"type": "string"},
            "estimated_duration_minutes": {"type": "integer", "minimum": 0},
            "warmup_items": {"type": "array", "items": _item_schema()},
            "main_block": {"type": "array", "items": _item_schema()},
            "accessory_block": {"type": "array", "items": _item_schema()},
            "cooldown_items": {"type": "array", "items": _item_schema()},
        },
    }


def _extract_text_from_responses_output(response_payload: dict[str, Any]) -> str:
    """
    Responses API returns a list of output items; structured JSON is usually delivered
    in an output_text content field. This helper robustly extracts that text.
    """
    for out in response_payload.get("output", []):
        # Usually the first message content contains output_text.
        if out.get("type") == "message":
            for content in out.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    # Fallback: sometimes the SDK/json structure may differ; attempt to find any output_text.
    for out in response_payload.get("output", []):
        for content in out.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")
    return ""


def openai_refine_workout_with_responses_api(
    *,
    deterministic_proposal: dict[str, Any],
    context: dict[str, Any],
    approved_exercise_slugs: set[str],
) -> dict[str, Any]:
    """
    Call the OpenAI Responses API and return the parsed JSON dict output.

    This function:
    - uses env vars for api key + model selection
    - requires strict structured JSON output
    """
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip()

    proposal_schema = _build_proposal_json_schema()

    # Build input messages.
    openai_input = build_openai_prompt(context=context)

    # Responses API payload (HTTP call to avoid SDK signature drift).
    payload: dict[str, Any] = {
        "model": model,
        "input": openai_input,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "workout_refinement",
                "schema": proposal_schema,
                "strict": True,
            }
        },
        # Keeping sampling defaults deterministic-ish; the main determinism comes from schema + validation.
        "temperature": 0.2,
    }

    req = urllib.request.Request(
        url="https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = str(e)
        raise RuntimeError(f"OpenAI HTTP error: {e.code} body={body[:500]}") from e

    response_payload = json.loads(raw)
    text = _extract_text_from_responses_output(response_payload)
    if not text:
        raise RuntimeError("OpenAI response did not contain output_text.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"OpenAI output_text was not valid JSON: {text[:300]}") from e

    # Validate AI output against guardrails.
    validated_ai = validate_ai_refinement_output(
        ai_output=parsed,
        deterministic_proposal=deterministic_proposal,
        approved_exercise_slugs=approved_exercise_slugs,
    )

    # Convert AI output into the same normalized structure used by the deterministic planner.
    return _convert_ai_output_to_deterministic_shape(
        ai_output=validated_ai,
        deterministic_proposal=deterministic_proposal,
    )


def _extract_json_block(text: str) -> str:
    """
    Extract JSON object text from an LLM response.
    Handles cases where markdown fences are included.
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

    # Fallback: take largest object-like range.
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1]
    return stripped


def ollama_refine_workout(
    *,
    deterministic_proposal: dict[str, Any],
    context: dict[str, Any],
    approved_exercise_slugs: set[str],
) -> dict[str, Any]:
    """
    Call local Ollama (e.g. llama3.2) and parse JSON refinement.

    Env vars:
    - OLLAMA_BASE_URL (default: http://localhost:11434)
    - OLLAMA_MODEL (default: llama3.2)
    - OLLAMA_TIMEOUT_SECONDS (default: 45)
    """
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    model = os.environ.get("OLLAMA_MODEL", "llama3.2").strip() or "llama3.2"
    timeout_seconds = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "45"))
    proposal_schema = _build_proposal_json_schema()

    system_text = (
        "You are a gym workout planner assistant.\n"
        "Task: refine the deterministic workout proposal.\n"
        "STRICT RULES:\n"
        "1) Do NOT invent new exercises.\n"
        "2) Use only exercise_slug values that are provided in approved_exercises and deterministic_proposal.\n"
        "3) Keep the same counts for warmup_items, main_block, accessory_block, cooldown_items.\n"
        "4) Return ONLY JSON, no markdown, no explanation.\n"
        "5) JSON must satisfy this schema exactly.\n"
        f"SCHEMA_JSON: {json.dumps(proposal_schema, ensure_ascii=False)}"
    )
    user_text = (
        "Refine/personalize this deterministic workout proposal.\n"
        "Adjust sets/reps/rest/tempo and safety notes as needed, but preserve structure and approved slugs only.\n\n"
        f"CONTEXT_JSON:\n{json.dumps(context, ensure_ascii=False)}"
    )

    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        # Ask Ollama for strict JSON response format if supported by model/runtime.
        "format": proposal_schema,
        "options": {"temperature": 0.2},
    }

    req = urllib.request.Request(
        url=f"{base_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = str(e)
        raise RuntimeError(f"Ollama HTTP error: {e.code} body={body[:500]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama connection error: {e}") from e

    response_payload = json.loads(raw)
    text = (
        response_payload.get("message", {}).get("content")
        or response_payload.get("response")
        or ""
    )
    json_text = _extract_json_block(text)
    if not json_text:
        raise RuntimeError("Ollama response did not contain JSON content.")

    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Ollama output was not valid JSON: {json_text[:300]}") from e

    validated_ai = validate_ai_refinement_output(
        ai_output=parsed,
        deterministic_proposal=deterministic_proposal,
        approved_exercise_slugs=approved_exercise_slugs,
    )
    return _convert_ai_output_to_deterministic_shape(
        ai_output=validated_ai,
        deterministic_proposal=deterministic_proposal,
    )


def _item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["exercise_slug", "block_type", "prescription", "safety_notes"],
        "properties": {
            "exercise_slug": {"type": "string"},
            "block_type": {"type": "string", "enum": ["warmup", "main_work", "accessory", "cooldown"]},
            "prescription": {
                "type": "object",
                "additionalProperties": False,
                "required": ["sets", "reps", "rest_seconds", "tempo"],
                "properties": {
                    "sets": {"type": "integer", "minimum": 0, "maximum": 50},
                    "reps": {"type": "string"},
                    "rest_seconds": {"type": "integer", "minimum": 0, "maximum": 600},
                    "tempo": {"type": "string"},
                },
            },
            "safety_notes": {"type": "string"},
        },
    }


def validate_ai_refinement_output(
    *,
    ai_output: dict[str, Any],
    deterministic_proposal: dict[str, Any],
    approved_exercise_slugs: set[str],
) -> dict[str, Any]:
    """
    Validate AI output before it is used.

    MVP validation constraints:
    - Required top-level keys exist.
    - Each item must reference only approved exercise slugs.
    - The counts of warmup/main/accessory/cooldown items must match deterministic proposal
      (so AI cannot change workout structure substantially).
    - Each prescription must contain required fields with sane types.
    """
    required_top = {
        "title",
        "objective",
        "estimated_duration_minutes",
        "warmup_items",
        "main_block",
        "accessory_block",
        "cooldown_items",
    }
    missing = [k for k in required_top if k not in ai_output]
    if missing:
        raise ValueError(f"AI output missing keys: {missing}")

    # Structural guardrails: counts must match deterministic.
    def count(x: Any) -> int:
        return len(x) if isinstance(x, list) else -1

    if count(ai_output["warmup_items"]) != count(deterministic_proposal.get("warmup_items")):
        raise ValueError("AI warmup_items length does not match deterministic proposal.")
    if count(ai_output["main_block"]) != count(deterministic_proposal.get("main_block")):
        raise ValueError("AI main_block length does not match deterministic proposal.")
    if count(ai_output["accessory_block"]) != count(deterministic_proposal.get("accessory_block")):
        raise ValueError("AI accessory_block length does not match deterministic proposal.")
    if count(ai_output["cooldown_items"]) != count(deterministic_proposal.get("cooldown_items")):
        raise ValueError("AI cooldown_items length does not match deterministic proposal.")

    # Validate item structure + approved slugs.
    def validate_item(item: dict[str, Any], block_enum: str) -> None:
        if not isinstance(item, dict):
            raise ValueError("AI item is not an object.")
        for k in ["exercise_slug", "block_type", "prescription", "safety_notes"]:
            if k not in item:
                raise ValueError(f"AI item missing key {k}")
        if item["exercise_slug"] not in approved_exercise_slugs:
            raise ValueError(f"AI referenced unapproved exercise slug: {item['exercise_slug']}")
        if item["block_type"] != block_enum:
            raise ValueError(f"AI item block_type expected {block_enum} got {item['block_type']}")

        pres = item["prescription"]
        for pk in ["sets", "reps", "rest_seconds", "tempo"]:
            if pk not in pres:
                raise ValueError(f"AI prescription missing key {pk}")
        if not isinstance(pres["sets"], int):
            raise ValueError("AI sets must be int")
        if not isinstance(pres["rest_seconds"], int):
            raise ValueError("AI rest_seconds must be int")
        if not isinstance(pres["reps"], str):
            raise ValueError("AI reps must be string")
        if not isinstance(pres["tempo"], str):
            raise ValueError("AI tempo must be string")
        if pres["sets"] < 0:
            raise ValueError("AI sets must be >= 0")
        if pres["rest_seconds"] < 0:
            raise ValueError("AI rest_seconds must be >= 0")

    for item in ai_output["warmup_items"]:
        validate_item(item, "warmup")
    for item in ai_output["main_block"]:
        validate_item(item, "main_work")
    for item in ai_output["accessory_block"]:
        validate_item(item, "accessory")
    for item in ai_output["cooldown_items"]:
        validate_item(item, "cooldown")

    # If we got here, the output is structurally valid. Return as-is.
    return ai_output


def _convert_ai_output_to_deterministic_shape(
    *,
    ai_output: dict[str, Any],
    deterministic_proposal: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert validated AI output into the deterministic proposal structure.

    Deterministic structure expected:
      - warmup_items/main_block/accessory_block/cooldown_items: list of
        { exercise: {slug,...}, block_type, prescription: {sets,reps,rest_seconds,tempo}, safety_notes }
    """

    # Build slug -> exercise_metadata from deterministic proposal.
    exercise_by_slug: dict[str, dict[str, Any]] = {}
    for block_key in ["warmup_items", "main_block", "accessory_block", "cooldown_items"]:
        for item in deterministic_proposal.get(block_key, []) or []:
            ex_raw = item.get("exercise", {}) if isinstance(item, dict) else {}
            ex = ex_raw if isinstance(ex_raw, dict) else {}
            slug = ex.get("slug")
            if slug:
                exercise_by_slug[slug] = ex

    def convert_items(ai_items: list[dict[str, Any]], *, block_type: str) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for item in ai_items:
            slug = item["exercise_slug"]
            exercise = exercise_by_slug.get(slug, {"slug": slug})
            converted.append(
                {
                    "exercise": exercise,
                    "block_type": block_type,
                    "prescription": item["prescription"],
                    "safety_notes": item["safety_notes"],
                }
            )
        return converted

    return {
        "title": ai_output["title"],
        "objective": ai_output["objective"],
        "estimated_duration_minutes": ai_output["estimated_duration_minutes"],
        "warmup_items": convert_items(ai_output["warmup_items"], block_type="warmup"),
        "main_block": convert_items(ai_output["main_block"], block_type="main_work"),
        "accessory_block": convert_items(ai_output["accessory_block"], block_type="accessory"),
        "cooldown_items": convert_items(ai_output["cooldown_items"], block_type="cooldown"),
    }


def refine_workout_or_fallback_to_deterministic(
    *,
    member: Any,
    active_restrictions: Iterable[Any],
    session_params: Any,
    recent_workout_history: Optional[Iterable[Any]],
    available_exercises_context: Iterable[dict[str, Any]],
    deterministic_proposal: dict[str, Any],
) -> tuple[dict[str, Any], bool, str]:
    """
    Fallback strategy wrapper.

    Returns:
    - refined_proposal (AI-refined if valid, otherwise deterministic)
    - ai_used (bool)
    - reason/error message (empty if AI succeeded)
    """
    # Approved slugs come from the deterministic proposal's chosen exercises (not from AI).
    approved_slugs: set[str] = set()
    for block_key in ["warmup_items", "main_block", "accessory_block", "cooldown_items"]:
        for item in deterministic_proposal.get(block_key, []):
            ex_raw = item.get("exercise", {}) if isinstance(item, dict) else {}
            ex = ex_raw if isinstance(ex_raw, dict) else {}
            slug = ex.get("slug") or ex.get("exercise_slug")
            if slug:
                approved_slugs.add(slug)

    normalized_deterministic = _normalize_deterministic_proposal(deterministic_proposal)

    # Instant path: skip the OpenAI round-trip (dev, cost control, or latency-sensitive use).
    if os.environ.get("SKIP_LLM", "").strip().lower() in ("1", "true", "yes"):
        return normalized_deterministic, False, "SKIP_LLM"

    # Exercise metadata needed for rule-based validation (cardio/isometric/cooldown classification).
    exercise_metadata_by_slug: dict[str, dict[str, Any]] = {}
    for ex in available_exercises_context:
        if not isinstance(ex, dict):
            continue
        slug = ex.get("slug")
        if not slug:
            continue
        raw_instr = ex.get("instructions") or ""
        if isinstance(raw_instr, str) and len(raw_instr) > 1200:
            raw_instr = raw_instr[:1200]
        exercise_metadata_by_slug[str(slug)] = {
            "name": ex.get("name") or "",
            "category": ex.get("category") or "",
            "instructions": raw_instr if isinstance(raw_instr, str) else "",
        }

    # Prompt + validation only need metadata for exercises that appear in this workout.
    exercise_metadata_by_slug = {k: v for k, v in exercise_metadata_by_slug.items() if k in approved_slugs}

    context = build_openai_context(
        member=member,
        active_restrictions=active_restrictions,
        session_params=session_params,
        recent_workout_history=recent_workout_history,
        available_exercises_context=available_exercises_context,
        deterministic_proposal=normalized_deterministic,
    )

    try:
        # Regenerate until the strict validation rules pass.
        workout_input = dict(context)
        workout_input["approved_exercises_metadata_by_slug"] = exercise_metadata_by_slug

        target_duration = int(getattr(session_params, "available_time", 0) or 0)

        request = OpenAIWorkoutGenerationRequest(
            workout_input=workout_input,
            exercise_metadata_by_slug=exercise_metadata_by_slug,
            target_duration_minutes=target_duration,
            approved_exercise_slugs=approved_slugs,
            deterministic_proposal=normalized_deterministic,
            # Speed-first default: retry only if strict validation fails.
            max_attempts=int(os.environ.get("OPENAI_WORKOUT_MAX_ATTEMPTS", "1")),
        )
        refined, ai_used, reason = generate_validated_one_session_workout_plan_openai(request=request)
        if ai_used:
            return refined, True, ""
        return _normalize_deterministic_proposal(refined), False, reason
    except Exception as e:
        return _normalize_deterministic_proposal(deterministic_proposal), False, str(e)[:500]


def _normalize_deterministic_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """
    Ensure deterministic proposals use the same internal block_type naming
    that the AI refinement uses:
      - warmup -> "warmup"
      - main_block -> "main_work"
      - accessory_block -> "accessory"
      - cooldown_items -> "cooldown"
    """
    normalized = dict(proposal)

    def normalize_items(items: Any, *, block_type: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return out
        for item in items:
            if isinstance(item, dict):
                new_item = dict(item)
                new_item["block_type"] = block_type
                out.append(new_item)
        return out

    normalized["warmup_items"] = normalize_items(proposal.get("warmup_items"), block_type="warmup")
    normalized["main_block"] = normalize_items(proposal.get("main_block"), block_type="main_work")
    normalized["accessory_block"] = normalize_items(proposal.get("accessory_block"), block_type="accessory")
    normalized["cooldown_items"] = normalize_items(proposal.get("cooldown_items"), block_type="cooldown")
    return normalized


def answer_workout_plan_question(
    *,
    question: str,
    plan_json: dict[str, Any],
    member_context: dict[str, Any],
    restrictions_context: list[dict[str, Any]],
) -> tuple[str, str]:
    """
    Return an answer to a user question about one generated workout plan.

    Returns:
      (answer_text, source_tag)
      source_tag in {"openai", "fallback"}
    """
    q = (question or "").strip()
    if not q:
        return "Kérlek, írj be egy kérdést az edzéstervről.", "fallback"

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return (
            "Most nem érhető el az AI válaszadó. Biztonsági okból sérülés esetén beszélj az edződdel, "
            "és csak fájdalommentes gyakorlatot végezz.",
            "fallback",
        )

    model = os.environ.get("OPENAI_MODEL_QA", os.environ.get("OPENAI_MODEL", "gpt-4o-mini")).strip()
    system_text = (
        "You are a workout-plan Q&A assistant for a gym app. "
        "Answer ONLY based on provided workout plan and member context. "
        "Do not provide medical diagnosis. "
        "If injury risk is mentioned, advise caution and suggest consulting trainer/doctor. "
        "Be concise (max 6 sentences), practical, and safety-first. "
        "Respond in Hungarian."
    )
    user_payload = {
        "question": q,
        "member": member_context,
        "restrictions": restrictions_context,
        "workout_plan": plan_json,
    }
    user_text = f"Válaszolj erre a kérdésre a kontextus alapján:\n{json.dumps(user_payload, ensure_ascii=False)}"

    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_text}]},
        ],
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        url="https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        text = _extract_text_from_responses_output(data).strip()
        if not text:
            raise RuntimeError("Empty response")
        return text, "openai"
    except Exception:
        return (
            "Ezt a kérdést biztonsági szempontból az edződdel érdemes átbeszélni. "
            "Ha fájdalmat vagy bizonytalanságot érzel, hagyd ki az érintett gyakorlatot, "
            "és kérj alternatívát (pl. kisebb terhelés, kisebb mozgástartomány, más eszköz).",
            "fallback",
        )

