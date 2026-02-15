import datetime
import random
import uuid
from typing import TypeVar

from django.db import models
from django.db.models import Count, Q
from django.db.models import QuerySet
from django.utils import timezone

import utils
from apps.category.models import Category
from apps.fields.tagsfield import TagsField
from apps.media.audio.models import Audio
from apps.media.images.models import Image
from apps.memberships.models import Subscription, Feature, Plan
from apps.posts.models import BasePost, AbstractAnalytics, PostReaction, Comment, PostQueryset, \
    PostManager
from apps.posts.podcasts.utils import get_default_title
from core.compat import get_user_model
from utils.utils import get_client_ip

User = get_user_model()

T = TypeVar('T', bound=models.Model)


def _get_random(qs: QuerySet[T]) -> T | None:
    count = qs.count()
    if count > 0:
        return qs.all()[random.randint(0, count - 1)]
    return None


class PodcastQuerySet(PostQueryset):

    def recent(self):
        """Standard recent posts (last 3 days)"""
        limit = timezone.now() - datetime.timedelta(days=3)
        return self.filter(timestamp__gte=limit).order_by('-timestamp')

    def trending(self, days=3):
        """
        Sorts by 'Velocity': Number of views in the last X days.
        """
        # Calculate the date threshold
        time_threshold = timezone.now() - datetime.timedelta(days=days)

        # We query the ObjectView (view_logs) table via the GenericRelation
        return self.annotate(
            recent_view_count=Count(
                'view_logs',
                filter=Q(view_logs__timestamp__gte=time_threshold)
            )
        ).order_by('-recent_view_count', '-timestamp')

    def recommended(self, user, limit=10):
        """
        Smart recommendation engine.
        Priority 1: Podcasts matching User's Subscribed Teams/Regions/Competitions.
        Priority 2: Trending podcasts (fallback).
        """
        if not user.is_authenticated:
            # Fallback for anonymous users: Just show trending
            return self.trending()[:limit]

        # 1. Gather User's Interests (From their own AbstractAnalytics subscriptions)
        # Assuming the User model or a Profile model has these M2M relations,
        # OR we check what the user has previously subscribed to.
        # Let's assume we look at what entities the USER follows:

        # (You might need to adjust these lookups based on where you store User interests.
        # If User follows a 'Team', we want Podcasts tagged with that 'Team'.)

        # Example: Get IDs of teams/regions the user follows
        # subscribed_teams = user.following_teams.values_list('pk', flat=True)
        # subscribed_regions = user.following_regions.values_list('pk', flat=True)

        # COMPLEX QUERY: "Find podcasts that share a relationship with the user"
        # We use Q objects to construct a giant OR filter.

        # Note: This relies on how you link Users to Teams/Regions.
        # If you don't have direct User->Team links, you might use:
        # "Podcasts similar to podcasts the user has already liked/subscribed to"

        subscribed_podcasts = user.subscribed_analytics.all()  # From your AbstractAnalytics

        if not subscribed_podcasts.exists():
            return self.trending()[:limit]

        # Content-Based Filtering:
        # "Find podcasts that share the same Team, Region, or Competition as the podcasts I already subscribe to"

        return self.filter(
            Q(teams__in=subscribed_podcasts.values('teams')) |
            Q(regions__in=subscribed_podcasts.values('regions')) |
            Q(competitions__in=subscribed_podcasts.values('competitions'))
        ).exclude(
            # Don't show me podcasts I'm already subscribed to or have seen recently
            id__in=subscribed_podcasts.values('id')
        ).annotate(
            # Sort by "Relevance" (how many matching tags?)
            relevance=Count('teams') + Count('regions') + Count('competitions')
        ).order_by('-relevance', '-timestamp').distinct()[:limit]

    def popular_by_category(self, category_slug):
        return self.filter(categories__slug=category_slug).annotate(
            total_views=models.F("view_count")
        ).order_by('-total_views', '-timestamp')


class PodcastManager(PostManager):

    def get_queryset(self):
        return PodcastQuerySet(self.model, using=self._db)

    def trending(self):
        return self.get_queryset().trending()

    def recent(self):
        return self.get_queryset().recent()

    def recommended(self, user):
        return self.get_queryset().recommended(user)

    def popular_by_category(self, category_slug):
        return self.get_queryset().popular_by_category(category_slug=category_slug)


class Podcast(AbstractAnalytics, BasePost):
    tags = TagsField(max_length=255, null=True, blank=True)
    categories = models.ManyToManyField(Category, related_name="podcasts", blank=True)

    objects = PodcastManager()

    def __str__(self):
        return self.title

    def get_episodes(self) -> QuerySet["Episode"]:
        # Assuming 'episodes' is a related_name on an Episode model
        return self.episodes.all()

    def get_images(self) -> QuerySet[Image]:
        return Image.objects.filter_by_instance(self)

    def get_seasons(self) -> QuerySet:
        if self.is_parent:
            return self.get_children()
        return self.get_children().none()

    def get_raw_duration(self):
        episodes = self.get_episodes()
        if not episodes.exists():
            return 0
        return sum(e.get_raw_duration() for e in episodes)

    @property
    def duration_string(self) -> str:
        """
        Calculates total duration.
        Note: If 'duration' is a DB field on Episode, use aggregate(Sum('duration'))
        for better performance. Keeping original logic structure here.
        """
        episodes = self.get_episodes()
        if not episodes.exists():
            return "00:00"

        # Optimize: If possible, change this to database aggregation
        total_seconds = sum(e.get_duration() for e in episodes)
        # total_seconds = episodes.aggregate(Sum('duration'))['duration__sum']
        return utils.format_duration(total_seconds)  # Replace with utils.format_duration(total_seconds)

    def get_image_url(self):
        """Safe accessor for image."""
        image = _get_random(self.get_images())
        if image:
            if hasattr(image, "url"):
                return getattr(image, "url")
        return None

    def get_reactions(self):
        return PostReaction.objects.filter_by_instance(self)

    def check_is_liked(self, user):
        return self.get_reactions().filter(user=user).exists()

    def get_my_reaction(self, user):
        return self.get_reactions().filter(user=user).first()

    def get_comments(self):
        return Comment.objects.filter_by_instance(self)


class EpisodeQueryset(models.QuerySet):

    def latest_in_category(self, category_slug):
        return self.filter(
            models.Q(categories__slug=category_slug) | models.Q(podcast__categories__slug=category_slug)
        ).order_by("-timestamp").distinct()


class Episode(AbstractAnalytics):
    podcast = models.ForeignKey(Podcast, on_delete=models.CASCADE, related_name="episodes")
    description = models.TextField(null=True, blank=True)
    title = models.CharField(max_length=220, null=True, blank=True)
    subtitle = models.CharField(max_length=220, null=True, blank=True)
    slug = models.UUIDField(default=uuid.uuid4)
    hosts = TagsField(max_length=220, null=True, blank=True)
    tags = TagsField(max_length=255, null=True, blank=True)

    public_release_date = models.DateTimeField(null=True, blank=True)
    exclusive = models.BooleanField(default=False,
                                    help_text='If True, only paying plans (Fan+) can access after release')
    early_access_hours = models.PositiveSmallIntegerField(null=True, blank=True,
                                                          help_text='If set overrides plan early access hours')

    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    # new denormalized / precomputed field for fast ranking
    trend_score = models.FloatField(default=0.0, db_index=True)

    # optional categories per episode (useful if you tag individual episodes)
    categories = models.ManyToManyField(Category, related_name="episodes", blank=True)

    objects = EpisodeQueryset.as_manager()

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Episode"
        verbose_name_plural = "Episodes"
        ordering = ("-public_release_date",)

    @property
    def images(self) -> QuerySet[Image]:
        return Image.objects.filter_by_instance(self)

    @property
    def audio_qs(self) -> QuerySet[Audio]:
        return self.audios.all()

    @property
    def category_qs(self) -> QuerySet[Category]:
        return self.categories.union(self.podcast.categories.all()).distinct()

    def get_highest_plan_in_categories(self) -> Plan:
        return (self.category_qs.select_related("tier").order_by("-tier__tier").first()).tier

    @property
    def audio(self):
        return self.audios.filter(master=True).first()

    def in_queue(self, request) -> bool:
        return request.queue.tracks.filter(track_id=self.pk).exists()

    def get_reactions(self):
        return PostReaction.objects.filter_by_instance(self)

    def check_is_liked(self, user):
        return self.get_reactions().filter(user=user).exists()

    def get_my_reaction(self, user):
        return self.get_reactions().filter(user=user).first()

    def get_comments(self):
        return Comment.objects.filter_by_instance(self)

    def get_image(self):
        image = _get_random(self.images)
        if image:
            if hasattr(image, "url"):
                return getattr(image, "url")
        return None

    def get_type(self):
        return f"{self._meta.app_label}.{self.__class__.__name__}"

    def get_duration(self):
        return float(self.audio.duration)

    def get_raw_duration(self):
        return round(self.audio.duration)

    @property
    def duration(self):
        return utils.format_duration(self.get_duration())

    def save(
            self, *args, **kwargs
    ):
        if not self.title:
            self.title = get_default_title(self)

        super().save(*args, **kwargs)

    @staticmethod
    def is_downloadable_by(user):
        sub = Subscription.objects.active_for_user(user).order_by('-plan__tier_level').first()
        if not sub:
            return False
        return bool(sub.plan.can_download)

    def available_for(self, *, plan: Plan = None, now=None):
        """
        Determine whether this episode is AVAILABLE for a given PLAN right now,
        considering public release date, exclusivity and early-access windows.

        - plan: Plan instance or None (treats as free/no-plan).
        - now: optional datetime for deterministic tests (defaults to timezone.now()).

        IMPORTANT: This function only evaluates time/plan-based availability.
        It does NOT check entitlements, plan-targeted entitlements, admin bypass,
        or category mapping. Those belong in AccessService.
        """
        if now is None:
            now = timezone.now()

        # If no plan supplied, we can only allow if it's public and non-exclusive
        if plan is None:
            return False

        has_perm = any((bool(self.get_highest_plan_in_categories().ranks_above(plan)), self.category_qs.filter(
            tier=plan).exists()))

        # If public_release_date isn't set -> not public unless plan grants full access
        if has_perm and (not self.public_release_date):
            # plan must grant 'exclusive' or 'all' to access unreleased episodes
            if plan.grants(Feature.Kind.EXCLUSIVE):
                return True
            return False

        # If episode is public (exclusive to select plans) and released -> accessible by everyone in the tier
        if has_perm and (now >= self.public_release_date):
            return True

        # Determine early access window: episode override takes precedence
        episode_early = self.early_access_hours if (self.early_access_hours is not None) else 0
        plan_early = 0
        early_feat = plan.get_feature(Feature.Kind.EARLY_ACCESS)
        if early_feat:
            plan_early = early_feat.early_access_hours or 0
        early_hours = max(episode_early, plan_early)

        available_at = self.public_release_date - datetime.timedelta(hours=early_hours)

        # If plan grants the exclusive/all feature, and now >= available_at --> access
        if plan.grants(Feature.Kind.EARLY_ACCESS) and now >= available_at:
            return True
        return False

    def get_audio_quality(self, quality):
        audio = self.audios.filter(quality=quality).first()
        if audio:
            return audio.file.url
        return self.audios.order_by("bitrate").last().file.url


class PlayBackManager(models.Manager):
    def get_recently_played(self, request):
        qs = self.get_queryset()
        if request.user.is_authenticated:
            qs = qs.filter(user=request.user)
        else:
            qs = qs.filter(ip_address=get_client_ip(request))
        return qs.select_related("episode").order_by("-last_played_at")

    def get_uncompleted(self, request, limit=10):
        return self.get_recently_played(request).filter(is_completed=False)[:limit]

    def update_progress(self, user, episode_id, ip_address, seconds, is_completed=False):
        progress, created = self.get_queryset().update_or_create(
            user=user,
            ip_address=ip_address,
            episode_id=episode_id,
            defaults={
                'current_timestamp': seconds,
                'is_completed': is_completed,
                'last_played_at': timezone.now(),
            }
        )
        return progress


class PlayBack(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="playback_history")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    episode = models.ForeignKey(Episode, on_delete=models.CASCADE)
    current_timestamp = models.IntegerField(default=0, help_text="Seconds Played")
    is_completed = models.BooleanField(default=False)
    last_played_at = models.DateTimeField(auto_now=True)

    objects = PlayBackManager()

    class Meta:
        unique_together = ("user", "episode")
        ordering = ["-last_played_at"]
        verbose_name_plural = "PlayBack"

    def __str__(self):
        return f"{self.user} - {self.episode.title} ({self.current_timestamp}s)"

    def get_percentage_completed(self):
        if self.episode.get_duration() > 0:
            return round((self.current_timestamp / self.episode.get_raw_duration()) * 100)
        return 0

    def get_remaining_minutes(self):
        return round(self.episode.get_raw_duration() - self.current_timestamp)


class Summary(models.Model):
    episode = models.OneToOneField(Episode, on_delete=models.CASCADE, related_name='summary')
    summary_text = models.TextField()
    model = models.CharField(max_length=64)  # model used for summary
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"summary-{self.episode.title}"
