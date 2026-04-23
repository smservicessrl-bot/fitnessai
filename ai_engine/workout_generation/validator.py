from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .errors import WorkoutValidationException, WorkoutGenerationError


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: List[str]


class WorkoutPlanValidator:
    """
    Validates an OpenAI-generated one-session workout plan (strict JSON) against
    the MVP business rules.
    """

    # Heuristic tokens used to classify exercise types from DB metadata.
    _STRENGTH_CATEGORIES = {"strength", "hypertrophy"}
    _COOLDOWN_ALLOWED_CATEGORIES = {"mobility", "rehab", "core", "cardio"}

    _BREATHING_TOKENS = {"breath", "breathe", "inhale", "exhale", "nasal"}
    _STRETCH_TOKENS = {"stretch", "stretches", "stretching", "lengthen"}

    _ISO_TOKENS = {
        "plank",
        "hold",
        "isometric",
        "wall sit",
        "wall-sit",
        "dead hang",
        "dead-hang",
    }

    # Keep cardio tokens specific enough to avoid misclassifying strength exercises.
    # In particular, do NOT include plain "row" because it matches strength "seated cable row".
    _CARDIO_TOKENS = {"treadmill", "bike", "bicycle", "rower", "elliptical", "cardio"}

    _COACHING_CUE_TOKENS = {
        "brace",
        "squeeze",
        "keep",
        "maintain",
        "control",
        "slow",
        "pause",
        "drive",
        "exhale",
        "inhale",
        "breathe",
        "retract",
        "set",
        "stack",
        "hinge",
        "straight",
        "line",
        "ribs",
        "glutes",
        "shoulder",
        "elbow",
        "knee",
        "hips",
        "core",
        "chest",
        "back",
        "mid-foot",
        "midfoot",
        "pain-free",
        "range",
    }

    _ANATOMY_TOKENS = {
        "ribs",
        "glutes",
        "shoulder",
        "elbow",
        "knee",
        "hips",
        "core",
        "spine",
        "chest",
        "back",
        "ankle",
        "mid-foot",
        "midfoot",
        "hamstring",
        "quads",
        "quads",
        "calves",
    }

    def __init__(
        self,
        *,
        exercise_metadata_by_slug: Dict[str, Dict[str, Any]],
        target_duration_minutes: int,
        approved_exercise_slugs: Optional[set[str]] = None,
        expected_slug_plan: Optional[Dict[str, List[str]]] = None,
        max_note_words: int = 60,
    ) -> None:
        self.exercise_metadata_by_slug = exercise_metadata_by_slug
        self.target_duration_minutes = int(target_duration_minutes or 0)
        self.approved_exercise_slugs = approved_exercise_slugs
        self.expected_slug_plan = expected_slug_plan
        self.max_note_words = max_note_words

    def validate(self, plan: Dict[str, Any]) -> ValidationResult:
        errors: List[str] = []

        if not isinstance(plan, dict):
            return ValidationResult(False, ["Plan must be a JSON object."])

        required_top = {
            "title",
            "objective",
            "estimated_duration_minutes",
            "warmup_items",
            "main_block",
            "accessory_block",
            "cooldown_items",
        }
        missing = [k for k in required_top if k not in plan]
        if missing:
            errors.append(f"Missing top-level keys: {missing}")

        warmup_items = plan.get("warmup_items") or []
        main_items = plan.get("main_block") or []
        accessory_items = plan.get("accessory_block") or []
        cooldown_items = plan.get("cooldown_items") or []

        for block_key in ["warmup_items", "main_block", "accessory_block", "cooldown_items"]:
            if not isinstance(plan.get(block_key), list):
                errors.append(f"{block_key} must be an array.")

        # Optional: ensure model kept the same slug plan and counts/order.
        if self.expected_slug_plan:
            expected_flat = self._flatten_slug_plan(self.expected_slug_plan)
            actual_flat = self._flatten_slug_plan(
                {
                    "warmup_items": [i.get("exercise_slug") for i in warmup_items if isinstance(i, dict)],
                    "main_block": [i.get("exercise_slug") for i in main_items if isinstance(i, dict)],
                    "accessory_block": [i.get("exercise_slug") for i in accessory_items if isinstance(i, dict)],
                    "cooldown_items": [i.get("exercise_slug") for i in cooldown_items if isinstance(i, dict)],
                }
            )
            if expected_flat != actual_flat:
                errors.append("Exercise_slug plan/order/count must match deterministic proposal.")

        # Gather slugs for cross-workout validation.
        all_items: List[Tuple[str, Dict[str, Any]]] = []
        for block_name, items in [
            ("warmup_items", warmup_items),
            ("main_block", main_items),
            ("accessory_block", accessory_items),
            ("cooldown_items", cooldown_items),
        ]:
            for it in items:
                if isinstance(it, dict):
                    all_items.append((block_name, it))

        slugs = [it.get("exercise_slug") for _, it in all_items if isinstance(it.get("exercise_slug"), str)]

        # No duplicate exercises, except: one cooldown row may repeat a slug already used (small exercise libraries).
        slug_counts = Counter(slugs)
        duplicate_slugs = {s for s, n in slug_counts.items() if n > 1}
        if duplicate_slugs:
            bad: set[str] = set()
            for s in duplicate_slugs:
                n = slug_counts[s]
                cooldown_uses = sum(
                    1
                    for bn, it in all_items
                    if bn == "cooldown_items" and isinstance(it, dict) and it.get("exercise_slug") == s
                )
                if n == 2 and cooldown_uses == 1:
                    continue
                bad.add(s)
            if bad:
                errors.append(f"Duplicate exercises are not allowed: {sorted(bad)}")

        # Validate each item structure and business rules.
        for block_name, item in all_items:
            ex_slug = item.get("exercise_slug")
            if not isinstance(ex_slug, str) or not ex_slug:
                errors.append(f"{block_name} item missing/invalid exercise_slug.")
                continue

            if self.approved_exercise_slugs is not None and ex_slug not in self.approved_exercise_slugs:
                errors.append(f"{block_name} references unapproved exercise_slug: {ex_slug}")
                continue

            meta = self.exercise_metadata_by_slug.get(ex_slug) or {}
            ex_name = (meta.get("name") or "").lower()
            ex_category = (meta.get("category") or "").lower()
            ex_instructions = (meta.get("instructions") or "").lower()

            if not meta:
                errors.append(f"{block_name} exercise_slug has no metadata for validation: {ex_slug}")

            prescription = item.get("prescription") or {}
            if not isinstance(prescription, dict):
                errors.append(f"{block_name} exercise {ex_slug} prescription must be an object.")
                continue

            reps = prescription.get("reps")
            safety_notes = item.get("safety_notes")
            duration_seconds = prescription.get("duration_seconds")
            duration_minutes = prescription.get("duration_minutes")

            if not isinstance(safety_notes, str) or not safety_notes.strip():
                errors.append(f"{block_name} exercise {ex_slug} safety_notes must be non-empty coaching cues.")

            # Notes must be specific coaching cues (heuristic).
            errors.extend(self._validate_coaching_notes(block_name=block_name, ex_slug=ex_slug, notes=safety_notes or ""))

            # Warmup rule: must NOT include strength exercises.
            if block_name == "warmup_items":
                if ex_category in self._STRENGTH_CATEGORIES:
                    errors.append(f"Warmup cannot include strength/hypertrophy exercises: {ex_slug}")

            # Cooldown rule: only mobility, breathing, or stretching.
            if block_name == "cooldown_items":
                if not self._is_cooldown_allowed(meta=meta, name_lower=ex_name):
                    errors.append(f"Cooldown contains non-allowed exercise type for {ex_slug}")

            # Plank rule: plank can appear at most once.
            # We enforce this via duplicates check for "plank exercises" if the model somehow repeats it.
            # (But duplicates across all exercises already catches repetitions.)
            if "plank" in ex_name:
                # If this exercise_slug repeats it's already caught; here we enforce "at most once per workout" by name too.
                pass

            is_isometric = self._is_isometric_exercise(
                name_lower=ex_name,
                instructions_lower=ex_instructions,
                slug_lower=ex_slug.lower(),
            )
            is_cardio = self._is_cardio_exercise(category_lower=ex_category, name_lower=ex_name)

            # Cardio must use minutes.
            if is_cardio:
                if duration_minutes is None:
                    # Accept when model expresses duration via `reps` minutes unit
                    # (important when LLMs omit explicit duration fields).
                    if not self._reps_string_contains_unit(reps, unit="minutes"):
                        errors.append(f"Cardio exercise {ex_slug} must set prescription.duration_minutes.")
                elif not isinstance(duration_minutes, int):
                    errors.append(f"Cardio exercise {ex_slug} duration_minutes must be an integer.")
                elif duration_minutes <= 0:
                    errors.append(f"Cardio exercise {ex_slug} duration_minutes must be > 0.")

                # duration_seconds must not be set for cardio (strict interpretation).
                if duration_seconds is not None and duration_seconds > 0:
                    errors.append(f"Cardio exercise {ex_slug} must not use duration_seconds.")

                if not self._reps_string_contains_unit(reps, unit="minutes"):
                    errors.append(f"Cardio exercise {ex_slug} reps must include a minutes unit (e.g. '10 min').")

            # Isometric must use seconds.
            if is_isometric:
                if duration_seconds is None:
                    # Accept when model expresses isometric duration via `reps` seconds unit.
                    if not self._reps_string_contains_unit(reps, unit="seconds"):
                        errors.append(f"Isometric exercise {ex_slug} must set prescription.duration_seconds.")
                elif not isinstance(duration_seconds, int):
                    errors.append(f"Isometric exercise {ex_slug} duration_seconds must be an integer.")
                elif duration_seconds <= 0:
                    errors.append(f"Isometric exercise {ex_slug} duration_seconds must be > 0.")

                if duration_minutes is not None and duration_minutes > 0:
                    errors.append(f"Isometric exercise {ex_slug} must not use duration_minutes.")

                if not self._reps_string_contains_unit(reps, unit="seconds"):
                    errors.append(
                        f"Isometric exercise {ex_slug} reps must include a seconds unit (e.g. '45 sec')."
                    )

            # If it's neither cardio nor isometric, allow duration fields to be null.
            if not is_cardio and not is_isometric:
                # Allow 0 as "not used" to reduce unnecessary regeneration churn.
                if (duration_seconds is not None and duration_seconds > 0) or (duration_minutes is not None and duration_minutes > 0):
                    errors.append(
                        f"Non time-based exercise {ex_slug} must not set duration_seconds/duration_minutes."
                    )

        # Total duration rule: must fit requested duration.
        estimated = plan.get("estimated_duration_minutes")
        if isinstance(estimated, int):
            if self.target_duration_minutes > 0:
                if estimated > self.target_duration_minutes:
                    errors.append(
                        f"Estimated duration ({estimated}) exceeds requested ({self.target_duration_minutes})."
                    )
                min_ok = max(0, self.target_duration_minutes - 10)
                if estimated < min_ok:
                    errors.append(
                        f"Estimated duration ({estimated}) is too short for requested ({self.target_duration_minutes})."
                    )
        else:
            errors.append("estimated_duration_minutes must be an integer.")

        # Plank at most once across workout (by name token).
        plank_names = [
            item.get("exercise_slug")
            for _, item in all_items
            if isinstance(item.get("exercise_slug"), str)
            and "plank" in (self.exercise_metadata_by_slug.get(item.get("exercise_slug"), {}).get("name") or "").lower()
        ]
        if len(set(plank_names)) > 1:
            errors.append("Plank can appear at most once across the entire workout.")
        elif len(plank_names) > 0 and len(set(plank_names)) == 1:
            # Fine.
            pass

        return ValidationResult(len(errors) == 0, errors)

    def _flatten_slug_plan(self, plan: Dict[str, List[str]]) -> List[str]:
        out: List[str] = []
        for key in ["warmup_items", "main_block", "accessory_block", "cooldown_items"]:
            for s in plan.get(key) or []:
                if isinstance(s, str):
                    out.append(s)
        return out

    def _is_cardio_exercise(self, *, category_lower: str, name_lower: str) -> bool:
        if category_lower == "cardio":
            return True
        return any(tok in name_lower for tok in self._CARDIO_TOKENS)

    def _is_isometric_exercise(self, *, name_lower: str, instructions_lower: str, slug_lower: str = "") -> bool:
        # Avoid misclassifying regular strength movements. Many exercises use "hold" in a
        # non-isometric sense (e.g. "Hold dumbbell at chest" for goblet squats) — do NOT
        # treat instructions.startswith("hold ") as isometric.
        iso_name_tokens = {"plank", "isometric", "wall sit", "wall-sit", "dead hang", "dead-hang"}

        # Slug is stable English id even when `name` is localized (e.g. Hungarian title without "plank").
        if slug_lower and any(tok in slug_lower for tok in iso_name_tokens):
            return True
        if any(tok in name_lower for tok in iso_name_tokens):
            return True
        if any(tok in instructions_lower for tok in iso_name_tokens):
            return True

        seconds_unit_re = r"\b(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds|mp|másodperc|masodperc)\b"
        if "hold" in name_lower or "hold" in instructions_lower:
            if re.search(seconds_unit_re, instructions_lower, flags=re.IGNORECASE):
                return True

        return False

    def _is_cooldown_allowed(self, *, meta: Dict[str, Any], name_lower: str) -> bool:
        category_lower = str(meta.get("category") or "").lower()
        if category_lower in self._COOLDOWN_ALLOWED_CATEGORIES:
            return True
        if any(tok in name_lower for tok in self._BREATHING_TOKENS):
            return True
        if any(tok in name_lower for tok in self._STRETCH_TOKENS):
            return True
        # If instructions were provided, include them for better classification.
        instructions_lower = str(meta.get("instructions") or "").lower()
        if any(tok in instructions_lower for tok in self._BREATHING_TOKENS):
            return True
        if any(tok in instructions_lower for tok in self._STRETCH_TOKENS):
            return True
        return False

    def _reps_string_contains_unit(self, reps: Any, *, unit: str) -> bool:
        if not isinstance(reps, str):
            return False
        text = reps.lower()
        if unit == "minutes":
            # Support both English and Hungarian units.
            # Hungarian examples: "10 perc", "10 percet", "10 percek".
            return bool(
                re.search(
                    r"\b(\d+(?:\.\d+)?)\s*(min|mins|minute|minutes|perc|percek|percet)\b",
                    text,
                    flags=re.IGNORECASE,
                )
            ) or bool(re.search(r"\b(\d+(?:\.\d+)?)\s*min\b", text, flags=re.IGNORECASE))
        if unit == "seconds":
            # Support both English and Hungarian units.
            # Hungarian examples: "45 sec", "45 mp", "45 másodperc".
            return bool(
                re.search(
                    r"\b(\d+(?:\.\d+)?)\s*(sec|secs|second|seconds|mp|másodperc|masodperc)\b",
                    text,
                    flags=re.IGNORECASE,
                )
            ) or bool(re.search(r"\b(\d+(?:\.\d+)?)\s*s\b", text, flags=re.IGNORECASE))
        return False

    def _validate_coaching_notes(self, *, block_name: str, ex_slug: str, notes: str) -> List[str]:
        """
        Heuristic check that notes look like coaching cues rather than generic fluff.
        """
        errors: List[str] = []
        clean = (notes or "").strip()

        # Word count and length constraints.
        words = [w for w in re.split(r"\s+", clean) if w]
        # Keep this heuristic permissive enough for real-world LLM variance,
        # but still reject empty / super-short notes.
        if len(words) < 4:
            errors.append(f"{block_name} exercise {ex_slug} safety_notes must be more specific (>= 4 words).")
            return errors
        if len(words) > self.max_note_words:
            errors.append(f"{block_name} exercise {ex_slug} safety_notes is too long for MVP guidance.")
            return errors

        # Language-agnostic note validation:
        # Don’t require English coaching-token keywords here, because we support
        # generating notes in languages specified via session/member notes (e.g., Hungarian).
        # The minimum word-count check above prevents empty/generic output.

        return errors

