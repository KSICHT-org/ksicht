from collections import defaultdict
import csv
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponse
from django.utils import formats
from django.utils.decorators import method_decorator
from django.views.generic import DetailView, ListView
from django.views.generic.detail import BaseDetailView

from .. import models


def is_enlisted(user, event):
    return user.is_authenticated and user in event.attendees.all()


class EventListView(ListView):
    template_name = "core/event_listing.html"

    def get_queryset(self):
        return models.Event.objects.visible_to(self.request.user).prefetch_related(
            "attendees"
        )

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        year_list = defaultdict(list)

        for e in data["object_list"]:
            enlisted = self.request.user in e.attendees.all()
            can_enlist = (
                e.is_accepting_enlistments
                and self.request.user.is_authenticated
                and not enlisted
            )
            year_list[e.start_date.year].append((e, enlisted, can_enlist))

        data["year_list"] = year_list.items()

        return data


class EventDetailView(DetailView):
    template_name = "core/event_detail.html"

    def get_queryset(self):
        return models.Event.objects.visible_to(self.request.user).prefetch_related(
            "attendees"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_enlisted"] = is_enlisted(self.request.user, self.object)
        context["can_enlist"] = (
            self.object.is_accepting_enlistments
            and self.request.user.is_authenticated
            and not context["is_enlisted"]
        )
        context["attendee_count"] = self.object.attendees.count()
        context["free_places"] = max(
            0, self.object.capacity - context["attendee_count"]
        )
        return context


@method_decorator([login_required], name="dispatch")
class EventEnlistView(DetailView):
    template_name = "core/event_enlist.html"

    def get_queryset(self):
        return (
            models.Event.objects.visible_to(self.request.user)
            .accepting_enlistments(self.request.user)
            .prefetch_related("attendees")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context["attendee_count"] = self.object.attendees.count()
        context["free_places"] = max(
            0, self.object.capacity - context["attendee_count"]
        )

        # Verify user has phone number and birth date set.
        context["phone_check_passed"] = not self.object.require_phone_number or bool(
            self.request.user.participant_profile.phone
        )
        context["birth_date_check_passed"] = not self.object.require_birth_date or bool(
            self.request.user.participant_profile.birth_date
        )
        context["can_enlist"] = (
            context["phone_check_passed"] and context["birth_date_check_passed"]
        )

        # Make sure user can still enlist.
        can_enlist = not is_enlisted(self.request.user, self.object)

        if not can_enlist:
            raise Http404()

        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)

        if not context["can_enlist"]:
            raise Http404()

        models.EventAttendee.objects.create(
            user=self.request.user,
            event=self.object,
            user_birth_date=self.request.user.participant_profile.birth_date,
            user_phone=self.request.user.participant_profile.phone,
        )

        context["has_enlisted"] = True
        context["is_substitue"] = self.object.capacity > context["attendee_count"]

        return self.render_to_response(context)


class EventAttendeesExportView(BaseDetailView):
    queryset = models.Event.objects.all()

    def render_to_response(self, context):
        event = context["object"]
        attendees = models.EventAttendee.objects.filter(event=event).select_related(
            "user"
        )
        participants = models.Participant.objects.filter(
            user__eventattendee__in=attendees
        )

        response = HttpResponse(content_type="text/csv")
        filename = quote(f"{event} - účastníci.csv")
        response["Content-Disposition"] = f"attachment; filename*=utf-8''{filename}"

        writer = csv.writer(response, quotechar='"')
        writer.writerow(
            [
                "Pořadí",
                "Datum přihlášky",
                "Email",
                "Jméno",
                "Příjmení",
                "Status",
                "(Telefon)",
                "(Datum narození))",
                "(Škola)",
                "(Město)",
            ]
        )

        for idx, attendee in enumerate(attendees):
            rank = idx + 1
            is_substitute = rank > event.capacity
            participant = next(
                (p for p in participants if p.user_id == attendee.user.pk), None
            )
            birth_date = (
                participant.birth_date if participant else None
            ) or attendee.user_birth_date
            row = [
                f"{rank}.",
                formats.date_format(attendee.signup_date, "SHORT_DATE_FORMAT"),
                attendee.user.email,
                attendee.user.first_name,
                attendee.user.last_name,
                "Náhradník" if is_substitute else "Účastník",
                (participant.phone if participant else None) or attendee.user_phone,
                (
                    formats.date_format(birth_date, "SHORT_DATE_FORMAT")
                    if birth_date
                    else None
                ),
            ]

            if participant:
                row += [participant.school_name, participant.city]

            writer.writerow(row)

            if rank == event.capacity:
                writer.writerow([])

        return response
