from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class AnalyticsConfig(AppConfig):
    name = 'apps.analytics'
    label = 'analytics'
    verbose_name = _("Analytics")

    namespace = 'analytics'
