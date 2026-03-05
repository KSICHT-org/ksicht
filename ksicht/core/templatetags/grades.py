from django import template

from ksicht.core.models import Grade


register = template.Library()


@register.simple_tag
def grade_list(count=5):
    return Grade.objects.all()[:count]


@register.filter
def dict_get(d, key):
    """Look up a value in a dictionary by key."""
    if isinstance(d, dict):
        return d.get(key)
    return None


@register.filter
def negate(value):
    """Negate a numeric value."""
    try:
        return -value  # type: ignore
    except (TypeError, ValueError):
        return value
