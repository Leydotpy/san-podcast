import os
import shutil
import random
from PIL import Image
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.files import File
from django.shortcuts import get_object_or_404

from apps.thumbnail.models import Thumbnail


class ThumbnailGenerator:
    dimensions = (
        (Thumbnail.Size.XL, (600, 600)),
        (Thumbnail.Size.LG, (400, 400)),
        (Thumbnail.Size.MD, (200, 200)),
        (Thumbnail.Size.SM, (150, 150)),
        (Thumbnail.Size.XS, (40, 40)),
    )

    @staticmethod
    def get_model(model, mid):
        ctype = get_object_or_404(ContentType, model=model.lower())
        try:
            return ctype, ctype.get_object_for_this_type(id=mid)
        except ObjectDoesNotExist:
            raise

    @classmethod
    def generate_thumbnail(cls, instance, instance_id):
        content_type, obj = cls.get_model(instance.__class__.__name__, instance_id)
        try:
            field = instance.file
        except AttributeError as e:
            raise e
        for dimension in cls.dimensions:
            dim, created = Thumbnail.objects.get_or_create(
                content_type=content_type,
                object_id=obj.id,
                type=dimension[0]
            )
            if created:
                cls._generate(
                    media_path=field.path,
                    instance=dim,
                    max_length=dimension[1][0],
                    max_width=dimension[1][1],
                    code=instance.pk,
                )

    @staticmethod
    def _generate(media_path, instance, code, max_length, max_width):
        filename = os.path.basename(media_path)
        thumb = Image.open(media_path)
        size = (max_length, max_width)
        thumb.thumbnail(size, Image.Resampling.LANCZOS)
        temp_loc = "{}/{}/tmp".format(settings.MEDIA_ROOT, code)
        if not os.path.exists(temp_loc):
            os.makedirs(temp_loc)
        temp_file_path = os.path.join(temp_loc, filename)
        if os.path.exists(temp_file_path):
            temp_path = os.path.join(temp_loc, "{}".format(random.random()))
            os.makedirs(temp_path)
            temp_file_path = os.path.join(temp_path, filename)

        temp_image = open(temp_file_path, 'wb')
        thumb.save(temp_image)
        with open(temp_file_path, 'rb') as thumb_data:
            instance.media = File(thumb_data, name=filename)
            instance.save()
        shutil.rmtree(temp_loc, ignore_errors=True)
        return True
