from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import LoginCode


@admin.register(LoginCode)
class LoginCodeAdmin(ModelAdmin):
    list_display = ["email", "created_at", "expires_at", "attempts", "used"]
    list_filter = ["used"]
    search_fields = ["email"]
    readonly_fields = ["email", "code_hash", "created_at", "expires_at", "attempts", "used"]

    def has_add_permission(self, request):
        return False
