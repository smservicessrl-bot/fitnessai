from django.conf import settings
from django.db import models

from members.phone import normalize_phone


class MemberProfile(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "female", "Nő"
        MALE = "male", "Férfi"
        UNSPECIFIED = "unspecified", "Nincs megadva"

    class TrainingLevel(models.TextChoices):
        BEGINNER = "beginner", "Kezdő"
        INTERMEDIATE = "intermediate", "Középhaladó"
        ADVANCED = "advanced", "Haladó"

    class PrimaryGoal(models.TextChoices):
        STRENGTH = "strength", "Erő"
        HYPERTROPHY = "hypertrophy", "Izomtömeg"
        FAT_LOSS = "fat_loss", "Zsírégetés"
        GENERAL_FITNESS = "general_fitness", "Általános kondíció"
        REHAB_PREVENTION = "rehab_prevention", "Rehabilitáció / megelőzés"

    class WeeklyWorkoutFrequency(models.TextChoices):
        DAYS_1_2 = "1_2", "1–2 nap"
        DAYS_3_4 = "3_4", "3–4 nap"
        DAYS_5_7 = "5_7", "5–7 nap"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
        null=True,
        blank=True,
        help_text="Opcionális kapcsolat a tag Django-felhasználójához.",
    )

    full_name = models.CharField(max_length=150)
    phone = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Megjelenített telefonszám (tag saját fiókja vagy edző által megadva).",
    )
    phone_normalized = models.CharField(
        max_length=32,
        blank=True,
        default="",
        db_index=True,
        help_text="Csak számjegyek (egységes kereséshez); üres, ha nincs telefon.",
    )
    # MVP keeps `age` as an input to avoid DOB handling; compute-based age can be added later.
    age = models.PositiveSmallIntegerField(help_text="A tag életkora években.", default=18)
    sex = models.CharField(max_length=20, choices=Sex.choices, default=Sex.UNSPECIFIED)

    height_cm = models.PositiveIntegerField(null=True, blank=True, help_text="Magasság centiméterben.")
    weight_kg = models.DecimalField(
        null=True,
        blank=True,
        max_digits=6,
        decimal_places=2,
        help_text="Testsúly kilogrammban.",
    )

    training_level = models.CharField(max_length=20, choices=TrainingLevel.choices, default=TrainingLevel.BEGINNER)
    primary_goal = models.CharField(max_length=30, choices=PrimaryGoal.choices, default=PrimaryGoal.GENERAL_FITNESS)

    preferred_session_duration = models.PositiveSmallIntegerField(
        default=60,
        help_text="Preferált edzésidő percben (tervezési jelzés).",
    )
    weekly_workout_frequency = models.CharField(
        max_length=10,
        choices=WeeklyWorkoutFrequency.choices,
        default=WeeklyWorkoutFrequency.DAYS_3_4,
        help_text="Heti edzésszám (becslés).",
    )

    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Tag profil"
        verbose_name_plural = "Tag profilok"
        constraints = [
            models.UniqueConstraint(
                fields=["phone_normalized"],
                condition=models.Q(phone_normalized__gt=""),
                name="members_memberprofile_phone_normalized_nonempty_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} (age {self.age})"

    def save(self, *args, **kwargs) -> None:
        raw = (self.phone or "").strip()
        self.phone_normalized = normalize_phone(raw) if raw else ""
        super().save(*args, **kwargs)


class MemberRestriction(models.Model):
    class RestrictionType(models.TextChoices):
        AVOID = "avoid", "Kerülendő"
        LIMIT = "limit", "Korlátozás"
        MODIFY = "modify", "Módosítás"
        NOTE = "note", "Megjegyzés"

    # Keep `body_area` practical for MVP rendering/filtering.
    class BodyArea(models.TextChoices):
        FULL_BODY = "full_body", "Teljes test"
        BACK = "back", "Hát"
        CHEST = "chest", "Mell"
        SHOULDERS = "shoulders", "Váll"
        ARMS = "arms", "Kar"
        HIPS = "hips", "Csípő"
        KNEES = "knees", "Térd"
        ANKLES = "ankles", "Boka"
        CORE = "core", "Törzs"
        OTHER = "other", "Egyéb"

    member = models.ForeignKey(
        MemberProfile,
        on_delete=models.CASCADE,
        related_name="restrictions",
    )
    restriction_type = models.CharField(max_length=20, choices=RestrictionType.choices, default=RestrictionType.AVOID)
    body_area = models.CharField(max_length=30, choices=BodyArea.choices, default=BodyArea.OTHER)

    description = models.CharField(max_length=255, blank=True, default="")
    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-active", "-created_at"]
        verbose_name = "Tag korlátozás"
        verbose_name_plural = "Tag korlátozások"

    def __str__(self) -> str:
        member_name = self.member.full_name if self.member_id else "Ismeretlen tag"
        return f"{member_name}: {self.restriction_type} ({self.body_area})"


class GymEquipment(models.Model):
    equipment = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["equipment"]
        verbose_name = "Edzőtermi eszköz"
        verbose_name_plural = "Edzőtermi eszközök"

    def __str__(self) -> str:
        return self.equipment


class UploadedWorkoutPlan(models.Model):
    title = models.CharField(max_length=200)
    source = models.CharField(max_length=200, blank=True, default="")
    file = models.FileField(upload_to="uploaded_workout_plans/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_workout_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Feltöltött edzésterv"
        verbose_name_plural = "Feltöltött edzéstervek"

    def __str__(self) -> str:
        return self.title

