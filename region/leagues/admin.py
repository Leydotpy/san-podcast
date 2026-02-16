from django.contrib import admin
from apps.region.leagues.models import League, Campaign


class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "region", "short_name", "code", "slug")

    class Meta:
        model = League
        fields = ("region", "name", "short_name", "code", "image")


admin.site.register(League, LeagueAdmin)
admin.site.register(Campaign)
