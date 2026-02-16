from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save
from apps.region.leagues.models import League
from utils.utils import generate_code

from apps.thumbnail.utils import ThumbnailGenerator


@receiver(pre_save, sender=League)
def league_code_generate_fn(sender, instance, **kwargs):  # NOQA
    if not instance.code:
        instance.code = generate_code(4, klass=instance.__class__)
