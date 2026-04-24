from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import OuterRef, Subquery
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
def member_list(request):
    if request.method == "POST":
        upload_form = UploadedWorkoutPlanForm(request.POST, request.FILES)
        if upload_form.is_valid():
            item = upload_form.save(commit=False)
            item.uploaded_by = request.user
            item.save()
            messages.success(request, "PDF edzésterv feltöltve.")
            return redirect(reverse("members:member_list"))
    else:
        upload_form = UploadedWorkoutPlanForm()

    latest_plan_id = Subquery(
        WorkoutPlan.objects.filter(member_id=OuterRef("pk")).order_by("-created_at").values("id")[:1]
    )
    members = MemberProfile.objects.all().annotate(latest_plan_id=latest_plan_id).order_by("-created_at")
    uploaded_plans = UploadedWorkoutPlan.objects.select_related("uploaded_by").all()
    return render(
        request,
        "members/member_list.html",
        {
            "members": members,
            "uploaded_plans": uploaded_plans,
            "upload_form": upload_form,
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
        {"form": form, "restrictions_formset": restrictions_formset, "member": None},
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
            return redirect(reverse("members:member_list"))
    else:
        form = MemberProfileForm(instance=member)
        restrictions_formset = _get_restrictions_formset(data=None, instance=member)

    return render(
        request,
        "members/member_form.html",
        {"form": form, "restrictions_formset": restrictions_formset, "member": member},
    )


@login_required
def member_dashboard(request):
    if request.user.is_staff:
        return redirect(reverse("members:member_list"))
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
            "form": form,
            "recent_exercises": recent_exercises,
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
    return redirect(reverse("members:member_list"))
