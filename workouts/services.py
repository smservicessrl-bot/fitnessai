"""
Deterministic MVP workout generator (no AI).

This module is intentionally written to be:
- deterministic (stable output for the same inputs)
- readable (clear stages and small helpers)
- testable (pure-ish functions operating on inputs + candidate lists)

It does NOT write to the database. Views/services can persist the returned structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from exercises.models import Exercise
from members.models import MemberProfile, MemberRestriction


@dataclass(frozen=True)
class SessionParams:
    """
    Session inputs needed by the deterministic engine.

    Values should match the stored choice values in WorkoutPlan:
    - goal: WorkoutPlan.Goal values (strength/hypertrophy/fat_loss/general_fitness/rehab_prevention)
    - energy_level: WorkoutPlan.EnergyLevel values (low/medium/high)
    - soreness_level: WorkoutPlan.SorenessLevel values (none/mild/moderate/severe)
    - available_time: minutes available on the session day
    """

    goal: str
    energy_level: str
    soreness_level: str
    available_time: int


def _clamp_int(val: int, *, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def _normalize_choice_value(raw: str) -> str:
    return (raw or "").strip().lower()


def _allowed_difficulties(training_level: str, *, energy_level: str, soreness_level: str, goal: str) -> set[str]:
    """
    Map member training level to allowed exercise difficulty tiers.
    Then adjust for energy/soreness conservatism.
    """

    tl = _normalize_choice_value(training_level)
    energy = _normalize_choice_value(energy_level)
    soreness = _normalize_choice_value(soreness_level)
    goal_norm = _normalize_choice_value(goal)

    if tl == "beginner":
        allowed = {"beginner"}
    elif tl == "intermediate":
        allowed = {"beginner", "intermediate"}
    else:
        # advanced or unknown -> allow advanced but still adjust conservatism below
        allowed = {"intermediate", "advanced"}

    # Rehab/prevention should be conservative by default.
    if goal_norm == "rehab_prevention":
        allowed = allowed & {"beginner", "intermediate"}

    # Low energy: avoid the hardest tier.
    if energy == "low":
        allowed = allowed - {"advanced"}

    # High soreness: be more conservative. Keep a fallback if we removed everything.
    if soreness in {"moderate", "severe"}:
        allowed = allowed - {"advanced"}

    if not allowed:
        allowed = {"beginner"}
    return allowed


def _objective_for_goal(goal: str) -> str:
    g = _normalize_choice_value(goal)
    if g == "strength":
        return "Erő fejlesztése biztonságos, szabályokhoz igazított progresszióval."
    if g == "hypertrophy":
        return "Izomtömeg növelése kontrollált volumennel és stabil előírásokkal."
    if g == "fat_loss":
        return "Zsírégetés támogatása kiegyensúlyozott terheléssel és regenerációbarát volumennel."
    if g == "general_fitness":
        return "Általános kondíció javítása kiegyensúlyozott, egynapos tervvel."
    if g == "rehab_prevention":
        return "Kockázat csökkentése és ellenállóképesség növelése óvatos, rehab-barát választással."
    return "Egynapos konditerem-edzés (determinisztikus MVP)."


def _counts_from_duration(available_time: int) -> dict[str, int]:
    """
    Decide workout structure counts based on available time.
    Hardcoded MVP heuristics to keep the engine deterministic.
    """

    t = available_time or 0
    if t <= 45:
        counts = {"warmup": 2, "main": 4, "accessory": 1, "cooldown": 1}
    elif t <= 75:
        # Keep 60-minute sessions realistic for gym-floor execution.
        counts = {"warmup": 3, "main": 4, "accessory": 1, "cooldown": 1}
    else:
        counts = {"warmup": 3, "main": 6, "accessory": 2, "cooldown": 1}

    # Hard caps requested for MVP safety and timing consistency.
    max_main_exercises = 6
    max_total_exercises = 10
    counts["main"] = min(counts["main"], max_main_exercises)

    while sum(counts.values()) > max_total_exercises:
        if counts["accessory"] > 1:
            counts["accessory"] -= 1
            continue
        if counts["main"] > 4:
            counts["main"] -= 1
            continue
        if counts["warmup"] > 2:
            counts["warmup"] -= 1
            continue
        break

    return counts


def _goal_to_main_muscles(goal: str, counts: dict[str, int]) -> list[str]:
    """
    Provide a deterministic list of primary muscle groups to target in main block slots.
    """

    g = _normalize_choice_value(goal)
    # Base ordering matters: we will try to match each slot in order.
    if g == "strength":
        base = ["quadriceps", "glutes", "chest", "back", "shoulders", "core", "hamstrings", "calves"]
    elif g == "hypertrophy":
        base = ["quadriceps", "glutes", "chest", "back", "hamstrings", "shoulders", "core", "calves"]
    elif g in {"fat_loss", "general_fitness"}:
        base = ["quadriceps", "glutes", "chest", "back", "shoulders", "core", "hamstrings", "calves"]
    elif g == "rehab_prevention":
        # Prefer safer, lower-complexity targets; core first.
        base = ["core", "glutes", "hamstrings", "chest", "back", "shoulders", "quadriceps", "calves"]
    else:
        base = ["quadriceps", "glutes", "chest", "back", "core", "shoulders", "hamstrings", "calves"]

    return base[: counts["main"]]


def _goal_to_accessory_muscles(goal: str, counts: dict[str, int]) -> list[str]:
    g = _normalize_choice_value(goal)
    if g == "strength":
        base = ["biceps", "triceps", "calves", "core", "shoulders"]
    elif g == "hypertrophy":
        base = ["biceps", "triceps", "calves", "shoulders", "core"]
    elif g == "rehab_prevention":
        base = ["core", "calves", "shoulders", "hamstrings", "glutes"]
    else:
        base = ["calves", "biceps", "triceps", "core", "shoulders"]
    return base[: counts["accessory"]]


def _warmup_muscles(main_muscles: list[str], warmup_count: int) -> list[str]:
    # Warmups focus on core/mobility-like exercises first, then lead into the first main muscle.
    base = ["core", main_muscles[0] if main_muscles else "core", "full_body", main_muscles[1] if len(main_muscles) > 1 else "core"]
    # Ensure determinism and length.
    return (base + ["core"] * warmup_count)[:warmup_count]


def _core_slot_muscles(core_count: int) -> list[str]:
    return ["core"] * max(0, core_count)


def _is_isometric(exercise: Exercise) -> bool:
    n = (exercise.name or "").lower()
    ins = (exercise.instructions or "").lower()
    return any(
        token in n
        for token in {
            "plank",
            "hold",
            "wall sit",
            "isometric",
            "deszka",
            "tartás",
            "falülés",
            "izometrikus",
        }
    ) or ins.startswith("hold ") or ins.startswith("tarts ")


def _is_compound_strength(exercise: Exercise) -> bool:
    if exercise.category not in {Exercise.Category.STRENGTH, Exercise.Category.HYPERTROPHY}:
        return False
    if exercise.primary_muscle in {Exercise.MuscleGroup.CORE, Exercise.MuscleGroup.OTHER}:
        return False
    return exercise.equipment in {
        Exercise.Equipment.BARBELL,
        Exercise.Equipment.DUMBBELL,
        Exercise.Equipment.CABLE,
        Exercise.Equipment.MACHINE,
        Exercise.Equipment.KETTLEBELL,
    }


def _name_contains_any(exercise: Exercise, words: set[str]) -> bool:
    n = (exercise.name or "").lower()
    return any(w in n for w in words)


def _movement_slot_for_exercise(exercise: Exercise) -> Optional[str]:
    """
    Lightweight movement-pattern inference from the current MVP data model.
    """
    name = (exercise.name or "").lower()

    if (
        "squat" in name
        or "lunge" in name
        or "leg press" in name
        or "guggol" in name
        or "kitörés" in name
        or "lábtoló" in name
    ):
        return "squat"
    if "deadlift" in name or "hip thrust" in name or "hinge" in name or "felhúz" in name or "csípőemel" in name:
        return "hinge"
    if "bench press" in name or "push-up" in name or "fekvő" in name or "fekvőtámasz" in name:
        return "horizontal_push"
    if "row" in name or "evezés" in name:
        return "horizontal_pull"
    if "shoulder press" in name or "overhead press" in name or "vállnyom" in name:
        return "vertical_push"
    if "pulldown" in name or "pull-up" in name or "chin-up" in name or "melltű" in name or "felhúzód" in name:
        return "vertical_pull"
    return None


def _main_movement_slot_targets(main_count: int) -> list[str]:
    required = ["squat", "hinge", "horizontal_push", "horizontal_pull", "vertical_push", "vertical_pull"]
    return required[:max(0, main_count)]


def _tempo_for_exercise(*, exercise: Exercise, suggested_tempo: str) -> str:
    # Keep tempo only where it adds value; avoid clutter for cardio/core/simple machine work.
    if exercise.category in {Exercise.Category.CARDIO, Exercise.Category.CORE}:
        return ""
    if exercise.equipment == Exercise.Equipment.MACHINE and exercise.primary_muscle == Exercise.MuscleGroup.CALVES:
        return ""
    return suggested_tempo


def _coaching_cue_for_exercise(exercise: Exercise) -> str:
    """
    Generate concise coaching cues (<= 15 words) from known exercise names.
    """
    name = (exercise.name or "").lower()
    cues = [
        ("hip thrust", "Lökjen a sarkakból; fent erősen szorítsd össze a farizmokat."),
        ("csípőemel", "Lökjen a sarkakból; fent erősen szorítsd össze a farizmokat."),
        ("bench press", "Válllapok legyenek stabilak; a csuklók a könyök fölött maradjanak."),
        ("fekvő", "Válllapok legyenek stabilak; a csuklók a könyök fölött maradjanak."),
        ("row", "Könyökkel vezess; szorítsd össze a lapockákat."),
        ("evezés", "Könyökkel vezess; szorítsd össze a lapockákat."),
        ("pulldown", "Húzd a könyököket a bordák felé; emeld a mellkasod."),
        ("melltű", "Húzd a könyököket a bordák felé; emeld a mellkasod."),
        ("shoulder press", "Feszítsd a törzset; nyomj fel úgy, hogy ne íveljen az ágyék."),
        ("vállnyom", "Feszítsd a törzset; nyomj fel úgy, hogy ne íveljen az ágyék."),
        ("split squat", "Az elülső térd a középláb fölött maradjon; a törzs egyenes."),
        ("kitörés", "Az elülső térd a középláb fölött maradjon; a törzs egyenes."),
        ("squat", "Feszítsd a törzset, kontrolláld a mélységet, lökjen a középlábból."),
        ("guggol", "Feszítsd a törzset, kontrolláld a mélységet, lökjen a középlábból."),
        ("plank", "Rögzítsd a bordákat, feszítsd a farat; egyenes testvonal."),
        ("deszka", "Rögzítsd a bordákat, feszítsd a farat; egyenes testvonal."),
        ("curl", "A könyökök mozdulatlanok; a leengedés legyen kontrollált."),
        ("calf raise", "Tarts meg fent, lassan engedd le teljes tartományban."),
        ("vádli", "Tarts meg fent, lassan engedd le teljes tartományban."),
        ("treadmill walk", "Egyenes tartás, egyenletes légzés."),
        ("futópad", "Egyenes tartás, egyenletes légzés."),
    ]
    for needle, cue in cues:
        if needle in name:
            return cue

    raw = (exercise.instructions or "").strip()
    if not raw:
        return "Kontrollált ismétlések, fájdalommentes tartományban."
    words = raw.replace(".", " ").split()
    return " ".join(words[:15]).strip()


def _apply_restrictions_exclusion(
    *,
    exercise: Exercise,
    active_restrictions: Iterable[MemberRestriction],
) -> tuple[bool, str]:
    """
    Returns (is_allowed, safety_note).

    MVP rule:
    - For AVOID: if restriction maps to exercise.primary_muscle, exclude.
    - For LIMIT: allow but attach a safety note to reduce volume later (not hard-excluded).
    - For NOTE/MODIFY: allow, attach note/safety hint (MODIFY will be treated like LIMIT).
    """

    # Mapping from MemberRestriction.body_area values to Exercise.MuscleGroup values.
    # Keep this deterministic and MVP-sized.
    body_area_map: dict[str, set[str]] = {
        Exercise.MuscleGroup.FULL_BODY: {Exercise.MuscleGroup.FULL_BODY},
        "full_body": {Exercise.MuscleGroup.FULL_BODY},
        "back": {Exercise.MuscleGroup.BACK},
        "chest": {Exercise.MuscleGroup.CHEST},
        "shoulders": {Exercise.MuscleGroup.SHOULDERS},
        "arms": {Exercise.MuscleGroup.BICEPS, Exercise.MuscleGroup.TRICEPS},
        "hips": {Exercise.MuscleGroup.GLUTES, Exercise.MuscleGroup.HAMSTRINGS},
        "knees": {Exercise.MuscleGroup.QUADRICEPS, Exercise.MuscleGroup.HAMSTRINGS},
        "ankles": {Exercise.MuscleGroup.CALVES},
        "core": {Exercise.MuscleGroup.CORE},
        "other": {Exercise.MuscleGroup.OTHER},
    }

    primary = exercise.primary_muscle
    safety_notes: list[str] = []

    for r in active_restrictions:
        if not r.active:
            continue

        rtype = (r.restriction_type or "").lower()
        body_area = (r.body_area or "").lower()
        affected_muscles = body_area_map.get(body_area, {Exercise.MuscleGroup.OTHER})

        hits_muscle = primary in affected_muscles or (body_area == "full_body")

        if hits_muscle and rtype == "avoid":
            # Soft check for also matching contraindication keyword conventions:
            contraind = (exercise.contraindications or "").lower()
            # Accept both plural and singular keyword variants for basic MVP robustness.
            keyword_variants = {body_area}
            if body_area.endswith("s"):
                keyword_variants.add(body_area[:-1])
            if any(k in contraind for k in keyword_variants) or hits_muscle:
                return False, f"A korlátozás miatt kerülendő ({body_area})."

        if hits_muscle and rtype in {"limit", "modify"}:
            # Allowed but safety note will influence volume/prescription later.
            desc = (r.description or "").strip()
            suffix = f" ({desc})" if desc else ""
            safety_notes.append(f"Óvatosabb terhelés: {rtype} korlátozás a következőn: {body_area}.{suffix}")

        if hits_muscle and rtype == "note":
            desc = (r.description or "").strip()
            suffix = f" ({desc})" if desc else ""
            safety_notes.append(f"Megjegyzés ehhez a testtájhoz: {body_area}.{suffix}")

    return True, " ".join(safety_notes).strip()


def _score_candidate(
    *,
    exercise: Exercise,
    required_muscle: str,
    allowed_difficulties: set[str],
    energy_level: str,
    soreness_level: str,
    goal: str,
    active_restrictions: Iterable[MemberRestriction],
    recent_exercises: set[str],
    equipment_available: Optional[set[str]],
) -> tuple[int, str]:
    """
    Deterministic scoring; higher is better.
    Returns (score, safety_note).
    """
    # Hard filters already applied in selector, but keep scoring aware of safety notes.
    allowed, safety_note = _apply_restrictions_exclusion(exercise=exercise, active_restrictions=active_restrictions)
    if not allowed:
        return -10_000, safety_note

    # Equipment filtering (if given).
    if equipment_available is not None:
        if exercise.equipment not in equipment_available:
            return -5_000, safety_note

    # Difficulty gating.
    if exercise.difficulty not in allowed_difficulties:
        return -4_000, safety_note

    score = 0

    # Required muscle alignment.
    if exercise.primary_muscle == required_muscle:
        score += 120
    else:
        # Allow some flexibility for exercises that mark "full_body"/"other" as primary.
        if exercise.primary_muscle == Exercise.MuscleGroup.FULL_BODY:
            score += 30
        elif exercise.primary_muscle == Exercise.MuscleGroup.OTHER:
            score += 5

    # Category bias by goal.
    goal_norm = _normalize_choice_value(goal)
    if required_muscle in {Exercise.MuscleGroup.CORE}:
        # Core slot: prefer core category.
        if exercise.category in {Exercise.Category.CORE}:
            score += 35

    if goal_norm == "strength" and exercise.category in {Exercise.Category.STRENGTH}:
        score += 25
    elif goal_norm == "hypertrophy" and exercise.category in {Exercise.Category.HYPERTROPHY}:
        score += 25
    elif goal_norm == "rehab_prevention" and exercise.category in {Exercise.Category.REHAB, Exercise.Category.MOBILITY}:
        score += 30

    # Difficulty closeness:
    # Prefer beginner when energy is low, prefer advanced when energy is high and soreness is low.
    energy = _normalize_choice_value(energy_level)
    soreness = _normalize_choice_value(soreness_level)
    if energy == "low" or soreness in {"moderate", "severe"}:
        preferred = "beginner"
    elif energy == "high" and soreness == "none":
        preferred = "advanced"
    else:
        preferred = "intermediate"

    if exercise.difficulty == preferred:
        score += 22
    elif exercise.difficulty in allowed_difficulties:
        score += 12

    # Recent repetition penalty.
    if exercise.slug in recent_exercises:
        score -= 40

    # Restrictions limit safety already handled as safety_note; also reduce score slightly to prefer "unrestricted" options.
    if safety_note:
        score -= 8

    return score, safety_note


def _prescription_for_block(
    *,
    goal: str,
    training_level: str,
    block_type: str,
    energy_level: str,
    soreness_level: str,
    limit_factor: float,
    exercise: Optional[Exercise] = None,
) -> dict:
    """
    Compute deterministic prescription values (sets/reps/rest/tempo).
    `limit_factor` comes from restriction types affecting volume (0.0..1.0).
    """
    g = _normalize_choice_value(goal)
    tl = _normalize_choice_value(training_level)
    energy = _normalize_choice_value(energy_level)
    soreness = _normalize_choice_value(soreness_level)

    # Base sets by goal + block type.
    if g == "strength":
        base_main = 4
        base_accessory = 3
        base_warmup = 2
        base_cooldown = 2
        reps_main = "3-6"
        reps_accessory = "6-10"
        reps_warmup = "6-8"
        reps_cooldown = "8-12"
        rest_main = 180
        rest_accessory = 120
        rest_warmup = 60
        rest_cooldown = 60
        tempo_main = "2-0-2"
        tempo_accessory = "2-0-2"
        tempo_warmup = "2-1-2"
        tempo_cooldown = "3-0-2"
    elif g == "hypertrophy":
        base_main = 3
        base_accessory = 3
        base_warmup = 2
        base_cooldown = 2
        reps_main = "8-12"
        reps_accessory = "10-15"
        reps_warmup = "8-10"
        reps_cooldown = "12-15"
        rest_main = 120
        rest_accessory = 90
        rest_warmup = 60
        rest_cooldown = 60
        tempo_main = "3-0-2"
        tempo_accessory = "2-0-2"
        tempo_warmup = "2-1-2"
        tempo_cooldown = "2-0-2"
    elif g == "rehab_prevention":
        base_main = 2
        base_accessory = 2
        base_warmup = 2
        base_cooldown = 2
        reps_main = "6-10"
        reps_accessory = "8-12"
        reps_warmup = "8-10"
        reps_cooldown = "10-12"
        rest_main = 90
        rest_accessory = 75
        rest_warmup = 60
        rest_cooldown = 60
        tempo_main = "2-1-2"
        tempo_accessory = "2-0-2"
        tempo_warmup = "2-1-2"
        tempo_cooldown = "2-0-2"
    else:
        # general_fitness / fat_loss / fallback
        base_main = 3
        base_accessory = 2
        base_warmup = 2
        base_cooldown = 2
        reps_main = "6-12"
        reps_accessory = "10-15"
        reps_warmup = "6-10"
        reps_cooldown = "12-15"
        rest_main = 120
        rest_accessory = 90
        rest_warmup = 60
        rest_cooldown = 60
        tempo_main = "2-0-2"
        tempo_accessory = "2-0-2"
        tempo_warmup = "2-1-2"
        tempo_cooldown = "2-0-2"

    # Training level adjustment.
    if tl == "beginner":
        training_delta = -1
    elif tl == "advanced":
        training_delta = 1
    else:
        training_delta = 0

    # Energy/soreness conservatism.
    energy_delta = -1 if energy == "low" else 0
    soreness_delta = -1 if soreness in {"moderate", "severe"} else 0

    if block_type == "main":
        sets = base_main + training_delta + energy_delta + soreness_delta
        reps = reps_main
        rest = rest_main
        tempo = tempo_main
    elif block_type == "accessory":
        sets = base_accessory + energy_delta + soreness_delta
        reps = reps_accessory
        rest = rest_accessory
        tempo = tempo_accessory
    elif block_type == "warmup":
        sets = base_warmup + min(0, energy_delta)  # don't add more for beginner; keep warmup stable
        reps = reps_warmup
        rest = rest_warmup
        tempo = tempo_warmup
    else:
        sets = base_cooldown
        reps = reps_cooldown
        rest = rest_cooldown
        tempo = tempo_cooldown

    # Apply restriction volume factor (0.0..1.0).
    sets = int(round(sets * _clamp_int(int(limit_factor * 100), lo=0, hi=100) / 100))

    # Safety floor.
    if block_type in {"main", "accessory"}:
        sets = max(1, sets)
    else:
        sets = max(1, sets)

    if exercise is not None and _is_isometric(exercise):
        if block_type == "warmup":
            reps = "20-30 sec"
        elif block_type == "cooldown":
            reps = "45-60 sec"
        else:
            reps = "30-60 sec"

    if exercise is not None:
        tempo = _tempo_for_exercise(exercise=exercise, suggested_tempo=tempo)

    return {"sets": sets, "reps": reps, "rest_seconds": rest, "tempo": tempo}


def generate_deterministic_one_day_workout(
    *,
    member: MemberProfile,
    active_restrictions: Iterable[MemberRestriction],
    session_params: SessionParams,
    available_exercises: Iterable[Exercise],
    recent_exercises_slugs: Optional[Iterable[str]] = None,
    equipment_available: Optional[Iterable[str]] = None,
) -> dict:
    """
    Deterministically generate a one-day gym workout (no AI).

    Input contract:
    - member: member profile with training_level and primary_goal
    - active_restrictions: restrictions where active=True (or any iterable; function re-checks)
    - session_params: session constraints (goal/energy/soreness/available_time)
    - available_exercises: Exercise rows (already pre-filtered or full library)
    - recent_exercises_slugs: list of exercise slugs used recently to reduce repetition
    - equipment_available: allowed equipment types; if None, equipment filtering is skipped

    Output contract (normalized):
    {
      "title": str,
      "objective": str,
      "estimated_duration_minutes": int,
      "warmup_items": [item, ...],
      "main_block": [item, ...],
      "accessory_block": [item, ...],
      "cooldown_items": [item, ...],
    }
    """

    goal = session_params.goal or member.primary_goal
    counts = _counts_from_duration(session_params.available_time)

    main_muscles = _goal_to_main_muscles(goal, counts)
    accessory_muscles = _goal_to_accessory_muscles(goal, counts)
    warmup_muscles = _warmup_muscles(main_muscles, counts["warmup"])
    core_count = 1 if (sum(counts.values()) + 1) <= 10 else 0
    core_muscles = _core_slot_muscles(core_count)
    main_slot_targets = _main_movement_slot_targets(counts["main"])

    # Candidate pool: start from provided exercises, then apply deterministic filters.
    exercises = list(available_exercises)
    allowed_difficulties = _allowed_difficulties(
        member.training_level,
        energy_level=session_params.energy_level,
        soreness_level=session_params.soreness_level,
        goal=goal,
    )

    equipment_set = set(equipment_available) if equipment_available is not None else None
    recent_set = set(recent_exercises_slugs or [])

    # Helper for restriction limit factor:
    # If a restriction affects a muscle with type=limit/modify, reduce sets (deterministic).
    def limit_factor_for_required_muscle(required_muscle: str) -> float:
        body_area_map: dict[str, set[str]] = {
            Exercise.MuscleGroup.FULL_BODY: {Exercise.MuscleGroup.FULL_BODY},
            "full_body": {Exercise.MuscleGroup.FULL_BODY},
            "back": {Exercise.MuscleGroup.BACK},
            "chest": {Exercise.MuscleGroup.CHEST},
            "shoulders": {Exercise.MuscleGroup.SHOULDERS},
            "arms": {Exercise.MuscleGroup.BICEPS, Exercise.MuscleGroup.TRICEPS},
            "hips": {Exercise.MuscleGroup.GLUTES, Exercise.MuscleGroup.HAMSTRINGS},
            "knees": {Exercise.MuscleGroup.QUADRICEPS, Exercise.MuscleGroup.HAMSTRINGS},
            "ankles": {Exercise.MuscleGroup.CALVES},
            "core": {Exercise.MuscleGroup.CORE},
            "other": {Exercise.MuscleGroup.OTHER},
        }
        affected_required_muscle = {required_muscle}
        for r in active_restrictions:
            if not r.active:
                continue
            if (r.restriction_type or "").lower() not in {"limit", "modify"}:
                continue
            body_area = (r.body_area or "").lower()
            affected_muscles = body_area_map.get(body_area, set())
            if affected_required_muscle & affected_muscles:
                # Reduce volume by 20% for limit/modify.
                return 0.8
        return 1.0

    # Estimated duration heuristic (deterministic).
    estimated = (
        counts["warmup"] * 6
        + counts["main"] * 9
        + counts["accessory"] * 7
        + counts["cooldown"] * 5
    )
    estimated = int(max(15, min(session_params.available_time, estimated or session_params.available_time)))

    title = f"Egynapos konditerem-edzés — {member.full_name}"
    objective = _objective_for_goal(goal)

    # Selection state to avoid duplicates inside a single plan.
    selected: set[str] = set()

    def select_for_slot(required_muscle: str, *, block_type: str, main_slot_target: Optional[str] = None) -> dict:
        """
        Select one exercise deterministically for the given slot.
        """

        def matches_slot_muscle(ex: Exercise) -> bool:
            # Muscle match: for warmup/core slots we allow full_body/core as fallback.
            if block_type in {"warmup", "cooldown"}:
                if block_type == "cooldown":
                    return True
                if required_muscle == Exercise.MuscleGroup.CORE:
                    return ex.primary_muscle in {
                        Exercise.MuscleGroup.CORE,
                        Exercise.MuscleGroup.FULL_BODY,
                        Exercise.MuscleGroup.OTHER,
                    }
                return ex.primary_muscle == required_muscle or ex.primary_muscle in {Exercise.MuscleGroup.FULL_BODY}

            if ex.primary_muscle == required_muscle:
                return True
            if required_muscle != Exercise.MuscleGroup.OTHER and ex.primary_muscle == Exercise.MuscleGroup.FULL_BODY:
                return True
            return False

        def matches_block_category(ex: Exercise) -> bool:
            if block_type == "warmup":
                if _is_compound_strength(ex):
                    return False
                return ex.category in {
                    Exercise.Category.MOBILITY,
                    Exercise.Category.CORE,
                    Exercise.Category.CARDIO,
                    Exercise.Category.REHAB,
                }
            if block_type == "cooldown":
                # Mobility/rehab/core plus light cardio (many DBs tag easy walks / slow conditioning as cardio).
                return ex.category in {
                    Exercise.Category.MOBILITY,
                    Exercise.Category.REHAB,
                    Exercise.Category.CORE,
                    Exercise.Category.CARDIO,
                }
            return True

        # Block-aware candidate narrowing (deterministic, readable).
        candidates: list[Exercise] = []
        restrictions_for_scoring: Iterable[MemberRestriction] = active_restrictions
        relaxed_restriction_fallback = False
        for ex in exercises:
            if not getattr(ex, "active", True):
                continue

            if not matches_slot_muscle(ex):
                continue
            if not matches_block_category(ex):
                continue

            # Deterministic restriction exclusion/allowance.
            allowed, safety_note = _apply_restrictions_exclusion(
                exercise=ex,
                active_restrictions=active_restrictions,
            )
            if not allowed:
                continue

            # Avoid duplicates in-plan if possible.
            if ex.slug in selected:
                continue

            candidates.append(ex)

        # Fallback: relax muscle matching but keep uniqueness inside the workout.
        if not candidates:
            for ex in exercises:
                if not getattr(ex, "active", True):
                    continue
                if not matches_block_category(ex):
                    continue
                allowed, _ = _apply_restrictions_exclusion(exercise=ex, active_restrictions=active_restrictions)
                if not allowed:
                    continue
                if ex.slug in selected:
                    continue
                candidates.append(ex)

        # Safety-net fallback: if restrictions (e.g. avoid full_body) remove everything,
        # relax restriction filtering to keep the MVP usable.
        if not candidates:
            relaxed_restriction_fallback = True
            restrictions_for_scoring = []
            for ex in exercises:
                if not getattr(ex, "active", True):
                    continue
                if not matches_block_category(ex):
                    continue
                if ex.slug in selected:
                    continue
                candidates.append(ex)

        # Cooldown: if every mobility/cardio/rehab/core option is already used earlier, reuse one (validator allows one duplicate for cooldown).
        if block_type == "cooldown" and not candidates:
            for ex in exercises:
                if not getattr(ex, "active", True):
                    continue
                if not matches_block_category(ex):
                    continue
                allowed, _ = _apply_restrictions_exclusion(exercise=ex, active_restrictions=active_restrictions)
                if not allowed:
                    continue
                candidates.append(ex)
        if block_type == "cooldown" and not candidates:
            relaxed_restriction_fallback = True
            restrictions_for_scoring = []
            for ex in exercises:
                if not getattr(ex, "active", True):
                    continue
                if not matches_block_category(ex):
                    continue
                candidates.append(ex)

        # Score and pick best.
        best = None
        best_score = -10**9
        best_safety = ""

        limit_factor = limit_factor_for_required_muscle(required_muscle)
        for ex in candidates:
            score, safety_note = _score_candidate(
                exercise=ex,
                required_muscle=required_muscle,
                allowed_difficulties=allowed_difficulties,
                energy_level=session_params.energy_level,
                soreness_level=session_params.soreness_level,
                goal=goal,
                active_restrictions=restrictions_for_scoring,
                recent_exercises=recent_set,
                equipment_available=equipment_set,
            )
            # Encourage category fit on warmup/main/accessory.
            if block_type == "warmup" and ex.category in {Exercise.Category.MOBILITY, Exercise.Category.CORE, Exercise.Category.REHAB}:
                score += 10
            if block_type == "cooldown" and ex.category in {
                Exercise.Category.MOBILITY,
                Exercise.Category.CORE,
                Exercise.Category.REHAB,
                Exercise.Category.CARDIO,
            }:
                score += 8
            if block_type == "main" and main_slot_target:
                inferred = _movement_slot_for_exercise(ex)
                if inferred == main_slot_target:
                    score += 45
                elif main_slot_target == "horizontal_pull" and _name_contains_any(ex, {"row"}):
                    score += 30
            if score > best_score or (score == best_score and (best is None or ex.slug < best.slug)):
                best = ex
                best_score = score
                best_safety = safety_note

        if best is None:
            # Extreme fallback: return an empty slot with a placeholder note.
            return {
                "exercise": None,
                "prescription": {},
                "safety_notes": "Nem található megfelelő gyakorlat ehhez a helyhez.",
                "block_type": block_type,
            }

        selected.add(best.slug)

        # Prescriptions.
        pres = _prescription_for_block(
            goal=goal,
            training_level=member.training_level,
            block_type=block_type,
            energy_level=session_params.energy_level,
            soreness_level=session_params.soreness_level,
            limit_factor=limit_factor,
            exercise=best,
        )

        # Minimal notes for traceability.
        notes = []
        cue = _coaching_cue_for_exercise(best)
        if cue:
            notes.append(cue)
        if best_safety:
            notes.append(best_safety)
        if relaxed_restriction_fallback:
            notes.append("Korlátozás-fallback: a terv enyhített szűréssel készült.")

        if block_type == "main" and best.category in {Exercise.Category.STRENGTH, Exercise.Category.HYPERTROPHY}:
            notes.append("Válassz olyan terhelést, hogy kb. 2 tartalék ismétlés maradjon (RPE 7–8).")

        return {
            "exercise": {
                "slug": best.slug,
                "name": best.name,
                "equipment": best.equipment,
                "difficulty": best.difficulty,
                "category": best.category,
                "primary_muscle": best.primary_muscle,
            },
            "block_type": block_type,
            "prescription": {
                "sets": pres["sets"],
                "reps": pres["reps"],
                "rest_seconds": pres["rest_seconds"],
                "tempo": pres["tempo"],
            },
            "safety_notes": " ".join(notes).strip(),
        }

    # Build blocks.
    warmup_items = [select_for_slot(m, block_type="warmup") for m in warmup_muscles]
    main_block = [
        select_for_slot(m, block_type="main", main_slot_target=main_slot_targets[idx] if idx < len(main_slot_targets) else None)
        for idx, m in enumerate(main_muscles)
    ]
    accessory_block = [select_for_slot(m, block_type="accessory") for m in accessory_muscles]
    core_block = [select_for_slot(m, block_type="main") for m in core_muscles]
    # Cooldown focuses on core/mobility: pick from CORE first then FULL_BODY.
    cooldown_muscles = ["other"] * counts["cooldown"]
    cooldown_items = [select_for_slot(m, block_type="cooldown") for m in cooldown_muscles[: counts["cooldown"]]]

    return {
        "title": title,
        "objective": objective,
        "estimated_duration_minutes": estimated,
        "warmup_items": warmup_items,
        "main_block": main_block + core_block,
        "accessory_block": accessory_block,
        "cooldown_items": cooldown_items,
    }

