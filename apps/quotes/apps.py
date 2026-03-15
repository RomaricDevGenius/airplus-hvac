from django.apps import AppConfig


class QuotesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.quotes"
    verbose_name = "Demandes de devis"

    def ready(self):
        import apps.quotes.signals  # noqa: F401
