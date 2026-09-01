from django.conf import settings
from .core.models import Announcement


def global_info(request):
    try:
        user = getattr(request, "user", None)
        announcements = list(Announcement.objects.active(user=user))
    except Exception:
        announcements = []

    return {
        "siteinfo": settings.SITEINFO,
        "announcements": announcements,
    }

