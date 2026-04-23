from django.contrib import admin

from workouts.models import WorkoutExercise, WorkoutFeedback, WorkoutPlan


@admin.register(WorkoutPlan)
class WorkoutPlanAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "member",
        "created_by",
        "session_type",
        "goal",
        "available_time",
        "energy_level",
        "soreness_level",
        "ai_generated",
        "exercise_count_display",
        "created_at",
    ]
    list_filter = [
        "session_type",
        "goal",
        "energy_level",
        "soreness_level",
        "ai_generated",
        "created_at",
    ]
    # Keep search fields to text columns so it works consistently across DB backends.
    search_fields = ["member__full_name", "notes"]
    ordering = ["-created_at"]

    readonly_fields = ["created_at", "generated_plan_json", "exercise_slugs"]

    @admin.display(description="Gyakorlatok")
    def exercise_count_display(self, obj: WorkoutPlan) -> int:
        return obj.exercise_count


@admin.register(WorkoutFeedback)
class WorkoutFeedbackAdmin(admin.ModelAdmin):
    list_display = ["id", "workout_plan", "completed", "difficulty_rating", "energy_after", "pain_flag", "created_at"]
    list_filter = ["completed", "energy_after", "pain_flag", "created_at"]
    search_fields = ["workout_plan__member__full_name", "feedback_notes"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at"]


@admin.register(WorkoutExercise)
class WorkoutExerciseAdmin(admin.ModelAdmin):
    list_display = ["id", "workout_plan", "order", "block_type", "exercise", "sets", "reps", "rest_seconds"]
    list_filter = ["block_type", "exercise__equipment", "exercise__difficulty"]
    search_fields = ["exercise__name", "notes"]
    ordering = ["workout_plan_id", "order"]
    autocomplete_fields = ["exercise", "workout_plan"]

