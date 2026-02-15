from django.core.management.base import BaseCommand
from apps.posts.podcasts.tasks import recalc_episode_trending

class Command(BaseCommand):
    help = "Recalculate episode trend_score (calls celery task or runs inline)"
    def handle(self, *args, **options):
        recalc_episode_trending.delay()
        self.stdout.write(self.style.SUCCESS("Triggered recalc_episode_trending task"))