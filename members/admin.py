from django.contrib import admin

from .models import MemberProfile, MemberRestriction


class MemberRestrictionInline(admin.TabularInline):
    model = MemberRestriction
    extra = 1

    fields = ["restriction_type", "body_area", "description", "active", "created_at"]
    readonly_fields = ["created_at"]


@admin.register(MemberProfile)
class MemberProfileAdmin(admin.ModelAdmin):
    list_display = [
        "full_name",
        "age",
        "sex",
        "training_level",
        "primary_goal",
        "preferred_session_duration",
        "weekly_workout_frequency",
        "created_at",
        "updated_at",
    ]
    list_filter = ["sex", "training_level", "primary_goal", "weekly_workout_frequency", "created_at", "updated_at"]
    search_fields = ["full_name", "notes"]
    ordering = ["-created_at"]

    inlines = [MemberRestrictionInline]

    readonly_fields = ["created_at", "updated_at"]


@admin.register(MemberRestriction)
class MemberRestrictionAdmin(admin.ModelAdmin):
    list_display = ["member", "restriction_type", "body_area", "active", "created_at"]
    list_filter = ["restriction_type", "body_area", "active", "created_at"]
    search_fields = ["member__full_name", "description"]
    ordering = ["-active", "-created_at"]

    readonly_fields = ["created_at"]

