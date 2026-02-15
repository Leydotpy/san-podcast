from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


from apps.region.leagues.clubs.models import Team, Stadium
from apps.media.video.models import Video


class Shot(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    player = models.ForeignKey("persons.Player", on_delete=models.SET_NULL, null=True, related_name="shots")
    is_on_target = models.BooleanField(default=False)
    minute = models.TimeField(auto_now_add=True)

    def __str__(self):
        return self.player.name


class Foul(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    player = models.ForeignKey("persons.Player", on_delete=models.SET_NULL, null=True)
    minute = models.TimeField(auto_now_add=True)

    def __str__(self):
        return self.player.name


class SetPiece(models.Model):
    class Type(models.TextChoices):
        CORNER_KICK = "corner_kick", _("Corner Kick")
        FREE_KICK = "free_kick", _("Free Kick")

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    type = models.CharField(max_length=120, choices=Type.choices)
    minute = models.TimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} for {self.team}"


class Goal(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    scorer = models.ForeignKey("persons.Player", on_delete=models.CASCADE, related_name="goals")
    assist = models.ForeignKey("persons.Player",
                               on_delete=models.SET_NULL, null=True, blank=True, related_name="assists")
    scorer_experimental = models.ForeignKey(
        "tactics.Lineup",
        on_delete=models.CASCADE,
        related_name="goals_experimental"
    )
    assist_experimental = models.ForeignKey(
        "tactics.Lineup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assists_experimental"
    )
    minute = models.TimeField(auto_now_add=True)
    is_own_goal = models.BooleanField(default=False)

    objects = models.Manager()

    def __str__(self):
        return "goal by {}".format(self.scorer)

    def clean(self):
        super().clean()
        assert self.scorer.team == self.assist.team, \
            ValidationError("Goal scorer and assist provider must be team mates")


class TeamPossession(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="team_possession")
    possession = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.team.name


class Possession(models.Model):
    home = models.ForeignKey(TeamPossession, on_delete=models.CASCADE, related_name="home_possession")
    away = models.ForeignKey(TeamPossession, on_delete=models.CASCADE, related_name="away_possession")

    def __str__(self):
        return f"{self.home.possession}% - {self.away.possession}%"


class MatchManager(models.Manager):
    pass


class Match(models.Model):
    home_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="home_matches")
    away_team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="away_matches")
    venue = models.ForeignKey(Stadium, on_delete=models.SET_NULL, null=True)
    day = models.IntegerField(default=1, verbose_name=_("Match Day"))
    date = models.DateTimeField()
    competition = models.ForeignKey("leagues.League", on_delete=models.CASCADE, related_name="games")
    campaign = models.ForeignKey("leagues.Campaign", on_delete=models.CASCADE, related_name="matches")

    objects = MatchManager()

    def __str__(self):
        return "{} v {}".format(self.home_team, self.away_team)

    def get_event(self):
        return self.event

    @property
    def home_scores_count(self):
        return self.get_event().goals.filter(team=self.home_team).count()

    @property
    def away_scores_count(self):
        return self.get_event().goals.filter(team=self.away_team).count()

    class Meta:
        verbose_name = _("Match")
        verbose_name_plural = _("Matches")


class Highlight(Video):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="highlights")
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    def __str__(self):
        return str(self.match)


class Substitution(models.Model):
    class Reason(models.TextChoices):
        INJURY = "injury", _("Injury")
        TACTICAL = "tactical", _("Tactical")

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="substitutions")
    player_out = models.ForeignKey("persons.Player", on_delete=models.CASCADE, related_name="sub_outs")
    player_in = models.ForeignKey("persons.Player", on_delete=models.CASCADE, related_name="sub_ins")
    minute = models.PositiveIntegerField(default=0)
    reason = models.CharField(max_length=120, choices=Reason.choices, default=Reason.TACTICAL)

    objects = models.Manager()

    def __str__(self):
        return self.team


class Booking(models.Model):
    class Type(models.TextChoices):
        YELLOW = "yellow", _("Yellow")
        RED = "red", _("Red")

    player = models.ForeignKey("persons.Player", on_delete=models.CASCADE, related_name="bookings")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="bookings")
    booking = models.CharField(max_length=10, choices=Type.choices, default=Type.YELLOW)
    is_straight_red = models.BooleanField(default=False)
    is_second_yellow = models.BooleanField(default=False)
    minute = models.PositiveIntegerField(default=0)

    objects = models.Manager()

    def __str__(self):
        return self.player


class Event(models.Model):
    bookings = models.ManyToManyField(Booking, blank=True)
    match = models.OneToOneField(Match, on_delete=models.CASCADE)
    substitutions = models.ManyToManyField(Substitution, blank=True)
    possession = models.OneToOneField(Possession, on_delete=models.CASCADE)
    shots = models.ManyToManyField(Shot, blank=True)
    set_piece = models.ManyToManyField(SetPiece, blank=True)
    fouls = models.ManyToManyField(
        Foul,
        through="FoulEvent",
        through_fields=("event", "foul"),
        blank=True
    )
    goals = models.ManyToManyField(
        Goal,
        through="GoalEvent",
        through_fields=("event", "goal"),
        blank=True
    )

    def __str__(self):
        return str(self.match)

    def get_goals_by_team(self, team):
        return self.goals.filter(team=team)

    def get_fouls_by_team(self, team):
        return self.fouls.filter(team=team)

    def get_shots_by_team(self, team):
        return self.shots.filter(team=team)

    def get_bookings_by_team(self, team):
        return self.bookings.filter(team=team)

    def get_subs_by_team(self, team):
        return self.substitutions.filter(team=team)

    def get_set_piece_by_team(self, team):
        return self.set_piece.filter(team=team)


class GoalEvent(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    goal = models.ForeignKey(Goal, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.event.match)


class FoulEvent(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    foul = models.ForeignKey(Foul, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.event.match)
