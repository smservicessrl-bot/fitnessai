from django.db import models
from django.utils.translation import gettext_lazy as _, pgettext_lazy


class Exercise(models.Model):
    class Category(models.TextChoices):
        STRENGTH = "strength", _("Strength")
        HYPERTROPHY = "hypertrophy", _("Hypertrophy")
        MOBILITY = "mobility", _("Mobility")
        CORE = "core", _("Core")
        CARDIO = "cardio", _("Cardio")
        REHAB = "rehab", _("Rehab / prevention")

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", _("Beginner")
        INTERMEDIATE = "intermediate", _("Intermediate")
        ADVANCED = "advanced", _("Advanced")

    class Equipment(models.TextChoices):
        BARBELL = "barbell", _("Barbell")
        DUMBBELL = "dumbbell", _("Dumbbell")
        KETTLEBELL = "kettlebell", _("Kettlebell")
        MACHINE = "machine", _("Machine")
        CABLE = "cable", _("Cable")
        BAND = "band", _("Resistance band")
        BODYWEIGHT = "bodyweight", _("Bodyweight")
        CARDIO_MACHINE = "cardio_machine", _("Cardio machine")
        OTHER = "other", _("Other")

    class MuscleGroup(models.TextChoices):
        FULL_BODY = "full_body", _("Full body")
        CHEST = "chest", _("Chest")
        BACK = "back", pgettext_lazy("body area", "Back")
        SHOULDERS = "shoulders", _("Shoulders")
        BICEPS = "biceps", _("Biceps")
        TRICEPS = "triceps", _("Triceps")
        QUADRICEPS = "quadriceps", _("Quadriceps")
        HAMSTRINGS = "hamstrings", _("Hamstrings")
        GLUTES = "glutes", _("Glutes")
        CALVES = "calves", _("Calves")
        CORE = "core", _("Core")
        OTHER = "other", _("Other")

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=140, unique=True)

    category = models.CharField(max_length=30, choices=Category.choices, default=Category.STRENGTH)

    primary_muscle = models.CharField(
        max_length=30,
        choices=MuscleGroup.choices,
        db_index=True,
        default=MuscleGroup.OTHER,
    )
    # MVP uses JSON to keep the library flexible (secondary muscles can be 0..N).
    # Expected shape: ["chest", "triceps", ...] (values should come from MuscleGroup.choices).
    secondary_muscles = models.JSONField(default=list, blank=True)

    # MVP uses a single primary equipment type to keep admin filtering simple.
    equipment = models.CharField(max_length=30, choices=Equipment.choices, db_index=True, default=Equipment.OTHER)
    difficulty = models.CharField(max_length=30, choices=Difficulty.choices, db_index=True, default=Difficulty.BEGINNER)

    # For MVP, store contraindications as searchable free-text notes.
    contraindications = models.TextField(blank=True, default="")

    instructions = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-active", "name"]
        verbose_name = _("Exercise")
        verbose_name_plural = _("Exercises")

    def __str__(self) -> str:
        return self.name


class ExerciseSubstitution(models.Model):
    """
    Stores substitution candidates in a human-manageable way.

    For example: barbell bench -> dumbbell bench when equipment is limited or contraindications apply.
    """

    from_exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="substitutions_from",
    )
    to_exercise = models.ForeignKey(
        Exercise,
        on_delete=models.CASCADE,
        related_name="substitutions_to",
    )

    reason = models.CharField(max_length=255, blank=True, default="")
    priority = models.IntegerField(default=0, help_text=_("Higher-priority substitutions take precedence."))
    active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-active", "-priority", "from_exercise_id", "to_exercise_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_exercise", "to_exercise"],
                name="unique_exercise_substitution_pair",
            )
        ]
        verbose_name = _("Exercise substitution")
        verbose_name_plural = _("Exercise substitutions")

    def __str__(self) -> str:
        return f"{self.from_exercise.name} -> {self.to_exercise.name}"
