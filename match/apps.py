from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class MatchConfig(AppConfig):
    name = "apps.match"
    label = "match"
    verbose_name = _("Match")
    verbose_name_plural = _("Matches")
