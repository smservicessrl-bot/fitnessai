from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from exercises.models import Exercise
from members.forms import EquipmentForm, ExerciseCreateForm, MemberProfileForm, MemberRestrictionForm, UploadedWorkoutPlanForm
from members.models import GymEquipment, MemberProfile, MemberRestriction, UploadedWorkoutPlan
from members.permissions import get_member_for_app, member_profile_for_user
from workouts.models import WorkoutPlan

ONBOARDING_SESSION_KEY = "require_profile_setup"

staff_required = user_passes_test(lambda u: u.is_authenticated and u.is_staff)


@login_required
@staff_required
def admin_dashboard(request):
    now = timezone.now()
    cutoff_7d = now - timezone.timedelta(days=7)
    cutoff_30d = now - timezone.timedelta(days=30)
    total_members = MemberProfile.objects.count()
    total_plans = WorkoutPlan.objects.count()
    total_exercises = Exercise.objects.filter(active=True).count()
    total_equipments = GymEquipment.objects.count()
    total_uploaded_templates = UploadedWorkoutPlan.objects.count()
    members_last_30d = MemberProfile.objects.filter(created_at__gte=cutoff_30d).count()
    plans_last_7d = WorkoutPlan.objects.filter(created_at__gte=cutoff_7d).count()
    recent_members = MemberProfile.objects.order_by("-created_at")[:5]
    recent_plans = WorkoutPlan.objects.select_related("member").order_by("-created_at")[:5]
    return render(
        request,
        "members/admin_dashboard.html",
        {
            "active_nav": "dashboard",
            "total_members": total_members,
            "total_plans": total_plans,
            "total_exercises": total_exercises,
            "total_equipments": total_equipments,
            "total_uploaded_templates": total_uploaded_templates,
            "members_last_30d": members_last_30d,
            "plans_last_7d": plans_last_7d,
            "recent_members": recent_members,
            "recent_plans": recent_plans,
        },
    )


@login_required
@staff_required
def member_list(request):
    latest_plan_id = Subquery(
        WorkoutPlan.objects.filter(member_id=OuterRef("pk")).order_by("-created_at").values("id")[:1]
    )
    members = MemberProfile.objects.all().annotate(latest_plan_id=latest_plan_id).order_by("-created_at")
    return render(
        request,
        "members/member_list.html",
        {
            "active_nav": "members",
            "members": members,
        },
    )


def _get_restrictions_formset(*, data=None, instance=None, prefix="restrictions"):
    return inlineformset_factory(
        MemberProfile,
        MemberRestriction,
        form=MemberRestrictionForm,
        fields=["restriction_type", "body_area", "description", "active"],
        extra=1,
        can_delete=True,
    )(
        data=data,
        instance=instance,
        prefix=prefix,
    )


@login_required
@staff_required
def member_create(request):
    if request.method == "POST":
        form = MemberProfileForm(request.POST)
        restrictions_formset = _get_restrictions_formset(data=request.POST, instance=MemberProfile())

        if form.is_valid() and restrictions_formset.is_valid():
            with transaction.atomic():
                member = form.save()
                restrictions_formset.instance = member
                restrictions_formset.save()
            return redirect(reverse("members:member_edit", kwargs={"pk": member.pk}))
    else:
        form = MemberProfileForm()
        restrictions_formset = _get_restrictions_formset(data=None, instance=MemberProfile())

    return render(
        request,
        "members/member_form.html",
        {"active_nav": "members", "form": form, "restrictions_formset": restrictions_formset, "member": None},
    )


@login_required
@staff_required
def member_edit(request, pk: int):
    member = get_object_or_404(MemberProfile, pk=pk)

    if request.method == "POST":
        form = MemberProfileForm(request.POST, instance=member)
        restrictions_formset = _get_restrictions_formset(data=request.POST, instance=member)

        if form.is_valid() and restrictions_formset.is_valid():
            with transaction.atomic():
                form.save()
                restrictions_formset.save()
            return redirect(reverse("members:members_list"))
    else:
        form = MemberProfileForm(instance=member)
        restrictions_formset = _get_restrictions_formset(data=None, instance=member)

    return render(
        request,
        "members/member_form.html",
        {"active_nav": "members", "form": form, "restrictions_formset": restrictions_formset, "member": member},
    )


@login_required
def member_dashboard(request):
    if request.user.is_staff:
        return redirect(reverse("members:dashboard"))
    member = member_profile_for_user(request.user)
    if member is None:
        messages.info(request, "Nincs tagprofil ehhez a fiókhoz.")
        return redirect(reverse("home"))
    plans = WorkoutPlan.objects.filter(member=member).order_by("-created_at")[:100]
    em = (request.user.email or "").strip()
    show_account_email = bool(em and not em.endswith("@member.local"))
    return render(
        request,
        "members/member_dashboard.html",
        {
            "member": member,
            "plans": plans,
            "show_account_email": show_account_email,
        },
    )


@login_required
def member_profile_edit(request):
    member = get_member_for_app(request)
    onboarding_required = bool(request.session.get(ONBOARDING_SESSION_KEY))
    if request.method == "POST":
        form = MemberProfileForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            if onboarding_required:
                request.session.pop(ONBOARDING_SESSION_KEY, None)
            messages.success(request, "Profil mentve.")
            if onboarding_required:
                return redirect(reverse("app_workouts:workout_session_input"))
            return redirect(reverse("member_app:dashboard"))
    else:
        form = MemberProfileForm(instance=member)

    return render(
        request,
        "members/member_profile_self.html",
        {"form": form, "member": member},
    )


@login_required
@staff_required
def equipment_list(request):
    if request.method == "POST":
        form = EquipmentForm(request.POST)
        if form.is_valid():
            equipment_name = form.cleaned_data["equipment"]
            existing = GymEquipment.objects.filter(equipment__iexact=equipment_name).first()
            if existing is None:
                GymEquipment.objects.create(equipment=equipment_name)
                created = True
            else:
                created = False
            if created:
                messages.success(request, "Eszköz hozzáadva az elérhető listához.")
            else:
                messages.info(request, "Ez az eszköz már szerepel a listában.")
            return redirect(reverse("members:equipment_list"))
    else:
        form = EquipmentForm()

    equipments = GymEquipment.objects.all().order_by("equipment")
    return render(
        request,
        "members/equipment_list.html",
        {
            "active_nav": "equipment",
            "form": form,
            "equipments": equipments,
        },
    )


@login_required
@staff_required
def equipment_delete(request, pk: int):
    equipment = get_object_or_404(GymEquipment, pk=pk)
    if request.method == "POST":
        equipment.delete()
        messages.success(request, "Eszköz törölve.")
    return redirect(reverse("members:equipment_list"))


@login_required
@staff_required
def exercise_create(request):
    if request.method == "POST":
        form = ExerciseCreateForm(request.POST)
        if form.is_valid():
            exercise = form.save()
            messages.success(request, f"'{exercise.name}' gyakorlat létrehozva.")
            return redirect(reverse("members:exercise_create"))
    else:
        form = ExerciseCreateForm()

    recent_exercises = Exercise.objects.order_by("-created_at")[:20]
    return render(
        request,
        "members/exercise_form.html",
        {
            "active_nav": "exercises",
            "form": form,
            "recent_exercises": recent_exercises,
        },
    )


@login_required
@staff_required
def uploaded_workout_plan_list(request):
    if request.method == "POST":
        upload_form = UploadedWorkoutPlanForm(request.POST, request.FILES)
        if upload_form.is_valid():
            item = upload_form.save(commit=False)
            item.uploaded_by = request.user
            item.save()
            messages.success(request, "PDF edzésterv feltöltve.")
            return redirect(reverse("members:uploaded_workout_plan_list"))
    else:
        upload_form = UploadedWorkoutPlanForm()

    uploaded_plans = UploadedWorkoutPlan.objects.select_related("uploaded_by").all()
    return render(
        request,
        "members/uploaded_workout_plan_list.html",
        {
            "active_nav": "uploaded_plans",
            "upload_form": upload_form,
            "uploaded_plans": uploaded_plans,
        },
    )


@login_required
@staff_required
def uploaded_workout_plan_delete(request, pk: int):
    item = get_object_or_404(UploadedWorkoutPlan, pk=pk)
    if request.method == "POST":
        if item.file:
            item.file.delete(save=False)
        item.delete()
        messages.success(request, "Feltöltött PDF törölve.")
    return redirect(reverse("members:uploaded_workout_plan_list"))
