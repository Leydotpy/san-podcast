from django.conf import settings
from django.db import models

from apps.category.models import Category


class UserCategoryAffinity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    score = models.FloatField(default=0.0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "category")
        indexes = [
            models.Index(fields=["user", "-score"]),
            models.Index(fields=["category"]),
        ]

    def __str__(self):
        return f"{self.user.id} -> {self.category.id}: {self.score:.3f}"
