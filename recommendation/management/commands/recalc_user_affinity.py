from django.core.management.base import BaseCommand

from apps.recommendation.tasks import recalc_user_category_affinity_postgres


class Command(BaseCommand):
    help = "Recalculate user-category affinity (sync or via Celery)"

    def handle(self, *args, **options):
        try:
            # prefer dispatching to Celery
            recalc_user_category_affinity_postgres.delay()
            self.stdout.write(self.style.SUCCESS("Triggered recalc_user_category_affinity_postgres via Celery"))
        except Exception:
            # fallback: run synchronously
            recalc_user_category_affinity_postgres()
            self.stdout.write(self.style.SUCCESS("Recalculated user-category affinity synchronously"))
