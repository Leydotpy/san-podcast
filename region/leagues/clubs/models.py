import uuid

from django.db import models

from apps.fields import AutoSlugField
from apps.media.images.models import Image


class TeamManager(models.Manager):
    pass


class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_index=True)
    league = models.ForeignKey("leagues.League", on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=120)
    short_name = models.CharField(max_length=5, null=True, blank=True)
    code = models.IntegerField(null=True, blank=True, unique=True)
    slug = AutoSlugField(populate_from=("id", "code", "name"))
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = TeamManager()

    def __str__(self):
        return str(self.slug)

    def goals(self, match=None):
        if match is not None:
            return self.goal_set.filter(match=match)
        return self.goal_set.all()

    def get_images(self):
        return Image.objects.filter_by_instance(self)


class Stadium(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_index=True)
    name = models.CharField(max_length=120)
    region = models.ForeignKey("region.Country", on_delete=models.CASCADE)
    team = models.OneToOneField(Team, on_delete=models.CASCADE)
    date_built = models.DateField(null=True, blank=True)
    capacity = models.PositiveIntegerField(default=0)

    objects = models.Manager()

    def __str__(self):
        return str(self.name)
