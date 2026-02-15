from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PlayBack
from apps.recommendation.cache import invalidate_user_recommendations


@receiver(post_save, sender=PlayBack)
def invalidate_user_recommendations_receiver(sender, instance, **kwargs):
    user = instance.user
    if not user:
        return
    invalidate_user_recommendations(user.id)


# from profiles.models import Profile
# @receiver(post_save, sender=Profile)
# def on_subscription_change(sender, instance, **kwargs):
#     # instance.user or instance.id depending on your Profile setup
#     user = getattr(instance, "user", None)
#     if user:
#         invalidate_user_recommendations(user.id)