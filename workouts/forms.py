from django import forms
from django.utils.translation import gettext_lazy as _

from members.models import MemberRestriction, UploadedWorkoutPlan
from workouts.models import WorkoutFeedback, WorkoutPlan

SESSION_DURATION_CHOICES = [
    (30, _("30 min")),
    (45, _("45 min")),
    (60, _("60 min")),
    (75, _("75 min")),
    (90, _("90 min")),
]

SESSION_INJURY_AREA_CHOICES = [
    (value, label)
    for value, label in MemberRestriction.BodyArea.choices
    if value not in {MemberRestriction.BodyArea.FULL_BODY}
]


class WorkoutSessionInputForm(forms.ModelForm):
    """
    Trainer enters today's session parameters.

    Business logic (AI generation, rule constraints, etc.) must live in services/views,
    not in this form.
    """

    available_time = forms.TypedChoiceField(
        label=_("Workout duration"),
        coerce=int,
        choices=SESSION_DURATION_CHOICES,
        widget=forms.RadioSelect(),
    )
    session_injuries = forms.MultipleChoiceField(
        label=_("Today's injuries / painful areas"),
        required=False,
        choices=SESSION_INJURY_AREA_CHOICES,
        widget=forms.CheckboxSelectMultiple(),
        help_text=_("Applies to today's session only. Restrictions saved on your profile are pre-selected by default."),
    )

    reference_workout_plan = forms.ModelChoiceField(
        label=_("External plan inspiration (optional)"),
        queryset=UploadedWorkoutPlan.objects.none(),
        required=False,
        empty_label=_("None selected"),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text=_("The system uses this as style inspiration but tailors the plan to your profile and today's parameters."),
    )

    def __init__(self, *args, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reference_workout_plan"].queryset = UploadedWorkoutPlan.objects.all().order_by("-created_at")
        if member is not None and not self.data:
            profile_areas = list(
                MemberRestriction.objects.filter(member=member, active=True)
                .values_list("body_area", flat=True)
                .distinct()
            )
            self.fields["session_injuries"].initial = [
                area for area in profile_areas if area in dict(SESSION_INJURY_AREA_CHOICES)
            ]

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
            "session_type": _("Workout type"),
            "goal": _("Workout goal"),
            "energy_level": _("Intensity"),
            "soreness_level": _("Soreness / fatigue"),
            "notes": _("Workout notes"),
        }
        widgets = {
            "session_type": forms.HiddenInput(),  # for MVP: implied; only one choice supported
            "goal": forms.RadioSelect(),
            "energy_level": forms.RadioSelect(),
            "soreness_level": forms.HiddenInput(),
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
            "completed": _("Completed?"),
            "difficulty_rating": _("Difficulty (1–10)"),
            "energy_after": _("Energy after the workout"),
            "pain_flag": _("Any pain today?"),
            "feedback_notes": _("Feedback notes"),
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
        label=_("Question about the workout plan"),
        max_length=1000,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "id": "workout-qa-question",
                "placeholder": _("E.g.: Can I do the second exercise if I had a leg injury 2 weeks ago?"),
            }
        ),
    )
