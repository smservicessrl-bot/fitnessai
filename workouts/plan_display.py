from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterator

from workouts.models import WorkoutExercise, WorkoutPlan


def extract_exercise_slugs_from_proposal(proposal: dict[str, Any]) -> list[str]:
    """Ordered slugs: warmup, main, accessory, cooldown (matches former persistence order)."""
    slugs: list[str] = []
    for key in ("warmup_items", "main_block", "accessory_block", "cooldown_items"):
        for item in proposal.get(key) or []:
            if not isinstance(item, dict):
                continue
            ex = item.get("exercise") or {}
            if isinstance(ex, dict):
                s = ex.get("slug")
                if isinstance(s, str) and s:
                    slugs.append(s)
    return slugs


def _row_from_json_item(order: int, item: dict[str, Any]) -> Any:
    ex = item.get("exercise") or {}
    name = ""
    if isinstance(ex, dict):
        name = str(ex.get("name") or "").strip()
    if not name and isinstance(ex, dict):
        name = str(ex.get("slug") or "?")
    pres = item.get("prescription") or {}
    if not isinstance(pres, dict):
        pres = {}
    return SimpleNamespace(
        order=order,
        exercise=SimpleNamespace(
            name=name,
            equipment=str(ex.get("equipment", "") or "") if isinstance(ex, dict) else "",
            difficulty=str(ex.get("difficulty", "") or "") if isinstance(ex, dict) else "",
        ),
        sets=int(pres.get("sets", 1) or 1),
        reps=str(pres.get("reps", "") or ""),
        rest_seconds=int(pres.get("rest_seconds", 60) or 60),
        tempo=str(pres.get("tempo", "") or ""),
        notes=str(item.get("safety_notes") or "").strip(),
        block_type=str(item.get("block_type") or ""),
    )


def split_exercise_blocks_from_proposal(proposal: dict[str, Any]) -> tuple[list[Any], list[Any], list[Any]]:
    warmup: list[Any] = []
    main_work: list[Any] = []
    cooldown: list[Any] = []
    order = 1
    for item in proposal.get("warmup_items") or []:
        if isinstance(item, dict):
            warmup.append(_row_from_json_item(order, item))
            order += 1
    for item in proposal.get("main_block") or []:
        if isinstance(item, dict):
            main_work.append(_row_from_json_item(order, item))
            order += 1
    for item in proposal.get("accessory_block") or []:
        if isinstance(item, dict):
            main_work.append(_row_from_json_item(order, item))
            order += 1
    for item in proposal.get("cooldown_items") or []:
        if isinstance(item, dict):
            cooldown.append(_row_from_json_item(order, item))
            order += 1
    return warmup, main_work, cooldown


def _split_exercise_blocks_orm(plan: WorkoutPlan) -> tuple[list[WorkoutExercise], list[WorkoutExercise], list[WorkoutExercise]]:
    exercises = list(plan.exercises.all().order_by("order"))
    warmup = [e for e in exercises if e.block_type == WorkoutExercise.BlockType.WARMUP]
    main_work = [e for e in exercises if e.block_type == WorkoutExercise.BlockType.MAIN_WORK]
    cooldown = [e for e in exercises if e.block_type == WorkoutExercise.BlockType.COOLDOWN]
    return warmup, main_work, cooldown


def get_plan_exercise_blocks(plan: WorkoutPlan) -> tuple[list[Any], list[Any], list[Any]]:
    if plan.generated_plan_json:
        return split_exercise_blocks_from_proposal(plan.generated_plan_json)
    return _split_exercise_blocks_orm(plan)


def iter_plan_rows_ordered(plan: WorkoutPlan) -> Iterator[Any]:
    """Single execution order for CSV and similar exports."""
    w, m, c = get_plan_exercise_blocks(plan)
    yield from w
    yield from m
    yield from c
