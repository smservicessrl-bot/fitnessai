from django.db import models


class Exercise(models.Model):
    class Category(models.TextChoices):
        STRENGTH = "strength", "Erő"
        HYPERTROPHY = "hypertrophy", "Izomtömeg"
        MOBILITY = "mobility", "Mobilitás"
        CORE = "core", "Törzs"
        CARDIO = "cardio", "Kardió"
        REHAB = "rehab", "Rehabilitáció / megelőzés"

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Kezdő"
        INTERMEDIATE = "intermediate", "Középhaladó"
        ADVANCED = "advanced", "Haladó"

    class Equipment(models.TextChoices):
        BARBELL = "barbell", "Rúd"
        DUMBBELL = "dumbbell", "Súlyzó"
        KETTLEBELL = "kettlebell", "Kettlebell"
        MACHINE = "machine", "Gép"
        CABLE = "cable", "Kábel"
        BAND = "band", "Ellenállási szalag"
        BODYWEIGHT = "bodyweight", "Saját testsúly"
        CARDIO_MACHINE = "cardio_machine", "Kardió gép"
        OTHER = "other", "Egyéb"

    class MuscleGroup(models.TextChoices):
        FULL_BODY = "full_body", "Teljes test"
        CHEST = "chest", "Mell"
        BACK = "back", "Hát"
        SHOULDERS = "shoulders", "Váll"
        BICEPS = "biceps", "Bicepsz"
        TRICEPS = "triceps", "Tricepsz"
        QUADRICEPS = "quadriceps", "Combizom"
        HAMSTRINGS = "hamstrings", "Comhajlítók"
        GLUTES = "glutes", "Farizom"
        CALVES = "calves", "Vádli"
        CORE = "core", "Törzs"
        OTHER = "other", "Egyéb"

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
    # Example entries:
    # - "knee pain: avoid deep flexion"
    # - "shoulder impingement: avoid overhead press"
    contraindications = models.TextField(blank=True, default="")

    instructions = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-active", "name"]
        verbose_name = "Gyakorlat"
        verbose_name_plural = "Gyakorlatok"

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
    priority = models.IntegerField(default=0, help_text="Magasabb prioritású helyettesítések előnyben.")
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
        verbose_name = "Gyakorlat helyettesítés"
        verbose_name_plural = "Gyakorlat helyettesítések"

    def __str__(self) -> str:
        return f"{self.from_exercise.name} -> {self.to_exercise.name}"

