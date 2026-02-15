from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class BillingConfig(AppConfig):
    name = 'apps.billing'
    label = 'billing'

    verbose_name = _('Billing')
    verbose_name_plural = _('Billing')

    namespace = "billing"