from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "organizer.analytics"
    verbose_name = "Analytics"

    def ready(self) -> None:
        # Importing these modules runs their @widget decorators, which add the widgets
        # to the registry. ready() runs once, when Django has loaded all apps.
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from . import cache, insights, performance  # noqa: F401

        # Signals: Django calls cache.bump after ANY model is saved or deleted (or a
        # many-to-many link such as tags changes); bump itself ignores the models the
        # dashboard doesn't read. dispatch_uid prevents connecting twice.
        for signal in (post_save, post_delete, m2m_changed):
            signal.connect(cache.bump, dispatch_uid=f"analytics-cache-{signal}")
