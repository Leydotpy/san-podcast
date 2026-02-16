from django.contrib import admin

from apps.thumbnail.models import Thumbnail


@admin.register(Thumbnail)
class ThumbnailAdmin(admin.ModelAdmin):
    class Meta:
        model = Thumbnail
        exclude = ("timestamp",)