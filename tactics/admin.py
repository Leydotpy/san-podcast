from django.contrib import admin

from .models import (
    LineUp,
    MatchLineUp,
    TeamLineUp,
    Shape,
    FormationStyle,
    Formation,
    Position
)

admin.site.register(LineUp)
admin.site.register(MatchLineUp)
admin.site.register(TeamLineUp)
admin.site.register(Shape)
admin.site.register(FormationStyle)
admin.site.register(Formation)
admin.site.register(Position)