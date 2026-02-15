from django.utils.translation import gettext_lazy as _
from core.application import AppConfig


class AccountsConfig(AppConfig):
    name = 'apps.accounts'
    label = "accounts"
    verbose_name = _("Accounts")

    namespace = "accounts"

    def ready(self):
        from . import receivers
