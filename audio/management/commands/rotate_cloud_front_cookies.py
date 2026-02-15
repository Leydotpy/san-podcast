from django.core.management.base import BaseCommand
from apps.media.audio.tasks import rotate_cloud_front_cookies

class Command(BaseCommand):
    help = "Rotate / pre-generate CloudFront signed cookies for all HLSStream prefixes and cache them."

    def handle(self, *args, **options):
        rotate_cloud_front_cookies.delay()
        self.stdout.write(self.style.SUCCESS("Triggered rotate_cloudfront_cookies Celery task"))
