from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.utils.translation import gettext_lazy as _


def thumbnail_upload_to(instance, filename):
    folder = instance.content_object.pk
    return "{}/{}/{}".format(folder, instance.type, filename)


class ThumbnailQuerySet(models.QuerySet):

    def by_instance(self, instance):
        content_type = ContentType.objects.get_for_model(instance.__class__)
        obj_id = instance.id
        return self.filter(content_type=content_type, object_id=obj_id)


class ThumbnailManager(models.Manager):

    @property
    def _queryset(self):
        return ThumbnailQuerySet(model=self.model, using=self._db)

    def filter_by_instance(self, instance):
        return self._queryset.by_instance(instance=instance)

    def exist(self, instance):
        return self.filter_by_instance(instance=instance).exists()


class Thumbnail(models.Model):
    class Size(models.TextChoices):
        XL = "xl", _("XL")
        LG = "lg", _("LG")
        MD = "md", _("MD")
        SM = "sm", _("SM")
        XS = "xs", _("XS")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    type = models.CharField(max_length=2, choices=Size.choices, default=Size.MD)
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    media = models.ImageField(
        width_field="width",
        height_field="height",
        blank=True, null=True,
        upload_to=thumbnail_upload_to)
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = ThumbnailManager()

    def __str__(self):
        return str(self.media.path)

    def get_absolute_url(self, request):
        return request.build_absolute_uri(self.media.url)
