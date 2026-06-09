"""Passwordless email login: short-lived one-time codes.

The user enters their email, receives a code by mail, and submits it to log in —
no password. Only pre-registered emails (users created in the admin) can receive
a code. Codes are hashed at rest, expirable, attempt- and rate-limited.
"""

from __future__ import annotations

import datetime as dt

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone
from django.utils.crypto import get_random_string


def code_ttl() -> dt.timedelta:
    return dt.timedelta(minutes=getattr(settings, "LOGIN_CODE_TTL_MINUTES", 10))


def max_attempts() -> int:
    return getattr(settings, "LOGIN_CODE_MAX_ATTEMPTS", 5)


def code_length() -> int:
    return getattr(settings, "LOGIN_CODE_LENGTH", 6)


class LoginCode(models.Model):
    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"LoginCode<{self.email}> ({'used' if self.used else 'active'})"

    @classmethod
    def issue(cls, email: str) -> tuple[LoginCode, str]:
        """Create a code for `email`, returning (instance, plaintext_code)."""
        plaintext = get_random_string(code_length(), allowed_chars="0123456789")
        instance = cls.objects.create(
            email=email.lower(),
            code_hash=make_password(plaintext),
            expires_at=timezone.now() + code_ttl(),
        )
        return instance, plaintext

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_active(self) -> bool:
        return not self.used and not self.is_expired and self.attempts < max_attempts()

    def verify(self, plaintext: str) -> bool:
        """Check a submitted code, recording the attempt. Single-use on success."""
        if not self.is_active:
            return False
        self.attempts += 1
        if check_password(plaintext, self.code_hash):
            self.used = True
            self.save(update_fields=["attempts", "used"])
            return True
        self.save(update_fields=["attempts"])
        return False
