from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class CommentsConfig(AppConfig):
    name = 'apps.comments'
    label = 'comments'
    verbose_name = _('Comments')

    namespace = 'comments'
