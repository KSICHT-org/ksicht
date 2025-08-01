from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse
from django.views.generic import View
from django.views.generic.detail import BaseDetailView

from ksicht import pdf
from .. import models
from ..constants import SCHOOLS


__all__ = (
    "SeriesTaskEnvelopesPrintout",
    "ActiveParticipantsEnvelopesPrintout",
    "AllParticipantsEnvelopesPrintout",
    "AllParticipantsWithBrochurePreferenceEnvelopesPrintout",
)


class SeriesTaskEnvelopesPrintout(View):
    def get(self, request, *args, **kwargs):
        response = HttpResponse(content_type="application/pdf")
        filename = quote("obalky_pro_skoly")
        response["Content-Disposition"] = f"attachment; filename*=UTF-8''{filename}.pdf"

        def _build_lines(s):
            # If street exists
            if s[9]:
                return {
                    "lines": (
                        "K rukám učitelů chemie",
                        s[6],
                        s[8],
                        f"{s[13]} {s[14]}",
                    ),
                    "note": None,
                }
            return {
                "lines": ("K rukám učitelů chemie", s[6], s[14], s[13]),
                "note": None,
            }

        lines = [_build_lines(s) for s in SCHOOLS]

        pdf.envelopes(lines, settings.KSICHT_CONTACT_ADDRESS_LINES, response)

        return response


class ParticipantEnvelopesPrintout:
    def render_to_response(self, context):
        participants = self.get_participants(context).order_by(
            "user__last_name", "user__first_name", "user__email"
        ).distinct()
        title = self.get_title(context)
        response = HttpResponse(content_type="application/pdf")
        response[
            "Content-Disposition"
        ] = f"attachment; filename*=UTF-8''{quote(title)}.pdf"

        lines = [
            {
                "lines": (
                    p.get_full_name(),
                    p.street,
                    f"{p.zip_code} {p.city}",
                    p.get_country_display(),
                ),
                "note": self.get_recipient_note(p),
            }
            for p in participants
        ]

        pdf.envelopes(lines, settings.KSICHT_CONTACT_ADDRESS_LINES, response)

        return response

    def get_participants(self, context):
        raise NotImplementedError()

    def get_title(self, context):
        raise NotImplementedError()

    def get_recipient_note(self, participant: models.Participant):
        return None


class ActiveParticipantsEnvelopesPrintout(BaseDetailView, ParticipantEnvelopesPrintout):
    queryset = models.GradeSeries.objects.all()

    def get_participants(self, context):
        return models.Participant.objects.active_in_series(context["object"])

    def get_title(self, context):
        return str(context["object"]) + " - obálky pro řešitele"

    def get_recipient_note(self, participant: models.Participant):
        if participant.brochures_by_mail:
            return "Brožura"
        return None


class AllParticipantsEnvelopesPrintout(BaseDetailView, ParticipantEnvelopesPrintout):
    queryset = models.Grade.objects.all()

    def get_participants(self, context):
        return models.Participant.objects.filter(applications=context["object"])

    def get_title(self, context):
        return "Ročník " + str(context["object"]) + " - obálky pro přihlášené"


class AllParticipantsWithBrochurePreferenceEnvelopesPrintout(
    AllParticipantsEnvelopesPrintout
):
    def get_participants(self, context):
        return super().get_participants(context).filter(brochures_by_mail=True)

    def get_title(self, context):
        return "Ročník " + str(context["object"]) + " - obálky pro přihlášené - výběr"
