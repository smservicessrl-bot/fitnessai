from django.contrib import admin

from .models import Exercise, ExerciseSubstitution


class ExerciseSubstitutionInline(admin.TabularInline):
    model = ExerciseSubstitution
    fk_name = "from_exercise"
    extra = 1
    fields = ["to_exercise", "reason", "priority", "active"]

    # Keep the inline focused; created_at is useful but not needed for editing.
    readonly_fields = ["created_at"]


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "category", "primary_muscle", "equipment", "difficulty", "active"]
    list_filter = ["category", "primary_muscle", "equipment", "difficulty", "active"]
    search_fields = ["name", "slug", "contraindications", "instructions"]
    ordering = ["name"]

    autocomplete_fields = []

    inlines = [ExerciseSubstitutionInline]

    readonly_fields = ["created_at", "updated_at"]


@admin.register(ExerciseSubstitution)
class ExerciseSubstitutionAdmin(admin.ModelAdmin):
    list_display = ["from_exercise", "to_exercise", "priority", "active", "created_at"]
    list_filter = ["active", "priority"]
    search_fields = ["from_exercise__name", "to_exercise__name", "reason"]
    ordering = ["-priority", "from_exercise__name", "to_exercise__name"]
    readonly_fields = ["created_at"]

