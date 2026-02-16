import uuid

from django.db import models
from apps.fields import AutoSlugField
from apps.media.images.models import Image


class LeagueManager(models.Manager):
    pass


class League(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_index=True)
    region = models.ForeignKey("region.Country", on_delete=models.SET_NULL, null=True, related_name="leagues")
    name = models.CharField(max_length=120)
    short_name = models.CharField(max_length=120, null=True, blank=True)
    slug = AutoSlugField(populate_from=("id", "name", "region", "timestamp"))
    code = models.IntegerField(null=True, blank=True, unique=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = LeagueManager()

    def __str__(self):
        return str(self.slug)

    def get_images(self):
        return Image.objects.filter_by_instance(self)


class Campaign(models.Model):
    start = models.DateField()
    end = models.DateField()
    code = AutoSlugField(populate_from=("start", "end"))

    objects = models.Manager()

    def __str__(self):
        return "{} Season".format(self.name)

    @property
    def name(self):
        return "{}/{}".format(self.start.year, self.end.year)