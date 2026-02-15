from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class ForumConfig(AppConfig):
    name = 'apps.forum'
    label = 'forum'
    verbose_name = _('Forum')

    namespace = 'forum'
