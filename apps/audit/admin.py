"""
Admin du journal d'audit : consultation seule.
Aucun ajout, aucune modification, aucune suppression n'est possible depuis
l'interface — le journal est immuable (voir apps/audit/models.py).
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Consultation du journal d'audit (lecture seule)."""

    list_display = (
        "created_at",
        "action",
        "actor_label",
        "object_repr",
        "content_type",
        "ip_address",
    )
    list_filter = ("action", "created_at", "content_type")
    search_fields = (
        "actor_label",
        "object_repr",
        "object_id",
        "ip_address",
        "user_agent",
    )
    date_hierarchy = "created_at"
    list_select_related = ("actor", "content_type")
    ordering = ("-created_at",)
    list_per_page = 50

    fields = (
        "created_at",
        "action",
        "actor",
        "actor_label",
        "content_type",
        "object_id",
        "object_repr",
        "changes_lisibles",
        "changes",
        "extra",
        "ip_address",
        "user_agent",
    )
    readonly_fields = fields

    @admin.display(description="Modifications")
    def changes_lisibles(self, obj):
        """Rend les couples avant/après sous forme de liste HTML."""
        lignes = obj.changes_display
        if not lignes:
            return "—"
        html = "".join(
            format_html(
                "<li><strong>{}</strong> : {} &rarr; {}</li>",
                ligne["champ"], ligne["avant"], ligne["apres"],
            )
            for ligne in lignes
        )
        return mark_safe(f"<ul style='margin:0;padding-left:18px'>{html}</ul>")

    # --- Verrouillage complet -------------------------------------------------

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        """Retire l'action « supprimer les objets sélectionnés »."""
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
