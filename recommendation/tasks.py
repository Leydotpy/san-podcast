from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import connection, transaction
from django.utils import timezone

from apps.posts.podcasts.models import Podcast, Episode, PlayBack
from apps.recommendation.models import UserCategoryAffinity
from apps.recommendation.services.recommend import aggregated_playback_scores, aggregated_podcast_view_scores

User = get_user_model()

# Tunable parameters
LOOKBACK_DAYS = getattr(settings, "RECOMMEND_LOOKBACK_DAYS", 90)
TAU_DAYS = getattr(settings, "RECOMMEND_DECAY_TAU_DAYS", 30.0)  # tau for exponential decay
PLAY_WEIGHT = getattr(settings, "RECOMMEND_PLAY_WEIGHT", 1.0)
COMPLETION_WEIGHT = getattr(settings, "RECOMMEND_COMPLETION_WEIGHT", 3.0)
PODCAST_VIEW_WEIGHT = getattr(settings, "RECOMMEND_PODCAST_VIEW_WEIGHT", 0.5)


@shared_task(bind=True)
def recalc_user_category_affinity_postgres(self, lookback_days: int = LOOKBACK_DAYS) -> dict:
    """
    Batched affinity computation using Postgres SQL (one aggregation per source),
    exponential decay via EXP(), and bulk upsert into UserCategoryAffinity.

    This:
      - aggregates PlayBack -> episode_categories
      - aggregates Podcast ObjectView -> podcast_categories
      - merges both sources and upserts into recommendation_usercategoryaffinity

    Requirements:
      - PostgreSQL
      - Podcast/Episode categories through tables available
      - ObjectView table name available via AbstractAnalytics
    """

    if connection.vendor != "postgresql":
        raise RuntimeError("This task requires PostgreSQL (connection.vendor != 'postgresql').")

    now = timezone.now()
    lookback_interval = f"{lookback_days} days"
    tau_seconds = TAU_DAYS * 24.0 * 3600.0  # tau in seconds used in EXP()

    # table names programmatically (safe if you renamed db_table)
    playback_table = PlayBack._meta.db_table
    episode_table = Episode._meta.db_table
    episode_categories_table = Episode.categories.through._meta.db_table
    podcast_table = Podcast._meta.db_table
    podcast_categories_table = Podcast.categories.through._meta.db_table
    objectview_model = settings.AUTH_USER_MODEL  # not used directly here
    objectview_table = None

    # ObjectView model may live in another app; derive its table from ContentType lookup
    # but easiest is to import your ObjectView model path. We'll try to import by common path.
    try:
        # You used ObjectView directly in models — get model class by name:
        from django.apps import apps
        ObjectView = apps.get_model("yourapp.ObjectView")  # CHANGE THIS if your ObjectView app_label != 'yourapp'
        objectview_table = ObjectView._meta.db_table
    except Exception:
        # fallback: try common name 'analytics.ObjectView' (adjust to your project)
        try:
            ObjectView = apps.get_model("analytics.ObjectView")
            objectview_table = ObjectView._meta.db_table
        except Exception:
            # If we cannot locate ObjectView, raise explicit error to guide you
            raise RuntimeError(
                "Cannot locate ObjectView model programmatically. "
                "Edit recommendation/tasks.py and set ObjectView import to your app model path."
            )

    user_cat_table = UserCategoryAffinity._meta.db_table

    # content_type id for Podcast, used to filter ObjectView rows
    podcast_ct_id = ContentType.objects.get_for_model(Podcast).id

    # Build SQL: create a temp table tmp_affinities(user_id, category_id, score)
    # 1) Playback aggregates: join playback_table -> episode_categories_table
    # 2) Podcast view aggregates: join objectview_table -> podcast_categories_table
    # Use exponential decay: weight * EXP( - EXTRACT(EPOCH FROM (NOW() - timestamp)) / tau_seconds )
    # Then merge (UNION ALL) and aggregate by (user_id, category_id)
    sql = f"""
    BEGIN;

    -- 1) create temp table with aggregated scores from both sources
    CREATE TEMP TABLE tmp_affinities ON COMMIT DROP AS
    WITH play_agg AS (
        SELECT
            pb.user_id::bigint AS user_id,
            ec.category_id::bigint AS category_id,
            SUM(
                (CASE WHEN pb.is_completed THEN %s ELSE %s END)
                * EXP( - EXTRACT(EPOCH FROM (NOW() - pb.last_played_at)) / %s )
            ) AS score
        FROM {playback_table} pb
        JOIN {episode_categories_table} ec ON ec.episode_id = pb.episode_id
        WHERE pb.last_played_at >= NOW() - INTERVAL %s
        GROUP BY pb.user_id, ec.category_id
    ),
    view_agg AS (
        SELECT
            ov.user_id::bigint AS user_id,
            pc.category_id::bigint AS category_id,
            SUM(
                %s
                * EXP( - EXTRACT(EPOCH FROM (NOW() - ov.timestamp)) / %s )
            ) AS score
        FROM {objectview_table} ov
        JOIN {podcast_categories_table} pc ON pc.podcast_id = ov.object_id
        WHERE ov.content_type_id = %s
          AND ov.timestamp >= NOW() - INTERVAL %s
        GROUP BY ov.user_id, pc.category_id
    )
    SELECT user_id, category_id, SUM(score) AS score
    FROM (
      SELECT user_id, category_id, score FROM play_agg
      UNION ALL
      SELECT user_id, category_id, score FROM view_agg
    ) t
    GROUP BY user_id, category_id
    ;

    -- 2) prepare affected users list
    CREATE TEMP TABLE tmp_affected_users ON COMMIT DROP AS
    SELECT DISTINCT user_id FROM tmp_affinities;

    -- 3) delete existing affinities for affected users (clean slate)
    DELETE FROM {user_cat_table}
    WHERE user_id IN (SELECT user_id FROM tmp_affected_users);

    -- 4) insert new affinities (upsert, but we already deleted; keep ON CONFLICT for safety)
    INSERT INTO {user_cat_table} (user_id, category_id, score)
    SELECT user_id, category_id, score FROM tmp_affinities
    ON CONFLICT (user_id, category_id) DO UPDATE SET score = EXCLUDED.score;

    COMMIT;
    """

    params = [
        # play_agg CASE weights
        COMPLETION_WEIGHT,  # when pb.is_completed THEN COMPLETION_WEIGHT
        PLAY_WEIGHT,  # else PLAY_WEIGHT
        tau_seconds,  # tau in seconds for playback
        lookback_interval,  # play WHERE ... INTERVAL ...
        # view_agg constants
        PODCAST_VIEW_WEIGHT,  # podcast view base weight
        tau_seconds,  # tau for view decay
        podcast_ct_id,  # content_type_id for Podcast
        lookback_interval,  # view WHERE ... INTERVAL ...
    ]

    # run SQL
    with connection.cursor() as cur:
        cur.execute(sql, params)

    # return quick metrics (count of rows inserted)
    with connection.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {user_cat_table};")
        total = cur.fetchone()[0]

    return {"status": "ok", "total_affinities": total}

