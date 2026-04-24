from django import forms

from members.models import UploadedWorkoutPlan
from workouts.models import WorkoutFeedback, WorkoutPlan


class WorkoutSessionInputForm(forms.ModelForm):
    """
    Trainer enters today's session parameters.

    Business logic (AI generation, rule constraints, etc.) must live in services/views,
    not in this form.
    """

    reference_workout_plan = forms.ModelChoiceField(
        label="Inspirációs külső terv (opcionális)",
        queryset=UploadedWorkoutPlan.objects.none(),
        required=False,
        empty_label="Nincs kiválasztva",
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="A rendszer ezt mint stílus-inspirációt használja, de a tervet a profilodhoz és mai paramétereidhez igazítja.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reference_workout_plan"].queryset = UploadedWorkoutPlan.objects.all().order_by("-created_at")

    class Meta:
        model = WorkoutPlan
        exclude = [
            "member",
            "created_by",
            "ai_generated",
            "generated_context_json",
            "generated_plan_json",
            "exercise_slugs",
            "created_at",
        ]
        fields = [
            "session_type",
            "goal",
            "available_time",
            "energy_level",
            "soreness_level",
            "notes",
        ]
        labels = {
            "session_type": "Edzés típusa",
            "goal": "Edzés célja",
            "available_time": "Rendelkezésre álló idő (perc)",
            "energy_level": "Energiaszint",
            "soreness_level": "Izomláz / fáradtság",
            "notes": "Megjegyzések az edzéshez",
        }
        widgets = {
            "session_type": forms.HiddenInput(),  # for MVP: implied; only one choice supported
            "goal": forms.Select(attrs={"class": "form-control"}),
            "available_time": forms.NumberInput(attrs={"class": "form-control", "min": 10, "max": 240, "step": 5}),
            "energy_level": forms.RadioSelect(),
            "soreness_level": forms.RadioSelect(),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class WorkoutFeedbackForm(forms.ModelForm):
    """
    Trainer records completion + feedback after the session.
    """

    class Meta:
        model = WorkoutFeedback
        exclude = ["workout_plan", "created_at"]
        fields = [
            "completed",
            "difficulty_rating",
            "energy_after",
            "pain_flag",
            "feedback_notes",
        ]
        labels = {
            "completed": "Elvégezve?",
            "difficulty_rating": "Nehézség (1–10)",
            "energy_after": "Energia edzés után",
            "pain_flag": "Fájdalom ma?",
            "feedback_notes": "Visszajelzés megjegyzések",
        }
        widgets = {
            "completed": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "difficulty_rating": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 10, "step": 1}),
            "energy_after": forms.RadioSelect(),
            "pain_flag": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "feedback_notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


class WorkoutPlanQuestionForm(forms.Form):
    question = forms.CharField(
        label="Kérdés az edzéstervről",
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "id": "workout-qa-question",
                "placeholder": "Pl.: Csinálhatom a második gyakorlatot, ha 2 hete lábsérülésem volt?",
            }
        ),
    )

