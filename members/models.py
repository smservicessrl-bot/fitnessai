from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _, pgettext_lazy

from members.phone import normalize_phone


class MemberProfile(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "female", _("Female")
        MALE = "male", _("Male")
        UNSPECIFIED = "unspecified", _("Not specified")

    class TrainingLevel(models.TextChoices):
        BEGINNER = "beginner", _("Beginner")
        INTERMEDIATE = "intermediate", _("Intermediate")
        ADVANCED = "advanced", _("Advanced")

    class PrimaryGoal(models.TextChoices):
        STRENGTH = "strength", _("Strength")
        HYPERTROPHY = "hypertrophy", _("Hypertrophy")
        FAT_LOSS = "fat_loss", _("Fat loss")
        GENERAL_FITNESS = "general_fitness", _("General fitness")
        REHAB_PREVENTION = "rehab_prevention", _("Rehab / prevention")

    class WeeklyWorkoutFrequency(models.TextChoices):
        DAYS_1_2 = "1_2", _("1–2 days")
        DAYS_3_4 = "3_4", _("3–4 days")
        DAYS_5_7 = "5_7", _("5–7 days")

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="member_profile",
        null=True,
        blank=True,
        help_text=_("Optional link to the member's Django user."),
    )

    full_name = models.CharField(max_length=150)
    phone = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=_("Displayed phone number (member's own account or provided by the coach)."),
    )
    phone_normalized = models.CharField(
        max_length=32,
        blank=True,
        default="",
        db_index=True,
        help_text=_("Digits only (for consistent search); empty when no phone is set."),
    )
    # MVP keeps `age` as an input to avoid DOB handling; compute-based age can be added later.
    age = models.PositiveSmallIntegerField(help_text=_("Member age in years."), default=18)
    sex = models.CharField(max_length=20, choices=Sex.choices, default=Sex.UNSPECIFIED)

    height_cm = models.PositiveIntegerField(null=True, blank=True, help_text=_("Height in centimeters."))
    weight_kg = models.DecimalField(
        null=True,
        blank=True,
        max_digits=6,
        decimal_places=2,
        help_text=_("Body weight in kilograms."),
    )

    training_level = models.CharField(max_length=20, choices=TrainingLevel.choices, default=TrainingLevel.BEGINNER)
    primary_goal = models.CharField(max_length=30, choices=PrimaryGoal.choices, default=PrimaryGoal.GENERAL_FITNESS)

    preferred_session_duration = models.PositiveSmallIntegerField(
        default=60,
        help_text=_("Preferred workout duration in minutes (planning signal)."),
    )
    weekly_workout_frequency = models.CharField(
        max_length=10,
        choices=WeeklyWorkoutFrequency.choices,
        default=WeeklyWorkoutFrequency.DAYS_3_4,
        help_text=_("Weekly workout frequency (estimate)."),
    )

    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Member profile")
        verbose_name_plural = _("Member profiles")
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
        AVOID = "avoid", _("Avoid")
        LIMIT = "limit", _("Limit")
        MODIFY = "modify", _("Modify")
        NOTE = "note", _("Note")

    # Keep `body_area` practical for MVP rendering/filtering.
    class BodyArea(models.TextChoices):
        FULL_BODY = "full_body", _("Full body")
        BACK = "back", pgettext_lazy("body area", "Back")
        CHEST = "chest", _("Chest")
        SHOULDERS = "shoulders", _("Shoulders")
        ARMS = "arms", _("Arms")
        HIPS = "hips", _("Hips")
        KNEES = "knees", _("Knees")
        ANKLES = "ankles", _("Ankles")
        CORE = "core", _("Core")
        OTHER = "other", _("Other")

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
        verbose_name = _("Member restriction")
        verbose_name_plural = _("Member restrictions")

    def __str__(self) -> str:
        member_name = self.member.full_name if self.member_id else "Unknown member"
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
        verbose_name = _("Gym equipment")
        verbose_name_plural = _("Gym equipment")

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
        verbose_name = _("Uploaded workout plan")
        verbose_name_plural = _("Uploaded workout plans")

    def __str__(self) -> str:
        return self.title
