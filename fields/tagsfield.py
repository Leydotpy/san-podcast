import re
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.regex_helper import _lazy_re_compile
from django.utils.translation import gettext_lazy as _


# 1. Keep this for Forms if needed, or for generating the item regex
def char_list_validator(
        sep=",",
        message=None,
        code="invalid",
        allow_spaces=True,
        allow_unicode=True,
        extra_chars=r"_\-"
):
    # ... (Your existing code for generating regex usually goes here) ...
    # For the Model Field, we don't use this directly anymore.
    if allow_unicode:
        char_class = r"\w" + extra_chars
    else:
        char_class = r"A-Za-z0-9" + extra_chars

    space = r"\s*" if allow_spaces else ""

    # Regex ensures:
    # - At least one valid token
    # - No empty tokens between commas
    regexp = _lazy_re_compile(
        r"^(?:[%s]+%s(?:%s[%s]+%s)*)\Z"
        % (char_class, space, re.escape(sep), char_class, space)
    )

    return RegexValidator(
        regexp,
        message=message or _("Enter valid words separated by commas. No empty items allowed."),
        code=code,
    )


# 2. Create a specific validator for the List data type
def validate_tag_list(value):
    """
    Validates that 'value' is a list and every item in it
    matches the allowed characters.
    """
    # If the value is somehow None, we skip (allow null=True handles this)
    if value is None:
        return

    # Check if value is actually a list (essential because to_python returns a list)
    if not isinstance(value, (list, tuple)):
        # If it's a string, it means to_python didn't convert it,
        # or it's raw input. You might want to handle that,
        # but normally for this field it should be a list.
        return

        # Define the Regex for a SINGLE item (not the whole CSV string)
    # This matches: Letters, Numbers, Underscores, Hyphens
    item_regex = re.compile(r'^[A-Za-z0-9_\-]+$')

    for item in value:
        # Check against the single item regex
        if not item_regex.match(item):
            raise ValidationError(
                _("Invalid tag: '%(item)s'. Enter only words (letters, digits, underscores, hyphens)."),
                params={'item': item},
                code='invalid_tag'
            )


class TagsField(models.CharField):
    description = "Stores a list of strings separated by commas"

    # 3. Use the list validator, NOT the regex validator
    default_validators = [validate_tag_list]

    def from_db_value(self, value, expression, connection):
        if value is None:
            return ""
        return ",".join([v.strip() for v in value.split(',') if v.strip()])

    def to_python(self, value):
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if value is None:
            return []
        return [v.strip() for v in str(value).split(',') if v.strip()]

    def get_prep_value(self, value):
        if isinstance(value, list):
            return ','.join([str(v).strip() for v in value if str(v).strip()])
        return str(value).strip()

    def value_to_string(self, obj):
        value = self.value_from_object(obj)
        return self.get_prep_value(value)