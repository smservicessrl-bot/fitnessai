from __future__ import annotations

import json
from typing import Any, Optional


def _slim_deterministic_proposal_for_prompt(prop: Any) -> Any:
    """
    Drop bulky per-exercise payloads from the prompt. Slugs are repeated in `slug_plan`;
    the API must still return prescriptions — enforced by validation + post-processing.
    """
    if not isinstance(prop, dict):
        return prop
    slim: dict[str, Any] = {
        "title": prop.get("title"),
        "objective": prop.get("objective"),
        "estimated_duration_minutes": prop.get("estimated_duration_minutes"),
    }
    for key in ("warmup_items", "main_block", "accessory_block", "cooldown_items"):
        items = prop.get(key) or []
        slim_items: list[dict[str, Any]] = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                ex = it.get("exercise") or {}
                slug = ex.get("slug") if isinstance(ex, dict) else None
                if isinstance(slug, str) and slug:
                    slim_items.append({"exercise_slug": slug})
        slim[key] = slim_items
    return slim


def build_workout_generation_user_prompt(
    *,
    workout_input: dict[str, Any],
    validation_errors: Optional[list[str]] = None,
) -> str:
    """
    Build the OpenAI "user" message for workout generation.

    Expected keys in `workout_input`:
    - session: dict (must include `available_time`)
    - deterministic_proposal: dict with keys:
        - warmup_items, main_block, accessory_block, cooldown_items
      each containing items with `exercise.slug`.
    - approved_exercises_metadata_by_slug: mapping from slug -> metadata (name, category, instructions optional)
    - previous_validation_feedback_hint (optional)

    The prompt includes hard constraints (e.g., keep exercise slugs fixed) so the output
    can pass validation without requiring the model to "reason" about the rules.
    """

    session = workout_input.get("session") or {}
    available_time = session.get("available_time")

    deterministic = workout_input.get("deterministic_proposal") or {}

    def block_slugs(block_key: str) -> list[str]:
        items = deterministic.get(block_key) or []
        slugs: list[str] = []
        for it in items:
            if isinstance(it, dict):
                ex = it.get("exercise") or {}
                if isinstance(ex, dict):
                    slug = ex.get("slug")
                    if slug:
                        slugs.append(slug)
        return slugs

    slug_plan = {
        "warmup_items": block_slugs("warmup_items"),
        "main_block": block_slugs("main_block"),
        "accessory_block": block_slugs("accessory_block"),
        "cooldown_items": block_slugs("cooldown_items"),
    }

    metadata_by_slug = workout_input.get("approved_exercises_metadata_by_slug") or {}

    validation_feedback = ""
    if validation_errors:
        # Keep the feedback short; OpenAI needs it to fix the same class of mistakes.
        formatted = "\n".join([f"- {e}" for e in validation_errors[:10]])
        validation_feedback = (
            "\n\n"
            "VALIDATION_ERRORS_FROM_YOUR_PREVIOUS_OUTPUT (fix these):\n"
            f"{formatted}\n"
        )

    # Smaller prompt = lower latency and cost. Full library lists are not needed for slug-locked refinement.
    slim_input: dict[str, Any] = dict(workout_input)
    slim_input.pop("approved_exercises", None)
    det = slim_input.get("deterministic_proposal")
    if isinstance(det, dict):
        slim_input["deterministic_proposal"] = _slim_deterministic_proposal_for_prompt(det)

    context_json = json.dumps(slim_input, ensure_ascii=False)

    # The model must keep the slugs and order; it may update only prescription fields and safety_notes.
    instructions = (
        f"Session target duration: {available_time} minutes.\n"
        "You MUST keep the same exercise_slug values in each block, and in the same order. "
        "Only update prescription fields and safety_notes.\n"
        "Language preference: Determine language ONLY from context JSON field session.language_preference. "
        "If it is a non-null string, write title, objective, and every safety_notes in that language. "
        "If missing, default to Hungarian.\n"
        f"Expected exercise_slug plan:\n{json.dumps(slug_plan, ensure_ascii=False)}\n"
    )

    # Only exercises appearing in this plan (caller should filter metadata_by_slug accordingly).
    metadata_hint = (
        "\nApproved exercises metadata for THIS PLAN's slugs (from DB):\n"
        f"{json.dumps(metadata_by_slug, ensure_ascii=False)[:8000]}\n"
    )

    return (
        instructions
        + "\n"
        + "WORKOUT_INPUT_JSON:\n"
        + context_json
        + metadata_hint
        + validation_feedback
    )

