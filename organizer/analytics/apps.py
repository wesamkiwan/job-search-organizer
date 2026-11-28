from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "organizer.analytics"
    verbose_name = "Analytics"

    def ready(self) -> None:
        # Importing these modules runs their @widget decorators, which add the widgets
        # to the registry. ready() runs once, when Django has loaded all apps.
        from . import insights, performance  # noqa: F401
