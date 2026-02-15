from django.contrib import admin


from apps.analytics.models import ObjectView


class ObjectViewAdmin(admin.ModelAdmin):
    list_display = ("id", "ip_address", "user__username", "timestamp")
    list_filter = ("id", "timestamp")
    search_fields = ("ip_address", "user__username")

    class Meta:
        model = ObjectView

admin.site.register(ObjectView, ObjectViewAdmin)
