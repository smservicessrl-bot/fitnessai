from django import forms
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from exercises.models import Exercise
from members.models import GymEquipment, MemberProfile, MemberRestriction, UploadedWorkoutPlan
from members.phone import normalize_phone


class MemberProfileForm(forms.ModelForm):
    """
    Tablet-friendly form for trainer-managed member profile creation/editing.
    Keep all planning/generation logic out of the form.
    """

    class Meta:
        model = MemberProfile
        exclude = ["user", "created_at", "updated_at", "restrictions"]
        fields = [
            "full_name",
            "phone",
            "age",
            "sex",
            "height_cm",
            "weight_kg",
            "training_level",
            "primary_goal",
            "preferred_session_duration",
            "weekly_workout_frequency",
            "notes",
        ]
        labels = {
            "full_name": _("Full name"),
            "phone": _("Phone"),
            "age": _("Age (years)"),
            "sex": _("Sex"),
            "height_cm": _("Height (cm)"),
            "weight_kg": _("Weight (kg)"),
            "training_level": _("Training level"),
            "primary_goal": _("Primary goal"),
            "preferred_session_duration": _("Preferred workout duration (min)"),
            "weekly_workout_frequency": _("How often do you train per week?"),
            "notes": _("Notes"),
        }
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-control", "autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel", "inputmode": "tel"}),
            "age": forms.NumberInput(attrs={"class": "form-control", "min": 10, "max": 120, "step": 1}),
            "sex": forms.RadioSelect(),
            "height_cm": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 1}),
            "weight_kg": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 0.1}),
            "training_level": forms.RadioSelect(),
            "primary_goal": forms.RadioSelect(),
            "preferred_session_duration": forms.NumberInput(attrs={"class": "form-control", "min": 10, "max": 240, "step": 5}),
            "weekly_workout_frequency": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def clean(self):
        cleaned = super().clean()
        phone_raw = (cleaned.get("phone") or "").strip()
        phone_n = normalize_phone(phone_raw)
        if phone_n:
            qs = MemberProfile.objects.filter(phone_normalized=phone_n)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error("phone", _("This phone number already belongs to another profile."))
        return cleaned


class MemberRestrictionForm(forms.ModelForm):
    """
    Optional per-member restriction editing.
    Intended for inline formsets or separate admin-like screens.
    """

    class Meta:
        model = MemberRestriction
        exclude = ["member", "created_at"]
        fields = ["restriction_type", "body_area", "description", "active"]
        labels = {
            "restriction_type": _("Restriction type"),
            "body_area": _("Body area"),
            "description": _("Description / note"),
            "active": _("Active"),
        }
        widgets = {
            "restriction_type": forms.Select(attrs={"class": "form-control"}),
            "body_area": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class EquipmentForm(forms.ModelForm):
    class Meta:
        model = GymEquipment
        fields = ["equipment"]
        labels = {"equipment": _("New equipment name")}
        widgets = {
            "equipment": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("E.g.: TRX, battle rope, sled"),
                }
            )
        }

    def clean_equipment(self):
        value = (self.cleaned_data.get("equipment") or "").strip()
        if not value:
            raise forms.ValidationError(_("Please provide an equipment name."))
        return " ".join(value.split())


class ExerciseCreateForm(forms.ModelForm):
    class Meta:
        model = Exercise
        fields = [
            "name",
            "category",
            "primary_muscle",
            "secondary_muscles",
            "equipment",
            "difficulty",
            "contraindications",
            "instructions",
            "active",
        ]
        labels = {
            "name": _("Exercise name"),
            "category": _("Category"),
            "primary_muscle": _("Primary muscle group"),
            "secondary_muscles": _("Secondary muscle groups (comma-separated)"),
            "equipment": _("Equipment"),
            "difficulty": _("Difficulty"),
            "contraindications": _("Contraindications"),
            "instructions": _("Execution instructions"),
            "active": _("Active"),
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "primary_muscle": forms.Select(attrs={"class": "form-select"}),
            "secondary_muscles": forms.TextInput(attrs={"class": "form-control"}),
            "equipment": forms.Select(attrs={"class": "form-select"}),
            "difficulty": forms.Select(attrs={"class": "form-select"}),
            "contraindications": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "instructions": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_secondary_muscles(self):
        value = self.cleaned_data.get("secondary_muscles")
        if isinstance(value, list):
            return value
        if not value:
            return []
        allowed = {choice for choice, _label in Exercise.MuscleGroup.choices}
        parsed = [segment.strip() for segment in str(value).split(",") if segment.strip()]
        invalid = [item for item in parsed if item not in allowed]
        if invalid:
            raise forms.ValidationError(_("Invalid muscle group(s): %(items)s") % {"items": ", ".join(invalid)})
        return parsed

    def save(self, commit=True):
        exercise = super().save(commit=False)
        base_slug = slugify(exercise.name)[:120]
        if not base_slug:
            base_slug = "exercise"
        slug = base_slug
        idx = 2
        while Exercise.objects.exclude(pk=exercise.pk).filter(slug=slug).exists():
            suffix = f"-{idx}"
            slug = f"{base_slug[: max(1, 140 - len(suffix))]}{suffix}"
            idx += 1
        exercise.slug = slug
        if commit:
            exercise.save()
        return exercise


class UploadedWorkoutPlanForm(forms.ModelForm):
    class Meta:
        model = UploadedWorkoutPlan
        fields = ["title", "source", "file"]
        labels = {
            "title": _("Plan title"),
            "source": _("Source (e.g. athlete's name)"),
            "file": _("PDF file"),
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": _("E.g.: Arnold chest day")}),
            "source": forms.TextInput(attrs={"class": "form-control", "placeholder": _("E.g.: Arnold Schwarzenegger")}),
            "file": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "application/pdf"}),
        }

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if not f:
            raise forms.ValidationError(_("Please select a PDF file."))
        name = (f.name or "").lower()
        content_type = (getattr(f, "content_type", "") or "").lower()
        if not name.endswith(".pdf") and content_type != "application/pdf":
            raise forms.ValidationError(_("Only PDF files can be uploaded."))
        return f
