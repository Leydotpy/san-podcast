from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.shortcuts import get_object_or_404
from apps.posts.models import BasePost
from core.compat import AUTH_USER_MODEL


class Poll(BasePost):
    title = models.CharField(_("Question"), max_length=220)
    max_hours = models.FloatField(null=True, blank=True)
    expires = models.DateTimeField(null=True, blank=True)

    @property
    def poll_choices(self):
        return self.choices.all()

    @property
    def poll_votes(self):
        qs = self.poll_choices
        _votes = 0
        for q in qs:
            _votes += int(q.votes.count())
        return _votes

    @property
    def poll_voters(self):
        queryset = self.poll_choices
        # voters = list()
        # for query in queryset:
        #     for user in query.votes.all():
        #         voters.append(user)
        # return voters
        return [user for query in queryset for user in query.votes.all()]

    @property
    def can_vote(self):
        return now() >= self.expires

    def clean(self):
        if not self.expires and not self.max_hours:
            raise ValidationError("Set expiry or maximum hours for voting")
        return super(Poll, self).clean()

    def save(
        self, *args, **kwargs
    ):
        if not self.expires:
            self.expires = self.timestamp + timedelta(hours=self.max_hours)
        return super(Poll, self).save(*args, **kwargs)


class ChoiceQuerySet(models.QuerySet):

    def filter_by_poll(self, post_id):
        return self.filter(post__id=post_id)


class ChoiceManager(models.Manager):

    def get_queryset(self):
        return ChoiceQuerySet(self.model, using=self._db)

    def filter_by_poll(self, post_id):
        return self.get_queryset().filter_by_poll(post_id)

    def calculate(self, poll_id):
        poll = self.get(id=poll_id)
        total_votes = poll.post.poll_votes
        try:
            return int(poll.votes.count()) / total_votes * 100
        except ZeroDivisionError:
            return 0

    def vote(self, poll_id, user):
        poll = get_object_or_404(self.get_queryset(), id=poll_id)
        post = poll.post
        if user not in post.poll_voters:
            poll.votes.add(user)
            return poll.calculate, True
        return False

    def add_poll_choice(self, choice, post_id, image=None):
        poll = get_object_or_404(Poll, id=post_id)
        obj = self.create(poll=poll, choice=choice)
        if image is not None:
            self.filter(id=obj.id).update(image=image)
        return obj


def poll_upload_to(instance, filename):
    file, ext = filename.split(".")
    return f"poll/{instance.poll.slug}/{instance.choice}/{now().strftime('%H%M%S.%f')}.{file}_.{ext}"


class Choice(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name="choices")
    choice = models.CharField(max_length=120)
    image = models.ImageField(upload_to=poll_upload_to, null=True, blank=True)
    votes = models.ManyToManyField(AUTH_USER_MODEL, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = ChoiceManager()

    def __str__(self):
        return str(self.poll)

    def voted(self, user):
        return bool(user in self.votes.all())

    @property
    def calculate(self):
        try:
            return int(self.votes.count()) / self.poll.poll_votes * 100
        except ZeroDivisionError:
            return 0
