from django.core.management.base import BaseCommand

from apps.tactics.models import (
    Position,
    Shape,
    FormationStyle
)

from apps.config import POSITION_MAP

class Command(BaseCommand):
    help = 'Prepopulate lineup positions model and create shapes for corresponding lineup'

    def handle(self, *args, **options):
        for style, shapes in POSITION_MAP.items():
            style, _ = FormationStyle.objects.update_or_create(
                name=style,
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully created {style.name}'))
            for shape, positions in shapes.items():
                _shape, _ = Shape.objects.update_or_create(
                    name=shape,
                    style=style
                )
                self.stdout.write(self.style.SUCCESS(f'Successfully created {_shape.name}'))
                for position, coords in positions.items():
                    print(position, coords)
                    _position, _ = Position.objects.update_or_create(
                        position=position,
                        shape=_shape,
                        defaults=coords,
                    )
                    self.stdout.write(self.style.SUCCESS(f'Successfully created {_position.position}'))
        self.stdout.write(self.style.SUCCESS('Successfully created lineup positions'))
