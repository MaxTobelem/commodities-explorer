import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import LoginCode

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user("max", "max@example.com", "unused")


def test_request_code_emails_known_user(client, user, mailoutbox):
    r = client.post("/api/auth/request-code/", {"email": "max@example.com"})
    assert r.status_code == 200
    assert LoginCode.objects.filter(email="max@example.com").count() == 1
    assert len(mailoutbox) == 1
    assert "code de connexion" in mailoutbox[0].subject.lower()


def test_request_code_unknown_email_is_silent(client, mailoutbox):
    r = client.post("/api/auth/request-code/", {"email": "ghost@example.com"})
    assert r.status_code == 200  # generic response, no enumeration
    assert LoginCode.objects.count() == 0
    assert len(mailoutbox) == 0


def test_request_code_is_throttled(client, user, mailoutbox):
    client.post("/api/auth/request-code/", {"email": "max@example.com"})
    client.post("/api/auth/request-code/", {"email": "max@example.com"})
    assert LoginCode.objects.filter(email="max@example.com").count() == 1
    assert len(mailoutbox) == 1


def test_verify_code_logs_in(client, user):
    _, code = LoginCode.issue("max@example.com")

    r = client.post("/api/auth/verify-code/", {"email": "max@example.com", "code": code})
    assert r.status_code == 200
    assert r.json()["email"] == "max@example.com"

    # Session established → protected endpoints now reachable
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["username"] == "max"


def test_verify_wrong_code_fails(client, user):
    LoginCode.issue("max@example.com")
    r = client.post("/api/auth/verify-code/", {"email": "max@example.com", "code": "000000"})
    assert r.status_code == 400
    assert client.get("/api/auth/me/").status_code in (401, 403)


def test_verify_expired_code_fails(client, user):
    code_obj, code = LoginCode.issue("max@example.com")
    code_obj.expires_at = timezone.now() - dt.timedelta(minutes=1)
    code_obj.save(update_fields=["expires_at"])

    r = client.post("/api/auth/verify-code/", {"email": "max@example.com", "code": code})
    assert r.status_code == 400


def test_code_locks_after_max_attempts(client, user, settings):
    settings.LOGIN_CODE_MAX_ATTEMPTS = 3
    _, code = LoginCode.issue("max@example.com")

    for _ in range(3):
        client.post("/api/auth/verify-code/", {"email": "max@example.com", "code": "999999"})

    # Even the correct code is now rejected (attempts exhausted)
    r = client.post("/api/auth/verify-code/", {"email": "max@example.com", "code": code})
    assert r.status_code == 400


def test_me_requires_authentication(client):
    assert client.get("/api/auth/me/").status_code in (401, 403)
