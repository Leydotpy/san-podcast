from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class PodcastsConfig(AppConfig):
    name = "apps.posts.podcasts"
    label = "podcasts"
    verbose_name = _("Podcasts")

    namespace = "podcasts"

    # def ready(self):
    #     from apps.posts.podcasts import receivers # noqa
