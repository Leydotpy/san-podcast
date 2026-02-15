import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from core.compat import get_user_model

User = get_user_model()


def audio_upload_to(instance, filename):
    # safe path using slugified episode title or id
    base = slugify(instance.episode.slug) if instance.episode and instance.episode.slug else str(instance.episode_id)
    return f"episodes/{base}/{instance.quality}/{filename}"

class AudioQualityQuerySet(models.QuerySet):

    def low(self):
        return self.filter(quality=Audio.Quality.LOW)

    def medium(self):
        return self.filter(quality=Audio.Quality.MEDIUM)

    def high(self):
        return self.filter(quality=Audio.Quality.HIGH)

    def hls(self):
        return self.filter(quality=Audio.Quality.HLS)

    def preview(self):
        return self.filter(quality=Audio.Quality.PREVIEW)


class AudioQuerySet(AudioQualityQuerySet):
    def master(self, **kwargs):
        return self.select_related("episode").filter(master=True, **kwargs).first()


class AudioManager(models.Manager):
    def get_queryset(self):
        return AudioQuerySet(self.model, using=self._db)

    def master(self, episode_id):
        return self.get_queryset().master(episode_id=episode_id)

class Audio(models.Model):
    class Quality(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")
        HLS = "hls", _("HLS")
        PREVIEW = "preview", _("Preview")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    duration = models.PositiveIntegerField(null=True, blank=True, help_text="seconds")
    codec = models.CharField(max_length=32, default="mp3")
    sample_rate = models.PositiveIntegerField(null=True, blank=True)  # Hz
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    episode = models.ForeignKey("podcasts.Episode", related_name="audios", on_delete=models.CASCADE)  # adjust app/model name
    quality = models.CharField(max_length=16, null=True, blank=True, choices=Quality.choices, help_text="Quality to save or Preset key used to generate HLS (low|medium|high)")
    file = models.FileField(upload_to=audio_upload_to)
    prefix = models.CharField(max_length=512, blank=True,
                              help_text="Storage prefix for HLS segments (directory or key prefix)")
    bitrate = models.PositiveIntegerField(help_text="kbps", null=True, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    master = models.BooleanField(default=False)

    objects = AudioManager()
    qualities = AudioQualityQuerySet.as_manager()

    def __str__(self):
        return f"{self.episode.title}_{self.name or self.quality}"

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["episode"], condition=Q(master=True), name="unique_master_per_episode"),
            models.UniqueConstraint(fields=["episode", "quality"], name="unique_episode_quality"),
        ]
        indexes = [
            models.Index(fields=["episode", "quality"]),
        ]

    def clean(self):
        # enforce single master via DB constraint too
        if self.master:
            qs = Audio.objects.filter(episode=self.episode, master=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("This episode already has a master audio")

    def save(self, *args, **kwargs):
        # Only run clean validations that matter here (avoid heavy full_clean)
        self.clean()
        super().save(*args, **kwargs)

