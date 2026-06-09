"""Passwordless login logic: issue a code (email known users only) and verify it."""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from .models import LoginCode

User = get_user_model()

BACKEND = "django.contrib.auth.backends.ModelBackend"


def _throttle_seconds() -> int:
    return getattr(settings, "LOGIN_CODE_THROTTLE_SECONDS", 60)


def request_code(email: str) -> bool:
    """Issue and email a code if `email` belongs to an active account.

    Returns whether a code was actually sent. Callers should respond generically
    (no account enumeration) regardless of the result.
    """
    email = email.strip().lower()
    if not User.objects.filter(email__iexact=email, is_active=True).exists():
        return False

    throttle_since = timezone.now() - dt.timedelta(seconds=_throttle_seconds())
    if LoginCode.objects.filter(email=email, created_at__gte=throttle_since).exists():
        return False  # a fresh code was just sent

    _, plaintext = LoginCode.issue(email)
    _send_code_email(email, plaintext)
    return True


def verify_code(email: str, code: str):
    """Return the matching active user if the code is valid, else None."""
    email = email.strip().lower()
    login_code = (
        LoginCode.objects.filter(email=email, used=False).order_by("-created_at").first()
    )
    if login_code is None or not login_code.verify(code.strip()):
        return None
    return User.objects.filter(email__iexact=email, is_active=True).first()


def _send_code_email(email: str, code: str) -> None:
    ttl = getattr(settings, "LOGIN_CODE_TTL_MINUTES", 10)
    send_mail(
        subject="Votre code de connexion",
        message=(
            f"Votre code de connexion est : {code}\n"
            f"Il expire dans {ttl} minutes. Si vous n'êtes pas à l'origine de cette "
            f"demande, ignorez ce message."
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
