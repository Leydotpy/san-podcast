from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.db.models import (
    Count, F, FloatField, IntegerField, OuterRef, Subquery, Value, ExpressionWrapper
)
from django.db.models import Q
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.analytics.models import ObjectView
from apps.category.models import Category
from apps.media.models import PlayList
from apps.promotions.models import HandPickedPostList
from .models import Episode, Podcast, PlayBack

now = timezone.now()


def trending_episodes(limit=24):
    since_24h = now - timedelta(hours=24)
    since_7d = now - timedelta(days=7)

    plays_24q = PlayBack.objects.filter(
        episode=OuterRef("pk"),
        last_played_at__gte=since_24h,
    ).values("episode").annotate(c=Count("id")).values("c")

    plays_7dq = PlayBack.objects.filter(
        episode=OuterRef("pk"),
        last_played_at__gte=since_7d,
    ).values("episode").annotate(c=Count("id")).values("c")

    completions_q = PlayBack.objects.filter(
        episode=OuterRef("pk"),
        is_completed=True,
    ).values("episode").annotate(c=Count("id")).values("c")

    qs = Episode.objects.select_related("podcast").annotate(
        plays_24h=Coalesce(Subquery(plays_24q, output_field=IntegerField()), Value(0)),
        plays_7d=Coalesce(Subquery(plays_7dq, output_field=IntegerField()), Value(0)),
        completions=Coalesce(Subquery(completions_q, output_field=IntegerField()), Value(0)),
        stored_trend=Coalesce(F("trend_score"), Value(0.0)),
    )

    score = ExpressionWrapper(
        F("plays_24h") * 4.0 +
        F("plays_7d") * 1.5 +
        F("completions") * 2.0 +
        F("stored_trend"),
        output_field=FloatField(),
    )

    return (
        qs.annotate(trend_score_calc=score)
        .order_by("-trend_score_calc", "-plays_24h", "-completions")
        [:limit]
    )


def trending_podcasts(limit=20):
    since_7d = now - timedelta(days=7)

    podcast_ct = ContentType.objects.get_for_model(Podcast)

    views_7dq = ObjectView.objects.filter(
        content_type=podcast_ct,
        object_id=OuterRef("pk"),
        timestamp__gte=since_7d,
    ).values("object_id").annotate(c=Count("id")).values("c")

    episode_plays_q = PlayBack.objects.filter(
        episode__podcast=OuterRef("pk"),
        last_played_at__gte=since_7d,
    ).values("episode__podcast").annotate(c=Count("id")).values("c")

    completions_q = PlayBack.objects.filter(
        episode__podcast=OuterRef("pk"),
        is_completed=True,
    ).values("episode__podcast").annotate(c=Count("id")).values("c")

    qs = Podcast.objects.annotate(
        views_7d=Coalesce(Subquery(views_7dq, output_field=IntegerField()), Value(0)),
        plays_7d=Coalesce(Subquery(episode_plays_q, output_field=IntegerField()), Value(0)),
        completions=Coalesce(Subquery(completions_q, output_field=IntegerField()), Value(0)),
    )

    score = ExpressionWrapper(
        F("views_7d") * 1.0 +
        F("plays_7d") * 2.5 +
        F("completions") * 3.0,
        output_field=FloatField(),
    )

    return qs.annotate(trend_score_calc=score).order_by("-trend_score_calc")[:limit]


def new_releases(limit=24):
    return Episode.objects.select_related('podcast').order_by('-timestamp')[:limit]


def editor_picked_episodes(limit=24):
    # If you use HandPickedPostList which stores podcasts via OrderedPodcast:
    lists = HandPickedPostList.objects.prefetch_related('podcasts')
    results = []
    for lst in lists:
        podcasts = lst.get_ordered_podcasts() if hasattr(lst, 'get_ordered_podcasts') else lst.podcasts.all()
        for p in podcasts:
            eps = p.episodes.order_by('-timestamp')[:2]
            results.extend(eps)
            if len(results) >= limit:
                return results[:limit]
    return results[:limit]


def top_playlists(limit=20):
    return PlayList.objects.annotate(item_views=Sum('items__view_count')).order_by('-featured', '-item_views',
                                                                                   '-timestamp')[:limit]


def popular_podcasts_by_category(category_slug, limit=12):
    return Podcast.objects.filter(categories__slug=category_slug).annotate(total_views=F('view_count')).order_by(
        '-total_views')[:limit]


def personalized_recommendations(user, limit=24):
    if not user or not user.is_authenticated:
        # cold-start: mix trending and new releases
        trending = list(trending_episodes(limit=12))
        new = list(new_releases(limit=limit - len(trending)))
        return trending + new

    # get recent user views
    since_90d = now - timedelta(days=90)
    viewed_episode_ids = user.object_views.filter(timestamp__gte=since_90d,
                                                  content_type=ContentType.objects.get_for_model(Episode)).values_list(
        'object_id', flat=True)

    # category affinity (from episodes or podcasts)
    cat_qs = Category.objects.filter(episodes__id__in=viewed_episode_ids).annotate(score=Count('episodes')).order_by(
        '-score')[:5]
    cat_ids = [c.id for c in cat_qs]

    qs = Episode.objects.none()
    if cat_ids:
        qs = Episode.objects.filter(Q(categories__in=cat_ids))
    # include subscribed podcasts episodes
    subscribed_pod_ids = Podcast.objects.filter(subscribers__in=[user]).values_list('id', flat=True)
    if subscribed_pod_ids:
        qs = qs | Episode.objects.filter(podcast_id__in=subscribed_pod_ids)

    qs = qs.exclude(id__in=viewed_episode_ids).order_by('-timestamp').distinct()[:limit]
    results = list(qs)
    if len(results) < limit:
        # fill with trending
        extras = [e for e in trending_episodes(limit=limit) if e.id not in {r.id for r in results}]
        results.extend(extras[:limit - len(results)])
    return results[:limit]
