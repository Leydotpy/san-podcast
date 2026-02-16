from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from apps.region.models import Region
from utils.utils import generate_code

from apps.thumbnail.utils import ThumbnailGenerator


@receiver(pre_save, sender=Region)
def generate_code_for_region(sender, instance, *args, **kwargs): # NOQA
    if not instance.code:
        instance.code = generate_code(4, klass=instance.__class__)
