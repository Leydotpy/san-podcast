from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Audio
from .tasks import process_audio


@receiver(post_save, sender=Audio)
def audio_post_save(sender, instance, created, **kwargs):
    if created and instance.master and not instance.processed:
        process_audio.delay(str(instance.id))
