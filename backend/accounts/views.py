from django.contrib.auth import login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import auth


def user_payload(user) -> dict:
    return {
        "id": user.id,
        "username": user.get_username(),
        "email": user.email,
        "is_staff": user.is_staff,
    }


class RequestCodeView(APIView):
    """POST {email} → emails a one-time code to known accounts (generic response)."""

    authentication_classes = []  # no auth/CSRF needed to ask for a code
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        if not email:
            return Response({"detail": "Email requis."}, status=400)
        auth.request_code(email)
        return Response({"detail": "Si un compte existe, un code vient d'être envoyé."})


class VerifyCodeView(APIView):
    """POST {email, code} → logs the user in (session) on success."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        code = (request.data.get("code") or "").strip()
        if not email or not code:
            return Response({"detail": "Email et code requis."}, status=400)
        user = auth.verify_code(email, code)
        if user is None:
            return Response({"detail": "Code invalide ou expiré."}, status=400)
        login(request, user, backend=auth.BACKEND)
        return Response(user_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"detail": "Déconnecté."})


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MeView(APIView):
    """Current user; also sets the CSRF cookie the SPA needs for unsafe requests."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(user_payload(request.user))


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"detail": "ok"})
