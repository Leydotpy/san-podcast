from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class RegionConfig(AppConfig):
    name = "apps.region"
    label = "region"
    verbose_name = _("Region")

    namespace = "region"

    def ready(self):
        from apps.region import receivers # noqa
