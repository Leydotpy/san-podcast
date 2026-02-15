from typing import TypeVar
from uuid import uuid4

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.analytics.models import AbstractAnalytics
from apps.comments.models import Comment
from apps.fields import AutoSlugField

T = TypeVar('T', bound=models.Model)

# Create your models here.

now = timezone.now()


class ReactionQuerySet(models.QuerySet):
    def filter_by_instance(self, instance):
        content_type = ContentType.objects.get_for_model(instance.__class__)
        return super(ReactionQuerySet, self).filter(content_type=content_type, object_id=instance.id)


class ReactionManager(models.Manager):

    @property
    def _queryset(self):
        return ReactionQuerySet(model=self.model, using=self._db)

    def filter_by_instance(self, instance):
        return self._queryset.filter_by_instance(instance=instance)

    def create_for_model(self, model: str, object_id, user, reaction=None):
        """
        :param model: The model class name
        :param object_id: The Post or object ID
        :param user: The request user
        :param reaction: The reaction (E.g 'like')
        :return: PostReaction Model
        """
        app_label, model_name = model.split('.')
        klass = get_object_or_404(ContentType, app_label=app_label, model=model_name)
        try:
            obj = klass.get_object_for_this_type(pk=object_id)
        except ObjectDoesNotExist:
            raise Exception("object not found")
        if obj.get_reactions().filter(user=user, reaction=reaction).exists():
            raise Exception("you already have a reaction")
        self.create(content_type=klass, user=user, object_id=obj.id, reaction=reaction)
        return obj


class PostReaction(models.Model):
    class Reaction(models.TextChoices):
        LIKE = "like", _("Like")
        LOVE = "love", _("Love")
        HAPPY = "happy", _("Happy")
        SAD = "sad", _("Sad")
        ANGRY = "angry", _("Angry")
        FUNNY = "funny", _("Funny")
        DISLIKE = "dislike", _("Dislike")

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="reactions")
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reaction = models.CharField(max_length=20, choices=Reaction.choices, default=Reaction.LIKE)
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = ReactionManager()

    def __str__(self):
        return "{0} by {1}".format(self.reaction, self.user)


class PostQueryset(models.QuerySet):

    def browsable(self):
        return self.filter(parent=None)


class PostManager(models.Manager):

    def get_queryset(self):
        return PostQueryset(self.model, using=self._db)

    def browsable(self):
        return self.get_queryset().browsable()


class BasePost(models.Model):
    class Structure(models.TextChoices):
        STANDALONE = "STANDALONE", _("Stand-alone Post/Podcast")
        PARENT = "PARENT", _("Parent Post/Podcast")
        CHILD = "CHILD", _("Child Post/Podcast Season")

    title = models.CharField(max_length=220)
    subtitle = models.CharField(max_length=120, null=True, blank=True)
    structure = models.CharField(
        max_length=20,
        choices=Structure.choices,
        default=Structure.STANDALONE
    )
    description = models.TextField(blank=True, null=True)
    slug = models.SlugField(default=uuid4, null=True, blank=True)

    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        related_name="children",
        null=True,
        blank=True,
        help_text=_("Select a parent only if this is a Season or Child post.")
    )

    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = PostManager() # Assuming exists

    class Meta:
        abstract = True

    @property
    def is_parent(self):
        return self.structure == self.Structure.PARENT

    @property
    def is_child(self):
        return self.structure == self.Structure.CHILD

    @property
    def is_standalone(self):
        return self.structure == self.Structure.STANDALONE

    def get_children(self) -> QuerySet:
        return self.children.all()

    def clean(self):
        """Explicit validation logic instead of dynamic getattr calls."""
        if self.is_standalone:
            self._validate_standalone()
        elif self.is_child:
            self._validate_child()
        elif self.is_parent:
            self._validate_standalone()  # Parent validation is same as standalone for now

    def _validate_standalone(self):
        if not self.title:
            raise ValidationError(_("Title is required."))
        if self.parent:
            raise ValidationError(_("Standalone/Parent posts cannot have a parent."))

    def _validate_child(self):
        if not self.parent:
            raise ValidationError(_("Child posts/seasons must have a parent."))
        if not self.parent.is_parent:
            raise ValidationError(_("The selected parent is not marked as a Parent structure."))


def category_upload_to(instance, filename):
    name, ext = filename.split(".")
    return f"{instance.__class__.__name__}/{instance.name}/_{name}.{now.strftime('%H%M%S.%f')}.{ext}"


class Post(AbstractAnalytics, BasePost):
    content = models.JSONField()
    poll = models.ForeignKey("polls.Poll", on_delete=models.CASCADE, null=True, blank=True)
