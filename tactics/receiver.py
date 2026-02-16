from django.core.exceptions import ValidationError
from django.dispatch import receiver
from django.db.models.signals import m2m_changed

from apps.tactics.models import Formation, LineUp

type Instance = Formation
type LineUp = LineUp

@receiver(m2m_changed, sender=Formation.lineup.through)
def my_handler(sender, instance: Instance, action: str, model: LineUp, pk_set, **kwargs):
    errors = {}
    if action == 'pre_add':
        lineups = model.objects.filter(pk__in=pk_set)
        for lineup in lineups:
            if not instance.shape.check_player_position(lineup.position.position):
                errors[lineup.position.position] = (f"Invalid Lineup Shape !!"
                                                    f"{lineup.position.position} chosen"
                                                    f" for {lineup.player.name} "
                                                    f"is invalid for {instance.shape.name}'s variation")
        if len(errors.items()) > 0:
            raise ValidationError(errors)

    lineup_count = instance.lineup.all().count()
    if lineup_count > 11:
        errors["lineup_count"] = f"There are more than the maximum {lineup_count} lineups"
    if lineup_count < 11:
        errors["lineup_count"] = f"There are {lineup_count} lineups"

