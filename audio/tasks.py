import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime

from celery import Task
from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from apps.media.audio.models import Audio
from apps.media.storage import generate_cloudfront_signed_cookies
from apps.media.utils import detect_master_audio_info
from .utils import generate_hls_stream, generate_preview_clip, generate_variants, generate_transcription

logger = logging.getLogger(__name__)


class BaseTaskWithRetry(Task):
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 5, "countdown": 10}


@shared_task(bind=True, acks_late=True)
def rotate_cloud_front_cookies():
    """
    Iterate HLSStream rows and ensure cached CloudFront signed cookies exist for each prefix.
    This pre-warms/rotates cookies so the API endpoint can quickly return them without
    generating them on-demand repeatedly.
    """
    domain = getattr(settings, "CLOUDFRONT_DOMAIN", None)
    key_pair_id = getattr(settings, "CLOUDFRONT_KEY_PAIR_ID", None)
    private_key_pem = getattr(settings, "CLOUDFRONT_PRIVATE_KEY", None)
    cookie_ttl = getattr(settings, "CLOUDFRONT_COOKIE_TTL", 900)
    cache_margin = getattr(settings, "CLOUDFRONT_SIGN_CACHE_TIMEOUT_MARGIN", 60)

    if not domain or not key_pair_id or not private_key_pem:
        logger.warning("CloudFront signing not configured; rotate_cloudfront_cookies will not run")
        return

    streams = Audio.objects.filter(quality=Audio.Quality.HLS).values("id", "prefix")
    for s in streams:
        hls_id = s["id"]
        prefix = s["prefix"]
        resource_url = f"https://{domain}/{prefix}/*"
        cache_key = f"cf_signed_cookies:{hls_id}"
        cached = cache.get(cache_key)
        needs_refresh = True
        if cached:
            expires_at = cached.get("expires_at")
            if expires_at and expires_at > datetime.utcnow():
                # If expiry is not too close, skip
                remaining = (expires_at - datetime.utcnow()).total_seconds()
                if remaining > cache_margin:
                    needs_refresh = False

        if not needs_refresh:
            continue

        try:
            signed = generate_cloudfront_signed_cookies(resource_url, key_pair_id, private_key_pem,
                                                        expires_in_seconds=cookie_ttl)
            cookies = signed.get("cookies")
            expires_at = signed.get("expires_at")
            ttl_seconds = int((expires_at - datetime.utcnow()).total_seconds()) - cache_margin
            if ttl_seconds < 1:
                ttl_seconds = max(1, int(cookie_ttl / 2))
            cache.set(cache_key, {"cookies": cookies, "expires_at": expires_at}, timeout=ttl_seconds)
            logger.info("Rotated CloudFront cookies for hls_id=%s prefix=%s", hls_id, prefix)
        except Exception as exc:
            logger.exception("Failed rotating CloudFront cookies for hls_id=%s prefix=%s: %s", hls_id, prefix, exc)


@shared_task
def process_audio(
        audio_id: str,
        user_id: int | None = None,
        provider: str = "openai",
        provider_options: dict | None = None,
        *,
        generate_variants_flag: bool = True,
        generate_hls_flag: bool = True,
        generate_preview_flag: bool = True,
        generate_transcription_flag: bool = True,
        generate_chapters_flag: bool = True,
        generate_summary_flag: bool = True,
):
    provider_options = provider_options or {}
    tmpdir = tempfile.mkdtemp(prefix=f"ep-job-{uuid.uuid4()}-")

    try:
        audio = Audio.objects.select_related("episode").get(id=audio_id)
    except Audio.DoesNotExist:
        logger.exception(f"Audio {audio_id} not found")
        shutil.rmtree(tmpdir, ignore_errors=True)
        return None

    episode = audio.episode
    storage_base = episode.slug

    try:
        # download master locally
        master_local = os.path.join(tmpdir, "master")
        with open(master_local, "wb") as fh:
            for chunk in audio.file.chunks():
                fh.write(chunk)

        # Update master metadata
        info = detect_master_audio_info(master_local)
        audio.name = info.get("title")
        audio.bitrate = info.get("bitrate_kbps")
        audio.sample_rate = info.get("sample_rate")
        audio.codec = info.get("codec")
        audio.duration = int(info.get("duration", 0))
        audio.save(update_fields=["name", "bitrate", "sample_rate", "codec", "duration"])

        # Variants
        if generate_variants_flag:
            generate_variants(master_local, episode, storage_base)

        if generate_hls_flag:
            # create hls stream (uploads to storage and returns HLSStream)
            generate_hls_stream(master_local, episode, storage_base, preset_key="medium", segment_time=10)

        # Preview
        if generate_preview_flag:
            generate_preview_clip(master_local, episode, storage_base)

        # Transcription (optional)
        if generate_transcription_flag:
            try:
                generate_transcription(
                    tmpdir=tmpdir,
                    user_id=user_id,
                    provider=provider,
                    provider_options=provider_options,
                    master_local=master_local,
                    episode=episode,
                    storage_base=storage_base,
                    generate_chapters=generate_chapters_flag,
                    generate_summary=generate_summary_flag,
                )
            except Exception as e:
                logger.exception("Transcription generation failed", exc_info=e)
                pass
        # done
        # If HLSStream exists we already created/updated it in generate_hls_stream
        audio.processed = True
        audio.save(update_fields=["processed"])
        return audio.id
    finally:
        # always cleanup tempdir
        shutil.rmtree(tmpdir, ignore_errors=True)
