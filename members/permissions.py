from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from members.models import MemberProfile


def member_profile_for_user(user) -> MemberProfile | None:
    if not user.is_authenticated:
        return None
    return MemberProfile.objects.filter(user=user).first()


def assert_member_access(request: HttpRequest, member_id: int) -> None:
    """
    Staff may access any member. Non-staff users may only access their linked MemberProfile.
    """
    if request.user.is_staff:
        return
    mp = member_profile_for_user(request.user)
    if mp is None or mp.pk != member_id:
        raise PermissionDenied


def get_member_for_app(request: HttpRequest) -> MemberProfile:
    """Require an authenticated user with a linked MemberProfile (member self-service)."""
    if not request.user.is_authenticated:
        raise PermissionDenied
    mp = member_profile_for_user(request.user)
    if mp is None:
        raise PermissionDenied
    return mp
