from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class PollsConfig(AppConfig):
    name = "apps.posts.polls"
    label = "polls"
    verbose_name = _("Polls")