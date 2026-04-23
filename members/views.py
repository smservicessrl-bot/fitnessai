from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from members.forms import MemberProfileForm, MemberRestrictionForm
from members.models import MemberProfile, MemberRestriction
from members.permissions import get_member_for_app, member_profile_for_user
from workouts.models import WorkoutPlan

staff_required = user_passes_test(lambda u: u.is_authenticated and u.is_staff)


@login_required
@staff_required
def member_list(request):
    members = MemberProfile.objects.all().order_by("-created_at")
    return render(request, "members/member_list.html", {"members": members})


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
    if request.method == "POST":
        form = MemberProfileForm(request.POST, instance=member)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mentve.")
            return redirect(reverse("member_app:dashboard"))
    else:
        form = MemberProfileForm(instance=member)

    return render(
        request,
        "members/member_profile_self.html",
        {"form": form, "member": member},
    )
