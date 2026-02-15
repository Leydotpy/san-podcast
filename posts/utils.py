from django.utils import timezone

now = timezone.now()


def post_thumbnail_path(instance, filename):
    return f"{instance.__class__.__name__}/{instance.slug}/thumbnails/_{now.strftime('%H_%M_%S.%f')}.{filename}"


def podcast_audio_path(instance, filename):
    path = f"{instance.__class__.__name__}/{instance.slug}/audios/_{now.strftime('%H_%M_%S.%f')}.{filename}"
    return path


def highlight_video_path(instance, filename):
    path = f"{instance.__class__.__name__}/{instance.slug}/videos/_{now.strftime('%H_%M_%S.%f')}.{filename}"
    return path
