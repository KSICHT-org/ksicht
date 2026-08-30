import os
from django import template

register = template.Library()


@register.filter
def filename(value):
    if not value:
        return ""
    if isinstance(value, str):
        return os.path.basename(value)
    if hasattr(value, "name"):
        return os.path.basename(value.name)
    return str(value)
