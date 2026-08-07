"""Typing helpers for the request/response layer.

`HttpRequest.user` is typed by django-stubs as `AbstractBaseUser |
AnonymousUser` since Django can't statically know a view is
authentication-gated. `AuthenticatedHttpRequest` narrows that for views
behind `@login_required` / DRF's `IsAuthenticated` — annotate the view's
`request` parameter with it instead of casting at every call site.
"""

from django.http import HttpRequest

from apps.accounts.models import User


class AuthenticatedHttpRequest(HttpRequest):
    user: User  # narrows AbstractBaseUser | AnonymousUser for @login_required views
