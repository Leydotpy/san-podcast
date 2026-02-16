import uuid

from django.db import models

from apps.fields import AutoSlugField
from apps.media.images.models import Image


# Create your models here.

class RegionManager(models.Manager):
    pass


class Region(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_index=True)
    name = models.CharField(max_length=120)
    code = models.IntegerField(null=True, blank=True, unique=True)
    slug = AutoSlugField(populate_from=("id", "name", "code"))
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = RegionManager()

    def __str__(self):
        return str(self.slug)

    def get_countries(self):
        return self.countries.all()

    def get_images(self):
        return Image.objects.filter_by_instance(self)


class Country(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_index=True)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='countries')
    name = models.CharField(max_length=120)
    slug = AutoSlugField(populate_from=("id", "name", "code"))
    code = models.IntegerField(null=True, blank=True, unique=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.slug)

    class Meta:
        verbose_name_plural = "Countries"

    def get_images(self):
        return Image.objects.filter_by_instance(self)

    def get_leagues(self):
        return self.leagues.all()
