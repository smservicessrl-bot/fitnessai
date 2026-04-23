from __future__ import annotations

from typing import Any, Dict


def workout_plan_json_schema() -> Dict[str, Any]:
    """
    JSON schema for the ONE-SESSION workout plan output.

    Notes:
    - Duration fields are explicit to make validation (minutes vs seconds) reliable.
    - `safety_notes` is used for the user-facing coaching cues.
    """

    def item_schema() -> Dict[str, Any]:
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
                    "required": ["sets", "reps", "rest_seconds", "tempo", "duration_seconds", "duration_minutes"],
                    "properties": {
                        "sets": {"type": "integer", "minimum": 0, "maximum": 50},
                        "reps": {"type": "string"},
                        "rest_seconds": {"type": "integer", "minimum": 0, "maximum": 600},
                        "tempo": {"type": "string"},
                        # Strict structured outputs do not accept type: ["integer","null"]; use anyOf.
                        "duration_seconds": {
                            "anyOf": [
                                {"type": "integer", "minimum": 0, "maximum": 36000},
                                {"type": "null"},
                            ]
                        },
                        "duration_minutes": {
                            "anyOf": [
                                {"type": "integer", "minimum": 0, "maximum": 3600},
                                {"type": "null"},
                            ]
                        },
                    },
                },
                "safety_notes": {"type": "string"},
            },
        }

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
            "estimated_duration_minutes": {"type": "integer", "minimum": 0, "maximum": 1000},
            "warmup_items": {"type": "array", "items": item_schema()},
            "main_block": {"type": "array", "items": item_schema()},
            "accessory_block": {"type": "array", "items": item_schema()},
            "cooldown_items": {"type": "array", "items": item_schema()},
        },
    }

