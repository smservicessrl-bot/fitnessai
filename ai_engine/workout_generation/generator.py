from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .constants import WORKOUT_GENERATION_SYSTEM_PROMPT
from .openai_client import openai_generate_workout_plan_with_responses_api
from .prompts import build_workout_generation_user_prompt
from .schema import workout_plan_json_schema
from .validator import WorkoutPlanValidator


def _summarize_generation_errors(last_errors: List[str]) -> str:
    """
    Convert low-level provider errors into a compact, user-safe fallback reason.
    """
    if not last_errors:
        return "AI generation failed."
    joined = "; ".join(last_errors[:8])
    if "openai_auth" in joined.lower() or "openai_api_key is not set" in joined.lower():
        return "OPENAI_API_KEY is not set."
    return joined[:500]


def _expected_slug_plan_from_deterministic_proposal(deterministic_proposal: Dict[str, Any]) -> Dict[str, List[str]]:
    def block_slugs(block_key: str) -> List[str]:
        items = deterministic_proposal.get(block_key) or []
        slugs: List[str] = []
        for it in items:
            if isinstance(it, dict):
                ex = it.get("exercise") or {}
                if isinstance(ex, dict) and isinstance(ex.get("slug"), str):
                    slugs.append(ex["slug"])
        return slugs

    return {
        "warmup_items": block_slugs("warmup_items"),
        "main_block": block_slugs("main_block"),
        "accessory_block": block_slugs("accessory_block"),
        "cooldown_items": block_slugs("cooldown_items"),
    }


def _convert_openai_output_to_internal_shape(openai_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert strict OpenAI output into the deterministic-internal shape used by the persistence layer.
    """
    def convert_items(items: List[Dict[str, Any]], *, expected_block_type: str) -> List[Dict[str, Any]]:
        converted: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            pres = it.get("prescription") or {}
            converted.append(
                {
                    "exercise": {"slug": it.get("exercise_slug")},
                    "block_type": expected_block_type,
                    "prescription": {
                        "sets": pres.get("sets"),
                        "reps": pres.get("reps"),
                        "rest_seconds": pres.get("rest_seconds"),
                        "tempo": pres.get("tempo"),
                    },
                    # User-facing coaching cues.
                    "safety_notes": it.get("safety_notes") or "",
                }
            )
        return converted

    return {
        "title": openai_output.get("title") or "",
        "objective": openai_output.get("objective") or "",
        "estimated_duration_minutes": openai_output.get("estimated_duration_minutes") or 0,
        "warmup_items": convert_items(openai_output.get("warmup_items") or [], expected_block_type="warmup"),
        "main_block": convert_items(openai_output.get("main_block") or [], expected_block_type="main_work"),
        "accessory_block": convert_items(openai_output.get("accessory_block") or [], expected_block_type="accessory"),
        "cooldown_items": convert_items(openai_output.get("cooldown_items") or [], expected_block_type="cooldown"),
    }


def _deterministic_item_to_openai_item(
    item: Dict[str, Any],
    *,
    block_key: str,
    block_type_by_key: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Build one OpenAI-schema item from a deterministic proposal item (slug + prescription)."""
    ex = item.get("exercise") or {}
    if not isinstance(ex, dict):
        return None
    slug = ex.get("slug")
    if not isinstance(slug, str) or not slug:
        return None
    pres = item.get("prescription") or {}
    if not isinstance(pres, dict):
        pres = {}
    bt = block_type_by_key.get(block_key, "main_work")
    return {
        "exercise_slug": slug,
        "block_type": bt,
        "prescription": {
            "sets": pres.get("sets", 1),
            "reps": str(pres.get("reps", "") or ""),
            "rest_seconds": int(pres.get("rest_seconds", 60) or 0),
            "tempo": str(pres.get("tempo", "") or ""),
            "duration_seconds": None,
            "duration_minutes": None,
        },
        "safety_notes": str(item.get("safety_notes") or ""),
    }


def _rebuild_openai_block_from_deterministic(
    block_key: str,
    desired_slugs: List[str],
    deterministic_proposal: Dict[str, Any],
    block_type_by_key: Dict[str, str],
) -> List[Dict[str, Any]]:
    """When the model returns an empty block, restore rows from the deterministic proposal (same slugs/order)."""
    det_items = deterministic_proposal.get(block_key) or []
    if not isinstance(det_items, list):
        return []
    by_slug: Dict[str, Dict[str, Any]] = {}
    for it in det_items:
        if not isinstance(it, dict):
            continue
        converted = _deterministic_item_to_openai_item(
            it, block_key=block_key, block_type_by_key=block_type_by_key
        )
        if converted:
            by_slug[converted["exercise_slug"]] = converted
    out: List[Dict[str, Any]] = []
    for slug in desired_slugs:
        row = by_slug.get(slug)
        if row is not None:
            out.append(row)
    return out


def _force_openai_exercise_plan_to_deterministic(
    *,
    openai_output: Dict[str, Any],
    expected_slug_plan: Dict[str, List[str]],
    deterministic_proposal: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Enforce the deterministic exercise structure onto the OpenAI output before validation.

    We still allow the LLM to refine `prescription` and `safety_notes`, but we prevent
    it from accidentally changing exercise slugs/order (which breaks strict validation).
    """
    if not isinstance(openai_output, dict) or not expected_slug_plan:
        return openai_output

    block_type_by_key: Dict[str, str] = {
        "warmup_items": "warmup",
        "main_block": "main_work",
        "accessory_block": "accessory",
        "cooldown_items": "cooldown",
    }

    for key, desired_slugs in expected_slug_plan.items():
        if not isinstance(desired_slugs, list):
            continue
        if key not in openai_output:
            continue

        items = openai_output.get(key)
        if not isinstance(items, list):
            continue

        if not desired_slugs:
            openai_output[key] = []
            continue

        if not items:
            if deterministic_proposal:
                rebuilt = _rebuild_openai_block_from_deterministic(
                    key, desired_slugs, deterministic_proposal, block_type_by_key
                )
                if rebuilt:
                    items = rebuilt
                    openai_output[key] = items
            if not items:
                # Still empty: leave as-is so validation can explain.
                continue

        desired_len = len(desired_slugs)
        if len(items) > desired_len:
            items = items[:desired_len]
        elif len(items) < desired_len and isinstance(items[-1], dict):
            # Pad by cloning the last item (keeps prescription/safety_notes shape).
            while len(items) < desired_len:
                items.append(dict(items[-1]))

        block_type = block_type_by_key.get(key)
        for i in range(min(len(items), desired_len)):
            if not isinstance(items[i], dict):
                items[i] = {}
            items[i]["exercise_slug"] = desired_slugs[i]
            if block_type:
                items[i]["block_type"] = block_type

        openai_output[key] = items

    return openai_output


@dataclass(frozen=True)
class OpenAIWorkoutGenerationRequest:
    """
    Inputs needed to produce a validated one-session workout plan.
    """

    workout_input: Dict[str, Any]
    exercise_metadata_by_slug: Dict[str, Dict[str, Any]]
    target_duration_minutes: int
    approved_exercise_slugs: Optional[set[str]] = None
    deterministic_proposal: Optional[Dict[str, Any]] = None
    max_attempts: int = 3


def generate_validated_one_session_workout_plan_openai(
    *,
    request: OpenAIWorkoutGenerationRequest,
) -> Tuple[Dict[str, Any], bool, str]:
    """
    Generate one-session workout plan using OpenAI strict JSON.

    Returns:
    - internal_proposal (deterministic-internal shape for persistence)
    - ai_used (bool)
    - reason (empty if successful)
    """
    schema = workout_plan_json_schema()

    deterministic_proposal = request.deterministic_proposal or request.workout_input.get("deterministic_proposal") or {}
    expected_slug_plan = _expected_slug_plan_from_deterministic_proposal(deterministic_proposal)

    target_duration_minutes = int(request.target_duration_minutes or 0)

    # Optional speed knobs (set via environment).
    # Keep them off by default to avoid accidental truncation of structured JSON.
    # Default to 60s because structured JSON + validation can take
    # longer on slower networks; falling back on timeouts is frustrating UX.
    timeout_seconds = int(os.environ.get("OPENAI_TIMEOUT_SECONDS", "60"))
    temperature = float(os.environ.get("OPENAI_TEMPERATURE", "0.2"))
    max_output_tokens_raw = os.environ.get("OPENAI_MAX_OUTPUT_TOKENS", "").strip()
    max_output_tokens: Optional[int] = None
    if max_output_tokens_raw:
        try:
            max_output_tokens = int(max_output_tokens_raw)
        except ValueError:
            max_output_tokens = None
    # Cap generation length by default — one-session JSON is typically far smaller; reduces tail latency.
    if max_output_tokens is None:
        try:
            max_output_tokens = int(os.environ.get("OPENAI_MAX_OUTPUT_TOKENS_DEFAULT", "4096"))
        except ValueError:
            max_output_tokens = 4096

    validator = WorkoutPlanValidator(
        exercise_metadata_by_slug=request.exercise_metadata_by_slug,
        target_duration_minutes=target_duration_minutes,
        approved_exercise_slugs=request.approved_exercise_slugs,
        expected_slug_plan=expected_slug_plan,
    )

    last_errors: List[str] = []
    for attempt in range(1, max(1, request.max_attempts) + 1):
        user_prompt = build_workout_generation_user_prompt(
            workout_input=request.workout_input,
            validation_errors=last_errors,
        )

        try:
            openai_output = openai_generate_workout_plan_with_responses_api(
                system_prompt=WORKOUT_GENERATION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                json_schema=schema,
                timeout_seconds=timeout_seconds,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
        except Exception as e:
            # Treat provider errors as retriable up to max_attempts.
            last_errors = [f"OpenAI error on attempt {attempt}: {str(e)[:300]}"]
            continue

        # Enforce deterministic exercise structure before strict validation.
        openai_output = _force_openai_exercise_plan_to_deterministic(
            openai_output=openai_output,
            expected_slug_plan=expected_slug_plan,
            deterministic_proposal=deterministic_proposal,
        )

        result = validator.validate(openai_output)
        if result.is_valid:
            internal = _convert_openai_output_to_internal_shape(openai_output)
            return internal, True, ""

        last_errors = result.errors or [f"Validation failed on attempt {attempt}."]

    # Failed after retries: fall back to deterministic proposal.
    internal_fallback = deterministic_proposal
    # Ensure fallback is in the internal shape expected by persistence.
    if not isinstance(internal_fallback, dict):
        internal_fallback = {}
    return internal_fallback, False, _summarize_generation_errors(last_errors)

