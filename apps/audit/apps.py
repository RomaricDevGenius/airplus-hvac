from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    verbose_name = "Journal d'audit"

    def ready(self):
        """
        Branche les récepteurs d'authentification (connexion, déconnexion,
        échec de connexion).

        L'import est volontairement fait ICI et pas au niveau du module : au
        moment où `apps.py` est lu, le registre des applications n'est pas
        encore prêt et importer des modèles déclencherait un chargement
        prématuré (AppRegistryNotReady).
        """
        from . import signals  # noqa: F401
