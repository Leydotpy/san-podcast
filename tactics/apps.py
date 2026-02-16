from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class TacticsConfig(AppConfig):
    name = "apps.tactics"
    label = "tactics"
    verbose_name = _("Tactics")
    verbose_name_plural = _("Tactics")

    def ready(self):
        from . import receiver
