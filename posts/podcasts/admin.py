from django.contrib import admin
from apps.posts.podcasts.models import Podcast, Episode
from apps.media.audio.models import Audio


class AudioInline(admin.StackedInline):
    model = Audio
    can_delete = True
    extra = 0
    readonly_fields =  ("duration", "size_bytes", "sample_rate", "bitrate", "codec", "quality", "processed")



class PodcastAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'subtitle', 'structure', 'slug', 'timestamp')
    list_display_links = ('id', 'title')
    # inlines = [ImageInline]

    class Meta:
        model = Podcast


class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'podcast__title', 'title', 'subtitle', 'hosts', 'timestamp')
    list_display_links = ('id', 'title')
    list_filter = ('id', 'timestamp', 'title')
    readonly_fields = ('id', 'slug', 'timestamp', 'updated', 'trend_score')
    inlines = [AudioInline]

    class Meta:
        model = Episode


admin.site.register(Episode, EpisodeAdmin)
admin.site.register(Podcast, PodcastAdmin)
