from django.contrib import admin
from .models import QuoteRequest, QuoteRequestItem


class QuoteRequestItemInline(admin.TabularInline):
    model = QuoteRequestItem
    extra = 0
    raw_id_fields = ("product",)


@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    list_display = ("subject", "client", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("subject", "message", "client__username", "client__email")
    inlines = [QuoteRequestItemInline]
    readonly_fields = ("created_at", "updated_at")
