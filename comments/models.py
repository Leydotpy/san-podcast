import datetime
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from rest_framework.serializers import ValidationError

# Create your models here.

User = get_user_model()

now = datetime.datetime.now()


def upload_location(instance, filename):
    path = f"comments/{instance.user.username}/{instance.comment_type}/{now.strftime('%H_%M_%S.%f')}_{filename}"
    return path


class CommentManager(models.Manager):

    def all(self):
        return super(CommentManager, self).filter(parent=None)

    def filter_by_instance(self, instance):
        c_type = ContentType.objects.get_for_model(instance.__class__)
        obj_id = instance.id
        return super(CommentManager, self).filter(content_type=c_type, object_id=obj_id).filter(parent=None)

    def create_by_model_type(self, model_type, object_id, comment_type, content, media, user, parent_obj=None):
        content_type = get_object_or_404(ContentType, model=model_type)
        try:
            obj = content_type.get_object_for_this_type(id=object_id)
        except ObjectDoesNotExist:
            raise
        if comment_type == "text" and content == "":
            raise ValidationError({"comment": "Please type a comment"})
        elif comment_type == "sticker" or comment_type == "image" and media is None:
            raise ValidationError({"comment": "Please upload a valid media file"})
        instance = self.create(content=content, comment_type=comment_type,
                               user=user, content_type=content_type, media=media, object_id=obj.id)
        if parent_obj:
            self.filter(pk=instance.id).update(parent=parent_obj)
        return instance


class Comment(models.Model):
    class Type(models.TextChoices):
        TEXT = "text", _("Text")
        IMAGE = "image", _("Image")
        STICKER = "sticker", _("Sticker")

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE)
    content = models.TextField(null=True, blank=True)
    comment_type = models.CharField(max_length=30, choices=Type.choices, default=Type.TEXT)
    media = models.FileField(upload_to=upload_location, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = CommentManager()

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return str(self.user.username)

    @property
    def children(self):
        return Comment.objects.filter(parent=self)

    @property
    def is_parent(self):
        if self.parent is not None:
            return False
        return True

    @property
    def reply_count(self):
        return self.children.count()
