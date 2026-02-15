from .models import Goal


def get_goals_by_player(player):
    return Goal.objects.filter(scorer_experimental__in=player.get_positions_played())


def get_player_goals_by_position(player, position):
    return Goal.objects.filter(scorer_experimental__in=player.filter_positions_played_by(position))


def get_assists_by_player(player):
    return Goal.objects.filter(assist_experimental__in=player.get_positions_played())


def get_player_assists_by_position(player, position):
    return Goal.objects.filter(assist_experimental__in=player.filter_positions_played_by(position))
