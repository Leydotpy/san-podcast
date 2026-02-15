from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class PostsConfig(AppConfig):
    name = 'apps.posts'
    label = 'posts'
    verbose_name = _("Posts")

    namespace = 'posts'
