import os
import csv
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from ai_engine.services import answer_workout_plan_question, refine_workout_or_fallback_to_deterministic
from exercises.models import Exercise
from members.models import MemberProfile, MemberRestriction
from members.permissions import assert_member_access, get_member_for_app

_EQUIPMENT_LABEL = dict(Exercise.Equipment.choices)
_DIFFICULTY_LABEL = dict(Exercise.Difficulty.choices)
_BLOCK_TYPE_LABEL = {
    "warmup": "Bemelegítés",
    "main_work": "Fő munka",
    "main": "Fő",
    "accessory": "Kiegészítő",
    "cooldown": "Levezetés",
}
from workouts import services as planner_services
from workouts.forms import WorkoutPlanQuestionForm, WorkoutSessionInputForm
from workouts.models import WorkoutExercise, WorkoutPlan, WorkoutPlanQuestion
from workouts.plan_display import (
    extract_exercise_slugs_from_proposal,
    get_plan_exercise_blocks,
    iter_plan_rows_ordered,
)


@login_required
def workout_session_input(request, member_id: int):
    """
    Generate a workout plan using:
    1) deterministic planner
    2) optional LLM refinement (Ollama/OpenAI via ai_engine.services)
    3) persistence to WorkoutPlan (generated_plan_json + exercise_slugs; no per-exercise rows)
    """
    assert_member_access(request, member_id)
    member = get_object_or_404(MemberProfile, pk=member_id)

    if request.method == "POST":
        form = WorkoutSessionInputForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                plan: WorkoutPlan = form.save(commit=False)
                plan.member = member
                plan.created_by = request.user
                # Session params for deterministic engine.
                planner_input = planner_services.SessionParams(
                    goal=plan.goal,
                    energy_level=plan.energy_level,
                    soreness_level=plan.soreness_level,
                    available_time=plan.available_time,
                )

                active_restrictions = MemberRestriction.objects.filter(member=member, active=True)
                available_exercises_qs = Exercise.objects.filter(active=True).order_by("slug")
                available_exercises = list(available_exercises_qs)

                # Very light recent-history signal for repetition control.
                recent_plans = list(WorkoutPlan.objects.filter(member=member).order_by("-created_at")[:5])
                recent_slugs: set[str] = set()
                for p in recent_plans:
                    if p.exercise_slugs:
                        recent_slugs.update(p.exercise_slugs)
                    elif p.generated_plan_json:
                        recent_slugs.update(extract_exercise_slugs_from_proposal(p.generated_plan_json))
                    else:
                        recent_slugs.update(
                            WorkoutExercise.objects.filter(workout_plan=p).values_list(
                                "exercise__slug", flat=True
                            )
                        )

                deterministic = planner_services.generate_deterministic_one_day_workout(
                    member=member,
                    active_restrictions=active_restrictions,
                    session_params=planner_input,
                    available_exercises=available_exercises,
                    recent_exercises_slugs=recent_slugs,
                    equipment_available=None,  # MVP: no per-session equipment input yet
                )

                # Only exercises in this plan: smaller prompts and faster context building than full library.
                plan_slugs = set(extract_exercise_slugs_from_proposal(deterministic))
                exercise_by_slug = {ex.slug: ex for ex in available_exercises}
                available_exercises_context = [
                    {
                        "slug": ex.slug,
                        "name": ex.name,
                        "equipment": ex.equipment,
                        "difficulty": ex.difficulty,
                        "category": ex.category,
                        "instructions": ex.instructions,
                    }
                    for slug in plan_slugs
                    if (ex := exercise_by_slug.get(slug)) is not None
                ]

                refined_or_fallback, ai_used, ai_reason = refine_workout_or_fallback_to_deterministic(
                    member=member,
                    active_restrictions=active_restrictions,
                    session_params=plan,
                    recent_workout_history=recent_plans,
                    available_exercises_context=available_exercises_context,
                    deterministic_proposal=deterministic,
                )

                plan.ai_generated = ai_used
                plan.generated_context_json = {
                    "deterministic_title": deterministic.get("title"),
                    "deterministic_duration": deterministic.get("estimated_duration_minutes"),
                    "ai_used": ai_used,
                    "ai_error": ai_reason if not ai_used else "",
                    "llm_provider": os.environ.get("LLM_PROVIDER", "openai"),
                }
                plan.generated_plan_json = refined_or_fallback
                plan.exercise_slugs = extract_exercise_slugs_from_proposal(refined_or_fallback)
                plan.save()

            hist = (
                reverse("app_workouts:workout_history")
                if getattr(request.resolver_match, "namespace", None) == "app_workouts"
                else reverse("workouts:workout_history", kwargs={"member_id": member.id})
            )
            return redirect(f"{hist}?plan_id={plan.id}")
    else:
        form = WorkoutSessionInputForm(
            initial={
                "session_type": WorkoutPlan.SessionType.ONE_DAY_GYM,
                "goal": member.primary_goal,
                "available_time": member.preferred_session_duration,
                "energy_level": WorkoutPlan.EnergyLevel.MEDIUM,
                "soreness_level": WorkoutPlan.SorenessLevel.NONE,
            }
        )

    return render(
        request,
        "workouts/workout_session_input.html",
        {"member": member, "form": form},
    )


@login_required
def workout_history(request, member_id: int):
    assert_member_access(request, member_id)
    member = get_object_or_404(MemberProfile, pk=member_id)
    plans = WorkoutPlan.objects.filter(member=member).order_by("-created_at")

    highlight_plan_id = request.GET.get("plan_id")

    # Precompute absolute PDF URLs so the template can render working QR codes
    # without relying on request context in nested templates.
    pdf_view = (
        "app_workouts:workout_plan_download_pdf"
        if getattr(request.resolver_match, "namespace", None) == "app_workouts"
        else "workouts:workout_plan_download_pdf"
    )
    for plan in plans:
        if pdf_view == "app_workouts:workout_plan_download_pdf":
            plan.plan_pdf_url = request.build_absolute_uri(
                reverse("app_workouts:workout_plan_download_pdf", kwargs={"plan_id": plan.id})
            )
        else:
            plan.plan_pdf_url = request.build_absolute_uri(
                reverse(
                    "workouts:workout_plan_download_pdf",
                    kwargs={"member_id": member.id, "plan_id": plan.id},
                )
            )

    return render(
        request,
        "workouts/workout_history.html",
        {
            "member": member,
            "plans": plans,
            "highlight_plan_id": highlight_plan_id,
        },
    )


@login_required
def workout_plan_detail(request, member_id: int, plan_id: int):
    assert_member_access(request, member_id)
    plan = get_object_or_404(
        WorkoutPlan.objects.select_related("member", "created_by"),
        pk=plan_id,
        member_id=member_id,
    )

    warmup, main_work, cooldown = get_plan_exercise_blocks(plan)
    question_form = WorkoutPlanQuestionForm()
    qa_history = WorkoutPlanQuestion.objects.filter(workout_plan=plan).order_by("-created_at")[:20]

    if getattr(request.resolver_match, "namespace", None) == "app_workouts":
        plan_pdf_url = request.build_absolute_uri(
            reverse("app_workouts:workout_plan_download_pdf", kwargs={"plan_id": plan_id})
        )
    else:
        plan_pdf_url = request.build_absolute_uri(
            reverse("workouts:workout_plan_download_pdf", kwargs={"member_id": member_id, "plan_id": plan_id})
        )

    return render(
        request,
        "workouts/workout_detail.html",
        {
            "plan": plan,
            "warmup": warmup,
            "main_work": main_work,
            "cooldown": cooldown,
            "member": plan.member,
            "plan_pdf_url": plan_pdf_url,
            "question_form": question_form,
            "qa_history": qa_history,
        },
    )


@login_required
def workout_plan_ask(request, member_id: int, plan_id: int):
    assert_member_access(request, member_id)
    plan = get_object_or_404(
        WorkoutPlan.objects.select_related("member"),
        pk=plan_id,
        member_id=member_id,
    )
    if request.method != "POST":
        return redirect(
            reverse(
                "app_workouts:workout_plan_detail" if getattr(request.resolver_match, "namespace", None) == "app_workouts" else "workouts:workout_plan_detail",
                kwargs={"plan_id": plan_id} if getattr(request.resolver_match, "namespace", None) == "app_workouts" else {"member_id": member_id, "plan_id": plan_id},
            )
        )

    form = WorkoutPlanQuestionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Kérlek, írj be egy érvényes kérdést.")
        target = (
            reverse("app_workouts:workout_plan_detail", kwargs={"plan_id": plan_id})
            if getattr(request.resolver_match, "namespace", None) == "app_workouts"
            else reverse("workouts:workout_plan_detail", kwargs={"member_id": member_id, "plan_id": plan_id})
        )
        return redirect(target)

    question_text = form.cleaned_data["question"].strip()
    member = plan.member
    restrictions = list(MemberRestriction.objects.filter(member=member, active=True))
    member_context = {
        "full_name": member.full_name,
        "age": member.age,
        "sex": member.sex,
        "training_level": member.training_level,
        "primary_goal": member.primary_goal,
        "notes": member.notes,
    }
    restrictions_context = [
        {"type": r.restriction_type, "body_area": r.body_area, "description": r.description}
        for r in restrictions
    ]
    answer_text, source = answer_workout_plan_question(
        question=question_text,
        plan_json=plan.generated_plan_json or {},
        member_context=member_context,
        restrictions_context=restrictions_context,
    )
    WorkoutPlanQuestion.objects.create(
        workout_plan=plan,
        asked_by=request.user,
        question_text=question_text,
        answer_text=answer_text,
        answer_source=source,
    )
    messages.success(request, "Válasz elkészült.")
    target = (
        reverse("app_workouts:workout_plan_detail", kwargs={"plan_id": plan_id})
        if getattr(request.resolver_match, "namespace", None) == "app_workouts"
        else reverse("workouts:workout_plan_detail", kwargs={"member_id": member_id, "plan_id": plan_id})
    )
    return redirect(f"{target}#plan-qa")


@login_required
def workout_plan_print(request, member_id: int, plan_id: int):
    """
    Printer-friendly page for in-gym execution sheets.
    Keeps layout high-contrast and minimal for A4/Letter printouts.
    """
    assert_member_access(request, member_id)
    plan = get_object_or_404(
        WorkoutPlan.objects.select_related("member"),
        pk=plan_id,
        member_id=member_id,
    )
    warmup, main_work, cooldown = get_plan_exercise_blocks(plan)

    return render(
        request,
        "workouts/workout_print.html",
        {
            "plan": plan,
            "member": plan.member,
            "warmup": warmup,
            "main_work": main_work,
            "cooldown": cooldown,
            "auto_print": False,
        },
    )


@login_required
def workout_plan_download_pdf(request, member_id: int, plan_id: int):
    """
    "Download PDF" UX:
    We reuse the print-friendly template and auto-open the browser print dialog.
    On phones/desktops, the user can choose "Save as PDF".
    """
    assert_member_access(request, member_id)
    plan = get_object_or_404(
        WorkoutPlan.objects.select_related("member"),
        pk=plan_id,
        member_id=member_id,
    )
    warmup, main_work, cooldown = get_plan_exercise_blocks(plan)

    return render(
        request,
        "workouts/workout_print.html",
        {
            "plan": plan,
            "member": plan.member,
            "warmup": warmup,
            "main_work": main_work,
            "cooldown": cooldown,
            "auto_print": True,
        },
    )


@login_required
def workout_plan_qr_png(request, member_id: int, plan_id: int):
    """
    Server-rendered QR code image pointing to the PDF/print endpoint for this plan.

    This avoids flaky client-side QR rendering on tablet devices.
    """
    assert_member_access(request, member_id)
    plan = get_object_or_404(WorkoutPlan.objects.select_related("member"), pk=plan_id, member_id=member_id)

    if getattr(request.resolver_match, "namespace", None) == "app_workouts":
        plan_pdf_url = request.build_absolute_uri(
            reverse("app_workouts:workout_plan_download_pdf", kwargs={"plan_id": plan_id})
        )
    else:
        plan_pdf_url = request.build_absolute_uri(
            reverse("workouts:workout_plan_download_pdf", kwargs={"member_id": member_id, "plan_id": plan_id})
        )

    # Import inside function so the module is only required at runtime when used.
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(plan_pdf_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)

    response = HttpResponse(buffer.getvalue(), content_type="image/png")
    response["Cache-Control"] = "no-store"
    return response


@login_required
def workout_plan_download_csv(request, member_id: int, plan_id: int):
    assert_member_access(request, member_id)
    plan = get_object_or_404(WorkoutPlan.objects.select_related("member"), pk=plan_id, member_id=member_id)

    response = HttpResponse(content_type="text/csv")
    safe_member_name = (plan.member.full_name or "tag").replace(" ", "_")
    response["Content-Disposition"] = f'attachment; filename="edzesterv_{plan.id}_{safe_member_name}.csv"'

    writer = csv.writer(response)
    writer.writerow(["Edzésterv export"])
    writer.writerow(["Terv azonosító", plan.id])
    writer.writerow(["Tag", plan.member.full_name])
    writer.writerow(["Létrehozva", plan.created_at.isoformat()])
    writer.writerow(["Cél", plan.get_goal_display()])
    writer.writerow(["Rendelkezésre álló idő (perc)", plan.available_time])
    writer.writerow(["Energiaszint", plan.get_energy_level_display()])
    writer.writerow(["Izomláz / fáradtság", plan.get_soreness_level_display()])
    writer.writerow(["MI által generált", "igen" if plan.ai_generated else "nem"])
    writer.writerow([])

    writer.writerow(
        [
            "Sorrend",
            "Blokk típus",
            "Gyakorlat",
            "Eszköz",
            "Nehézség",
            "Sorozatok",
            "Ismétlések",
            "Pihenő (mp)",
            "Tempó",
            "Megjegyzés",
        ]
    )
    for item in iter_plan_rows_ordered(plan):
        eq = getattr(item.exercise, "equipment", "") or ""
        diff = getattr(item.exercise, "difficulty", "") or ""
        bt = item.block_type or ""
        writer.writerow(
            [
                item.order,
                _BLOCK_TYPE_LABEL.get(bt, bt),
                item.exercise.name,
                _EQUIPMENT_LABEL.get(eq, eq),
                _DIFFICULTY_LABEL.get(diff, diff),
                item.sets,
                item.reps,
                item.rest_seconds,
                item.tempo,
                item.notes,
            ]
        )

    return response


# --- Member self-service (/app/workouts/...): same views, member_id from session user ---


@login_required
def app_workout_session_input(request):
    m = get_member_for_app(request)
    return workout_session_input(request, m.pk)


@login_required
def app_workout_history(request):
    m = get_member_for_app(request)
    return workout_history(request, m.pk)


@login_required
def app_workout_plan_detail(request, plan_id: int):
    m = get_member_for_app(request)
    return workout_plan_detail(request, m.pk, plan_id)


@login_required
def app_workout_plan_ask(request, plan_id: int):
    m = get_member_for_app(request)
    return workout_plan_ask(request, m.pk, plan_id)


@login_required
def app_workout_plan_print(request, plan_id: int):
    m = get_member_for_app(request)
    return workout_plan_print(request, m.pk, plan_id)


@login_required
def app_workout_plan_download_pdf(request, plan_id: int):
    m = get_member_for_app(request)
    return workout_plan_download_pdf(request, m.pk, plan_id)


@login_required
def app_workout_plan_qr_png(request, plan_id: int):
    m = get_member_for_app(request)
    return workout_plan_qr_png(request, m.pk, plan_id)


@login_required
def app_workout_plan_download_csv(request, plan_id: int):
    m = get_member_for_app(request)
    return workout_plan_download_csv(request, m.pk, plan_id)
