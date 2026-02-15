from django.contrib import admin
from apps.match.models import (Match, Booking,
                               Shot, Substitution, SetPiece,
                               Possession, TeamPossession,
                               Foul, Event, Highlight, Goal
                               )


class MatchAdmin(admin.ModelAdmin):
    class Meta:
        model = Match
        fields = "__all__"


admin.site.register(Match, MatchAdmin)
admin.site.register(Booking)
admin.site.register(Shot)
admin.site.register(Substitution)
admin.site.register(SetPiece)
admin.site.register(Possession)
admin.site.register(TeamPossession)
admin.site.register(Foul)
admin.site.register(Highlight)
admin.site.register(Goal)
admin.site.register(Event)
