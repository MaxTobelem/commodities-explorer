from django.urls import path

from .views import CsrfView, LogoutView, MeView, RequestCodeView, VerifyCodeView

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="auth-csrf"),
    path("request-code/", RequestCodeView.as_view(), name="auth-request-code"),
    path("verify-code/", VerifyCodeView.as_view(), name="auth-verify-code"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("logout/", LogoutView.as_view(), name="auth-logout"),
]
