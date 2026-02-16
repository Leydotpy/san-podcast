from django.utils.translation import gettext_lazy as _

from core.application import AppConfig


class RecommendationConfig(AppConfig):
    name = "apps.recommendation"
    label = "recommendation"
    verbose_name = _("Recommendation")
    verbose_name_plural = _("Recommendations")

    namespace = "recommendation"
