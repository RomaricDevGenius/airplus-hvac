from django.contrib import admin
from .models import ClientProfile


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "company_name", "phone", "password_changed", "created_at")
    search_fields = ("user__username", "user__email", "company_name", "phone")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
