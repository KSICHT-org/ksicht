from django import template

register = template.Library()


@register.filter
def safe_person_image_url(person):
    if not person:
        return ""
    try:
        if not person.image or not person.image.name:
            return ""
        if not person.image.storage.exists(person.image.name):
            return ""
        return person.image_thumbnail.url
    except Exception:
        return ""
