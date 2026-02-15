import uuid

from django.db.models.fields import CharField

from utils.utils import regen_id


class RegenField(CharField):

    def __init__(self, *args, max_length=240, **kwargs):
        if max_length > 240:
            raise ValueError("Max length is greater than 240 characters")
        kwargs["max_length"] = max_length
        kwargs["default"] = uuid.uuid4
        super().__init__(*args, **kwargs)