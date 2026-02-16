from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class ClubsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.region.leagues.clubs"
    label = "clubs"
    verbose_name = _("Clubs")

    namespace = "clubs"

    def ready(self):
        from apps.region.leagues.clubs import receivers # NOQA
