from django.utils.translation import gettext_lazy as _

from core.application import AppConfig


class ThumbnailConfig(AppConfig):
    name = "apps.thumbnail"
    label = "thumbnail"
    verbose_name = _("Thumbnail")

    namespace = "thumbnail"
