import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from core.compat import get_user_model
from utils.utils import get_client_ip

User = get_user_model()


# 1. The Smart "Log" Model
# This table acts as your raw dataset for Machine Learning later.
class ObjectView(models.Model):
    # Who viewed it?
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='object_views'
    )
    # If user is not logged in, we track IP to prevent spamming views
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # What did they view? (Generic Relation)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    # When?
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Object View"
        verbose_name_plural = "Object Views"
        ordering = ['-timestamp']
        indexes = [
            # Index for fast ML data extraction (User history)
            models.Index(fields=['user', 'content_type']),
            # Index for checking recent views (Spam protection)
            models.Index(fields=['content_type', 'object_id', 'ip_address', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.user if self.user else self.ip_address} viewed {self.content_object}"


class AnalyticsQueryset(models.QuerySet):
    ...


class AnalyticsManager(models.Manager):

    def get_queryset(self):
        return AnalyticsQueryset(self.model, using=self._db)


class AbstractAnalytics(models.Model):
    """
    Abstract model to handle generic analytics and relationships
    across different domains (Regions, Competitions, etc.).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, db_index=True)
    countries = models.ManyToManyField("region.Country", blank=True)
    competitions = models.ManyToManyField("leagues.League", blank=True)
    regions = models.ManyToManyField("region.Region", blank=True)
    teams = models.ManyToManyField("clubs.Team", blank=True)
    players = models.ManyToManyField("persons.Player", blank=True)
    matches = models.ManyToManyField("match.Match", blank=True)

    # Renamed for clarity, but kept original field name for DB compatibility
    subscribers = models.ManyToManyField(User, blank=True)

    # Reverse relationship to access the detailed logs if needed
    view_logs = GenericRelation(ObjectView)

    # DENORMALIZATION:
    # We keep a running total here. This makes "Most Popular" queries instant.
    # No need to count the view_logs table every time.
    view_count = models.PositiveIntegerField(default=0)

    analytics = AnalyticsManager()  # Assuming this exists elsewhere

    class Meta:
        abstract = True

    def toggle_subscription(self, user) -> bool:
        """Toggles subscription status. Returns True if subscribed, False if unsubscribed."""
        if self.subscribers.filter(pk=user.pk).exists():
            self.subscribers.remove(user)
            return False
        self.subscribers.add(user)
        return True

    def record_view(self, request):
        """
        Smart view recording:
        1. Checks if this user/IP has viewed this item recently (e.g., last 10 mins).
        2. If not, creates a log entry and increments the counter.
        """
        user = request.user if request.user.is_authenticated else None
        ip = get_client_ip(request)

        # Define a "cooldown" period (e.g., 10 minutes)
        # We don't want to count every single refresh as a new view for ML or Popularity
        cooldown_time = timezone.now() - timedelta(minutes=10)

        # Check if a view exists in the cooldown period
        existing_view = ObjectView.objects.filter(
            content_type=ContentType.objects.get_for_model(self),
            object_id=self.id,
            timestamp__gte=cooldown_time
        )

        if user:
            is_duplicate = existing_view.filter(user=user).exists()
        else:
            is_duplicate = existing_view.filter(ip_address=ip).exists()

        if not is_duplicate:
            # 1. Create the Log (For ML)
            ObjectView.objects.create(
                user=user,
                ip_address=ip,
                content_object=self
            )

            # 2. Increment the Counter (For Popularity Sorting)
            # using F() expression avoids race conditions
            self.view_count = models.F('view_count') + 1
            self.save(update_fields=['view_count'])

            # Refresh to get the integer value back from the DB expression
            self.refresh_from_db()
            return True

        return False

    def user_has_subscribed(self, user) -> bool:
        if not user or not user.is_authenticated:
            return False
        return self.subscribers.filter(pk=user.pk).exists()
