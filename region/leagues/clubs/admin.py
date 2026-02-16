from django.contrib import admin
from apps.region.leagues.clubs.models import Team, Stadium


class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "code", "slug", "timestamp")

    class Meta:
        model = Team
        fields = ("league", "name", "short_name", "code", "image")


admin.site.register(Team, TeamAdmin)
admin.site.register(Stadium)
