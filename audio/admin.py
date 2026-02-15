from django.contrib import admin

from .models import Audio


class AudioAdmin(admin.ModelAdmin):
    list_display = ('id','name', 'quality', 'codec', 'master', 'bitrate', 'episode__title', 'sample_rate', 'size_bytes')
    search_fields = ('name', 'quality', 'episode__title', 'sample_rate', 'size_bytes')
    list_filter = ('codec', 'quality', 'sample_rate', 'size_bytes')
    list_display_links = ('name', 'id')

    def get_readonly_fields(self, request, obj = Audio):
        if obj and not obj.master:
            return obj._meta.get_fields()
        return "duration", "size_bytes", "sample_rate", "bitrate", "codec", "quality", "processed"

    class Meta:
        model = Audio

admin.site.register(Audio, AudioAdmin)