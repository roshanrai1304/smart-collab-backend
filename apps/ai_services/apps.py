from django.apps import AppConfig


class AiServicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai_services"
    verbose_name = "AI Services"
    
    def ready(self):
        """Import signals when the app is ready."""
        import apps.ai_services.signals  # noqa: F401