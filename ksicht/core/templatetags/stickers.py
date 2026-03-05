from django import template


register = template.Library()


@register.inclusion_tag("core/includes/sticker.html")
def sticker(sticker, grayed_out=False, limit_label="", force_link_color=False, after_publication=False):
    return {
        "nr": sticker.nr,
        "title": sticker.title,
        "automatic": not sticker.handpicked,
        "grayed_out": grayed_out,
        "limit_label": limit_label,
        "force_link_color": force_link_color,
        "after_publication": after_publication,
    }
