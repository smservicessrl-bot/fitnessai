from django.conf import settings
from django.db import models


def _empty_plan_json() -> dict:
    return {}


def _empty_exercise_slugs() -> list:
    return []


class WorkoutPlan(models.Model):
    class SessionType(models.TextChoices):
        ONE_DAY_GYM = "gym_one_day", "Konditerem (egy nap)"

    class Goal(models.TextChoices):
        STRENGTH = "strength", "Erő"
        HYPERTROPHY = "hypertrophy", "Izomtömeg"
        FAT_LOSS = "fat_loss", "Zsírégetés"
        GENERAL_FITNESS = "general_fitness", "Általános kondíció"
        REHAB_PREVENTION = "rehab_prevention", "Rehabilitáció / megelőzés"

    class EnergyLevel(models.TextChoices):
        LOW = "low", "Alacsony"
        MEDIUM = "medium", "Közepes"
        HIGH = "high", "Magas"

    # Soreness is subjective; for MVP we keep it as a small rating scale.
    class SorenessLevel(models.TextChoices):
        NONE = "none", "Nincs"
        MILD = "mild", "Enyhe"
        MODERATE = "moderate", "Közepes"
        SEVERE = "severe", "Erős"

    member = models.ForeignKey(
        "members.MemberProfile",
        on_delete=models.CASCADE,
        related_name="workout_plans",
    )
    # Who generated/created the plan on the tablet.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="workout_plans_created",
        null=True,
        blank=True,
        help_text="A tervet létrehozó felhasználó (edző / személyzet).",
    )

    session_type = models.CharField(max_length=40, choices=SessionType.choices, default=SessionType.ONE_DAY_GYM)
    goal = models.CharField(max_length=30, choices=Goal.choices, default=Goal.GENERAL_FITNESS)

    available_time = models.PositiveSmallIntegerField(
        default=60,
        help_text="Az edzésre fordítható idő percben.",
    )
    energy_level = models.CharField(max_length=10, choices=EnergyLevel.choices, default=EnergyLevel.MEDIUM)
    soreness_level = models.CharField(
        max_length=15,
        choices=SorenessLevel.choices,
        default=SorenessLevel.NONE,
    )

    notes = models.TextField(blank=True, default="")
    ai_generated = models.BooleanField(default=False, db_index=True)
    generated_context_json = models.JSONField(
        default=dict,
        blank=True,
        help_text="A tervezőmotor által használt napló / hibakeresési kontextus (csak szűrt adat).",
    )
    generated_plan_json = models.JSONField(
        default=_empty_plan_json,
        blank=True,
        help_text="Teljes, érvényesített edzésjavaslat (bemelegítés / főblokk / kiegészítő / levezetés). Ha ki van töltve, ez az igazság forrása.",
    )
    exercise_slugs = models.JSONField(
        default=_empty_exercise_slugs,
        blank=True,
        help_text="A tervben szereplő gyakorlatok slug-jai sorrendben (ismétlődés és gyors számlálás).",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Edzésterv"
        verbose_name_plural = "Edzéstervek"

    def __str__(self) -> str:
        return f"WorkoutPlan for {self.member.full_name} ({self.session_type}, {self.created_at:%Y-%m-%d})"

    @property
    def exercise_count(self) -> int:
        if self.exercise_slugs:
            return len(self.exercise_slugs)
        if self.generated_plan_json:
            from workouts.plan_display import extract_exercise_slugs_from_proposal

            return len(extract_exercise_slugs_from_proposal(self.generated_plan_json))
        return self.exercises.count()


class WorkoutExercise(models.Model):
    class BlockType(models.TextChoices):
        WARMUP = "warmup", "Bemelegítés"
        MAIN_WORK = "main_work", "Fő munka"
        COOLDOWN = "cooldown", "Levezetés"

    workout_plan = models.ForeignKey(
        WorkoutPlan,
        on_delete=models.CASCADE,
        related_name="exercises",
    )
    exercise = models.ForeignKey(
        "exercises.Exercise",
        on_delete=models.PROTECT,
        related_name="workout_usages",
    )

    order = models.PositiveSmallIntegerField(help_text="Megjelenítési / végrehajtási sorrend a terven belül.")
    block_type = models.CharField(max_length=20, choices=BlockType.choices, default=BlockType.MAIN_WORK)

    sets = models.PositiveSmallIntegerField(default=3)
    reps = models.CharField(max_length=30, blank=True, default="", help_text="Ismétlések (pl. „8–12”, „10”, „idő:45 mp”).")
    rest_seconds = models.PositiveSmallIntegerField(default=90)
    tempo = models.CharField(max_length=20, blank=True, default="", help_text="Tempó (pl. „2-0-2”).")
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["workout_plan_id", "order"]
        verbose_name = "Edzés gyakorlat"
        verbose_name_plural = "Edzés gyakorlatok"
        constraints = [
            models.UniqueConstraint(
                fields=["workout_plan", "order"],
                name="unique_exercise_order_within_plan",
            )
        ]

    def __str__(self) -> str:
        return f"{self.workout_plan_id}:#{self.order} {self.exercise.name} ({self.block_type})"


class WorkoutFeedback(models.Model):
    class EnergyAfter(models.TextChoices):
        LOW = "low", "Alacsony"
        MEDIUM = "medium", "Közepes"
        HIGH = "high", "Magas"

    workout_plan = models.ForeignKey(
        WorkoutPlan,
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    completed = models.BooleanField(default=False, db_index=True)

    # Keep MVP ratings as small integers for easy UI sliders.
    difficulty_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Szubjektív nehézség (pl. 1–10).",
    )
    energy_after = models.CharField(max_length=10, choices=EnergyAfter.choices, default=EnergyAfter.MEDIUM)
    pain_flag = models.BooleanField(
        default=False,
        help_text="A tag fájdalmat jelzett-e, ami miatt módosítani kell a tervet.",
    )
    feedback_notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Edzés visszajelzés"
        verbose_name_plural = "Edzés visszajelzések"

    def __str__(self) -> str:
        return f"Feedback for plan {self.workout_plan_id} (completed={self.completed})"


class WorkoutPlanQuestion(models.Model):
    """
    Member/trainer Q&A tied to a specific generated workout plan.
    """

    workout_plan = models.ForeignKey(
        WorkoutPlan,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    asked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workout_plan_questions",
    )
    question_text = models.TextField()
    answer_text = models.TextField(blank=True, default="")
    answer_source = models.CharField(max_length=30, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Edzésterv kérdés"
        verbose_name_plural = "Edzésterv kérdések"

    def __str__(self) -> str:
        return f"Q#{self.pk} plan={self.workout_plan_id}"

