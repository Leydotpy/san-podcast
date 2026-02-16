from django.db.models.signals import m2m_changed
from django.db import models
from django.utils.translation import gettext_lazy as _


class Position(models.Model):
    class PlayerPosition(models.TextChoices):
        GK = "GK", _("Goal Keeper")
        SWK = "SWK", _("Sweeper Keeper")
        RB = "RB", _("Right Back")
        LB = "LB", _("Left Back")
        LWB = "LWB", _("Left Wing Back")
        RWB = "RWB", _("Right Wing Back")
        CBC = "CBC", _("Center Back")
        CBR = "CBR", _("Right Center Back")
        CBL = "CBL", _("Left Center Back")
        DMF = "DMF", _("Defensive MidFielder")
        CMF = "CMF", _("Central MidFielder")
        CMR = "CMR", _("Right Central MidFielder")
        CML = "CML", _("Left Central MidFielder")
        CAM = "CAM", _("Central Attacking MidFielder")
        LM = "LM", _("Left MidFielder")
        RM = "RM", _("Right MidFielder")
        RWF = "RWF", _("Right Wing Forward")
        LWF = "LWF", _("Left Wing Forward")
        SS = "SS", _("Supporting/Shadow Striker")
        ST = "ST", _("Striker")
        RST = "RST", _("Right Striker")
        LST = "LST", _("Left Striker")
        CF = "CF", _("Center Forward")

    position = models.CharField(max_length=4, choices=PlayerPosition.choices)
    top = models.PositiveIntegerField(default=0)
    left = models.PositiveIntegerField(default=0)
    bottom = models.PositiveIntegerField(default=0)
    right = models.PositiveIntegerField(default=0)
    timestamp = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    shape = models.ForeignKey("Shape", on_delete=models.CASCADE, related_name="positions")

    def __str__(self):
        return f"{self.position}, ({self.shape.style.name} - {self.shape.name})"


class LineUp(models.Model):
    player = models.ForeignKey("persons.Player", on_delete=models.CASCADE, related_name="positions_played")
    position = models.ForeignKey(Position,
                                 on_delete=models.CASCADE,
                                 related_name="lineups",
                                 )

    def __str__(self):
        return (f""
                f"{self.player.name},"
                f" ({self.position.shape.style.name} - {self.position.shape.name}),"
                f" {self.position.position}")


class Shape(models.Model):
    name = models.CharField(max_length=50)
    style = models.ForeignKey(
        "FormationStyle",
        on_delete=models.CASCADE,
        related_name="variations"
    )

    def __str__(self):
        return f"{self.name} ({self.style})"

    def check_player_position(self, position):
        return position in self.positions.all()


class FormationStyle(models.Model):
    class Style(models.TextChoices):
        FOUR_THREE_THREE = "4-3-3", _("4-3-3")
        FOUR_FOUR_TWO = "4-4-2", _("4-4-2")
        FOUR_FIVE_ONE = "4-5-1", _("4-5-1")
        FIVE_FOUR_ONE = "5-4-1", _("5-4-1")
        THREE_FIVE_TWO = "3-5-2", _("3-5-2")
        THREE_FOUR_THREE = "3-4-3", _("3-4-3")
        FOUR_TWO_FOUR = "4-2-4", _("4-2-4")
        FOUR_THREE_ONE_TWO = "4-3-1-2", _("4-3-1-2")

    name = models.CharField(max_length=50, choices=Style.choices)

    def __str__(self):
        return self.name

    def get_variations(self):
        return self.variations.all()


class Formation(models.Model):
    shape = models.ForeignKey(Shape, on_delete=models.CASCADE, related_name="formations")
    lineup = models.ManyToManyField(LineUp, blank=True)

    def __str__(self):
        return self.shape.name


class TeamLineUp(models.Model):
    team = models.ForeignKey("clubs.Team", on_delete=models.CASCADE, related_name="lineups")
    lineup = models.ForeignKey(Formation, on_delete=models.CASCADE)
    manager = models.ForeignKey("persons.Staff", on_delete=models.SET_NULL, null=True, blank=True)
    objects = models.Manager()

    def __str__(self):
        return self.team.name


class MatchLineUp(models.Model):
    match = models.OneToOneField("match.Match", on_delete=models.CASCADE, related_name="lineups")
    home_lineup = models.ForeignKey(TeamLineUp, on_delete=models.CASCADE, related_name="home_lineups")
    away_lineup = models.ForeignKey(TeamLineUp, on_delete=models.CASCADE, related_name="away_lineups")
    objects = models.Manager()

    def __str__(self):
        return str(self.match)
