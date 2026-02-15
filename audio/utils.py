import os
import logging
import shutil
import tempfile
import time
from typing import List

import ffmpeg
from django.core.files.base import ContentFile
from django.core.files import File as DjangoFile
from django.core.files.storage import default_storage
from django.db import transaction

from .models import Audio
from .subtitle import export_srt, export_vtt
from ..chapters.models import Chapter
from ..chapters.utils import build_chapters, summarize
from ..transcription.managed import transcribe_with_openai, transcribe_with_google_gcs
from ..transcription.metrics import AUDIO_DURATION_SECONDS, TRANSCRIPTIONS_FAILED, TRANSCRIPTIONS_TOTAL, \
    TRANSCRIPTION_DURATION
from ..transcription.models import Transcription, TranscriptionBillingRecord
from ..transcription.pricing import charge_user_quota, estimate_cost
from ..utils import detect_master_audio_info, AUDIO_PRESETS, create_hls_audio, transcode_to_variant
from ...posts.podcasts.models import Summary

logger = logging.getLogger(__name__)


def _safe_storage_key(base: str, *parts: str) -> str:
    """
    Build a stable storage key under base using provided parts.
    `base` should already be safe (slug or id).
    """
    safe_parts = [p.strip("/ ") for p in parts]
    return "/".join([base, *safe_parts])


def generate_variants(master_local_path: str, episode, storage_base: str) -> List[Audio]:
    """
    Create low/medium/high mp3 variants from master and persist them as Audio rows.
    Returns the list of Audio variants created/updated.
    """
    # probe to get bitrate (to decide which variants to produce)
    info = detect_master_audio_info(master_local_path)
    master_bitrate = info.get("bitrate_kbps") or 0

    if master_bitrate >= AUDIO_PRESETS["high"]["kbps"]:
        allowed = ["low", "medium", "high"]
    elif master_bitrate >= AUDIO_PRESETS["medium"]["kbps"]:
        allowed = ["low", "medium"]
    else:
        allowed = ["low"]

    created_variants = []
    tmpdir = tempfile.mkdtemp(prefix="variants-")
    try:
        for q in allowed:
            preset = AUDIO_PRESETS[q]
            out_local = os.path.join(tmpdir, f"variant_{q}.mp3")
            try:
                transcode_to_variant(master_local_path, out_local, preset)
            except Exception:
                logger.exception("transcode_to_variant failed for episode=%s quality=%s", episode.pk, q)
                raise

            size = os.path.getsize(out_local)
            filename = f"episodes/{storage_base}/variants/{q}.mp3"  # key in storage

            # upsert Audio variant model
            variant, _ = Audio.objects.update_or_create(
                episode=episode,
                quality=q,
                defaults={
                    "name": episode.title or f"{episode.pk}-{q}",
                    "codec": "mp3",
                    "sample_rate": preset["sample_rate"],
                    "size_bytes": size,
                    "bitrate": preset["kbps"],
                },
            )

            # delete existing file if any, then save new file via Django storage
            try:
                if variant.file and variant.file.name:
                    try:
                        variant.file.delete(save=False)
                    except Exception:
                        logger.debug("Could not delete old variant file for episode=%s q=%s", episode.pk, q)
                with open(out_local, "rb") as fh:
                    django_file = DjangoFile(fh, name=os.path.basename(filename))
                    variant.file.save(filename, django_file, save=True)  # uploads via default_storage
                    # update metadata after save (sometimes storage updates path)
                    variant.save(update_fields=["name", "codec", "sample_rate", "size_bytes", "bitrate"])
            except Exception:
                logger.exception("Failed saving variant file to storage for episode=%s q=%s", episode.pk, q)
                raise

            created_variants.append(variant)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return created_variants


def generate_hls_stream(master_local_path: str, episode, storage_base: str, preset_key: str = "medium", segment_time: int = 10) -> Audio:
    """
    Create HLS (audio-only) locally then upload playlist + segments to storage.
    Creates or updates an HLSStream DB row and returns it.
    """
    tmpdir = tempfile.mkdtemp(prefix="hls-")
    try:
        hls_dir = os.path.join(tmpdir, "hls")
        os.makedirs(hls_dir, exist_ok=True)

        preset = AUDIO_PRESETS.get(preset_key)
        if preset is None:
            raise ValueError(f"unknown preset {preset_key}")

        # create HLS files locally (index.m3u8 + segments)
        create_hls_audio(master_local_path, hls_dir, preset, segment_time=segment_time)

        # upload all files under a stable prefix
        prefix = f"episodes/hls/{storage_base}/{preset_key}"
        playlist_local = os.path.join(hls_dir, "index.m3u8")
        if not os.path.exists(playlist_local):
            # some create_hls_audio implementations create different playlist names; find first .m3u8
            for f in os.listdir(hls_dir):
                if f.endswith(".m3u8"):
                    playlist_local = os.path.join(hls_dir, f)
                    break

        uploaded_playlist_key = None
        for root, _, files in os.walk(hls_dir):
            for fname in files:
                local_path = os.path.join(root, fname)
                relative_name = os.path.relpath(local_path, hls_dir)
                key = f"{prefix}/{relative_name}"
                # delete existing if present
                try:
                    if default_storage.exists(key):
                        default_storage.delete(key)
                except Exception:
                    logger.debug("could not delete prior hls key %s", key)
                # read and save
                with open(local_path, "rb") as fh:
                    # using ContentFile to ensure binary-safe
                    default_storage.save(key, ContentFile(fh.read()))
                if local_path == playlist_local:
                    uploaded_playlist_key = key

        if uploaded_playlist_key is None:
            raise RuntimeError("HLS playlist not uploaded - aborting")

        # create/update HLSStream row
        hls_row, _ = Audio.objects.update_or_create(
            episode=episode,
            quality=preset_key,
            defaults={
                "file": uploaded_playlist_key,  # this assigns the storage key to FileField
                "prefix": prefix,
            }
        )
        # If storage backend didn't set FileField properly via name, set it explicitly
        # (Some storages require calling .save on FileField; since we already saved via default_storage,
        # assign the name and save)
        hls_row.file.name = uploaded_playlist_key
        hls_row.save(update_fields=["file", "prefix",])
        return hls_row
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def generate_preview_clip(master_local_path: str, episode, storage_base: str, window_seconds: int = 30):
    """
    Simplified preview generator: takes the first non-silent window or start=0 fallback.
    Saves an Audio row with quality 'preview' and returns it.
    """
    tmpdir = tempfile.mkdtemp(prefix="preview-")
    try:
        # simple approach: start at 0 (you can replace with VAD or loudness detection)
        out_local = os.path.join(tmpdir, "preview.mp3")
        (
            ffmpeg
            .input(master_local_path, ss=0, t=window_seconds)
            .output(out_local, acodec="libmp3lame", audio_bitrate="64k", ar=22050, ac=2)
            .overwrite_output()
            .run(quiet=True)
        )

        filename = f"episodes/{storage_base}/preview/preview.mp3"
        preview, _ = Audio.objects.update_or_create(
            episode=episode,
            quality="preview",
            defaults={"name": f"{episode.title} (preview)", "codec": "mp3"},
        )

        # delete existing preview file if present
        try:
            if preview.file and preview.file.name:
                preview.file.delete(save=False)
        except Exception:
            logger.debug("failed to delete old preview file")

        with open(out_local, "rb") as fh:
            preview.file.save(filename, DjangoFile(fh), save=True)
            preview.save(update_fields=["name", "codec"])
        return preview
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def generate_transcription(
        tmpdir,
        master_local,
        episode,
        storage_base,
        user_id,
        provider,
        provider_options,
        generate_chapters,
        generate_summary,
):
    provider_options = provider_options or {}
    start_time = time.monotonic()
    # convert to wav for ASR
    wav_path = os.path.join(tmpdir, "master_for_asr.wav")
    ffmpeg.input(master_local).output(wav_path, ac=1, ar="16000", format="wav",
                                      acodec="pcm_s16le").overwrite_output().run(quiet=True)

    try:
        probe = ffmpeg.probe(wav_path)
        duration = float(probe["format"].get("duration", 0))
    except Exception:
        duration = 0.0
    AUDIO_DURATION_SECONDS.observe(duration)

    # optional quota check
    if user_id:
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.get(pk=user_id)
        if not charge_user_quota(user, int(duration)):
            raise Exception("Transcription quota exceeded")

    # call provider
    try:
        if provider.lower() == "openai":
            result = transcribe_with_openai(wav_path, model=provider_options.get("model"))
        elif provider.lower() == "google":
            gcs_bucket = provider_options.get("gcs_bucket") or os.getenv("GCS_TEMP_BUCKET")
            result = transcribe_with_google_gcs(wav_path, gcs_bucket, provider_options.get("gcs_prefix", "tmp"),
                                                language_code=provider_options.get("language_code", "en-US"))
        else:
            raise ValueError("Unknown provider")
    except Exception as exc:
        TRANSCRIPTIONS_FAILED.labels(provider=provider, reason=exc.__class__.__name__).inc()
        logger.exception("Transcription provider failed for %s: %s", episode.id, exc)
        raise

    text = result.get("text", "") if isinstance(result, dict) else str(result)
    segments = result.get("segments") if isinstance(result, dict) else []
    language = result.get("language") if isinstance(result, dict) else provider_options.get("language_code",
                                                                                            "en")
    cost = estimate_cost(provider, int(duration))

    # prepare SRT/VTT
    srt_content = export_srt(segments or [])
    vtt_content = export_vtt(segments or [])

    srt_key = f"transcripts/{storage_base}/{episode.id}.srt"
    vtt_key = f"transcripts/{storage_base}/{episode.id}.vtt"
    uploaded_keys = []

    # upload subtitles first
    try:
        if srt_content:
            if default_storage.exists(srt_key):
                default_storage.delete(srt_key)
            default_storage.save(srt_key, ContentFile(srt_content.encode("utf-8")))
            uploaded_keys.append(srt_key)
        if vtt_content:
            if default_storage.exists(vtt_key):
                default_storage.delete(vtt_key)
            default_storage.save(vtt_key, ContentFile(vtt_content.encode("utf-8")))
            uploaded_keys.append(vtt_key)
    except Exception as exc:
        # cleanup partial uploads
        for k in uploaded_keys:
            try:
                if default_storage.exists(k):
                    default_storage.delete(k)
            except Exception:
                logger.warning("Failed to delete partial subtitle key %s", k)
        logger.exception("Failed to upload subtitles for episode=%s: %s", episode.id, exc)
        raise

    # persist transcription + billing
    try:
        with transaction.atomic():
            transcription, _ = Transcription.objects.update_or_create(
                episode=episode,
                defaults={
                    "language": language,
                    "text": text or "",
                    "segments": segments or [],
                    "provider": provider,
                    "audio_duration_seconds": int(duration),
                    "cost_usd": cost,
                },
            )
            if srt_content:
                transcription.srt_file.name = srt_key
            if vtt_content:
                transcription.vtt_file.name = vtt_key
            transcription.save(update_fields=["srt_file", "vtt_file"] if (srt_content or vtt_content) else [])
            TranscriptionBillingRecord.objects.create(episode=episode, provider=provider,
                                                      audio_seconds=int(duration), cost_usd=cost)
    except Exception:
        # cleanup uploaded subtitle keys on db failure
        for k in uploaded_keys:
            try:
                if default_storage.exists(k):
                    default_storage.delete(k)
            except Exception:
                logger.warning("Failed to delete subtitle key %s while rolling back", k)
        raise

    TRANSCRIPTIONS_TOTAL.labels(provider=provider).inc()
    elapsed = time.monotonic() - start_time
    TRANSCRIPTION_DURATION.labels(provider=provider).observe(elapsed)

    if generate_chapters and segments:
        # build chapters from segments and save
        chapters = build_chapters(segments)
        Chapter.objects.filter(episode=episode).delete()
        Chapter.objects.bulk_create(
            [Chapter(episode=episode, title=c["title"], start_time=c["start_time"]) for c in chapters])

    if generate_summary:
        try:
            summary_text = summarize(text[:20000])
        except Exception:
            logger.exception("Summary generation failed for episode=%s", episode.id)
            summary_text = ""
        Summary.objects.update_or_create(episode=episode, defaults={"summary_text": summary_text or "",
                                                                    "model": provider_options.get(
                                                                        "summary_model", "gpt-4.1-mini")})