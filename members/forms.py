from django import forms

from members.models import MemberProfile, MemberRestriction
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
            "full_name": "Teljes név",
            "phone": "Telefon",
            "age": "Életkor (év)",
            "sex": "Nem",
            "height_cm": "Magasság (cm)",
            "weight_kg": "Testsúly (kg)",
            "training_level": "Edzettségi szint",
            "primary_goal": "Elsődleges cél",
            "preferred_session_duration": "Preferált edzés hossza (perc)",
            "weekly_workout_frequency": "Hetente hányszor edzel?",
            "notes": "Megjegyzések",
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
                self.add_error("phone", "Ez a telefonszám már egy másik profilhoz tartozik.")
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
            "restriction_type": "Korlátozás típusa",
            "body_area": "Testtáj",
            "description": "Leírás / megjegyzés",
            "active": "Aktív",
        }
        widgets = {
            "restriction_type": forms.Select(attrs={"class": "form-control"}),
            "body_area": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

