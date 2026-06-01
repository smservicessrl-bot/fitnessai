from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def _empty_plan_json() -> dict:
    return {}


def _empty_exercise_slugs() -> list:
    return []


class WorkoutPlan(models.Model):
    class SessionType(models.TextChoices):
        ONE_DAY_GYM = "gym_one_day", _("Gym (single day)")

    class Goal(models.TextChoices):
        STRENGTH = "strength", _("Strength")
        HYPERTROPHY = "hypertrophy", _("Hypertrophy")
        FAT_LOSS = "fat_loss", _("Fat loss")
        GENERAL_FITNESS = "general_fitness", _("General fitness")
        REHAB_PREVENTION = "rehab_prevention", _("Rehab / prevention")

    class EnergyLevel(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")

    # Soreness is subjective; for MVP we keep it as a small rating scale.
    class SorenessLevel(models.TextChoices):
        NONE = "none", _("None")
        MILD = "mild", _("Mild")
        MODERATE = "moderate", _("Moderate")
        SEVERE = "severe", _("Severe")

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
        help_text=_("User who created the plan (coach / staff)."),
    )

    session_type = models.CharField(max_length=40, choices=SessionType.choices, default=SessionType.ONE_DAY_GYM)
    goal = models.CharField(max_length=30, choices=Goal.choices, default=Goal.GENERAL_FITNESS)

    available_time = models.PositiveSmallIntegerField(
        default=60,
        help_text=_("Available time for the workout in minutes."),
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
        help_text=_("Planner engine log / debug context (filtered data only)."),
    )
    generated_plan_json = models.JSONField(
        default=_empty_plan_json,
        blank=True,
        help_text=_("Full validated workout proposal (warm-up / main / accessory / cool-down). When set, this is the source of truth."),
    )
    exercise_slugs = models.JSONField(
        default=_empty_exercise_slugs,
        blank=True,
        help_text=_("Slugs of exercises in the plan in order (used for repetition control and fast counting)."),
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Workout plan")
        verbose_name_plural = _("Workout plans")

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
        WARMUP = "warmup", _("Warm-up")
        MAIN_WORK = "main_work", _("Main work")
        COOLDOWN = "cooldown", _("Cool-down")

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

    order = models.PositiveSmallIntegerField(help_text=_("Display / execution order within the plan."))
    block_type = models.CharField(max_length=20, choices=BlockType.choices, default=BlockType.MAIN_WORK)

    sets = models.PositiveSmallIntegerField(default=3)
    reps = models.CharField(max_length=30, blank=True, default="", help_text=_("Reps (e.g. “8–12”, “10”, “time:45 s”)."))
    rest_seconds = models.PositiveSmallIntegerField(default=90)
    tempo = models.CharField(max_length=20, blank=True, default="", help_text=_("Tempo (e.g. “2-0-2”)."))
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["workout_plan_id", "order"]
        verbose_name = _("Workout exercise")
        verbose_name_plural = _("Workout exercises")
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
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")

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
        help_text=_("Subjective difficulty (e.g. 1–10)."),
    )
    energy_after = models.CharField(max_length=10, choices=EnergyAfter.choices, default=EnergyAfter.MEDIUM)
    pain_flag = models.BooleanField(
        default=False,
        help_text=_("Whether the member reported pain that should adjust the plan."),
    )
    feedback_notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Workout feedback")
        verbose_name_plural = _("Workout feedback entries")

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
        verbose_name = _("Workout plan question")
        verbose_name_plural = _("Workout plan questions")

    def __str__(self) -> str:
        return f"Q#{self.pk} plan={self.workout_plan_id}"
