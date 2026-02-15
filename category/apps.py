from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class CategoryConfig(AppConfig):
    name = "apps.category"
    label = "category"
    verbose_name = _("Category")
    verbose_name_plural = _("Categories")

    namespace = "category"

