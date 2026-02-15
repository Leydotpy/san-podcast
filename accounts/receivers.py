from django.dispatch import receiver
from apps.posts.podcasts.signals import podcast_viewed
from .history import UserHistoryManager

@receiver(podcast_viewed)
def receive_podcast_viewed(sender, podcast, user, request, response, **kwargs):
    return UserHistoryManager.update(podcast, request, response)