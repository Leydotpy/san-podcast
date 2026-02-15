from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _



class AudioConfig(AppConfig):
    name = 'apps.media.audio'
    label = 'audio'
    verbose_name = _('Audio')
    verbose_name_plural = _('Audios')

    namespace = "audio"

    def ready(self):
        from . import receivers