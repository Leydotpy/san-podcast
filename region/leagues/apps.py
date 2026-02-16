from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class LeaguesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.region.leagues"
    label = "leagues"
    verbose_name = _("Leagues")

    namespace = "leagues"

    def ready(self):
        from apps.region.leagues import receivers # NOQA
