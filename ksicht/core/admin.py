from cuser.admin import UserAdmin
from django import forms
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.flatpages.admin import FlatPageAdmin
from django.contrib.flatpages.models import FlatPage
from django.db.models import TextField
from django.db.models.query import QuerySet
from django.forms.models import BaseInlineFormSet
from django.http import HttpRequest
from django.urls import reverse
from django.utils.safestring import mark_safe
from imagekit import ImageSpec
from imagekit.admin import AdminThumbnail
from imagekit.cachefiles import ImageCacheFile
from imagekit.processors import ResizeToFill
from markdownx.widgets import AdminMarkdownxWidget

from . import models


class GradeSeriesInlineFormSet(BaseInlineFormSet):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.initial = [
            {"series": "1"},
            {"series": "2"},
            {"series": "3"},
            {"series": "4"},
        ]


class GradeSeriesInline(admin.TabularInline):
    model = models.GradeSeries
    min_num = 4
    max_num = 4
    formset = GradeSeriesInlineFormSet

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Grade)
class GradeAdmin(admin.ModelAdmin):
    inlines = (GradeSeriesInline,)

    formfield_overrides = {
        TextField: {"widget": AdminMarkdownxWidget},
    }


class TaskInlineFormSet(BaseInlineFormSet):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.initial = [
            {"nr": "1"},
            {"nr": "2"},
            {"nr": "3"},
            {"nr": "4"},
            {"nr": "5"},
        ]


class TaskInline(admin.TabularInline):
    model = models.Task
    min_num = 5
    max_num = 5
    formset = TaskInlineFormSet


class GradeSeriesAttachmentInline(admin.TabularInline):
    model = models.GradeSeriesAttachment
    extra = 0


@admin.register(models.GradeSeries)
class GradeSeriesAdmin(admin.ModelAdmin):
    list_display = ("grade", "series", "submission_deadline")
    list_filter = ("grade",)
    list_select_related = ("grade",)
    search_fields = ("grade__school_year", "series")
    inlines = (GradeSeriesAttachmentInline, TaskInline)
    ordering = ("grade", "-submission_deadline")


@admin.register(models.Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = (
        "first_name",
        "last_name",
        "school",
        "user_link",
    )
    list_select_related = ("user",)
    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__email",
        "school",
    )
    autocomplete_fields = ("user",)
    readonly_fields = ("first_name", "last_name", "user_link")
    actions = ["increase_school_year"]

    def first_name(self, obj):
        return obj.user.first_name

    def last_name(self, obj):
        return obj.user.last_name

    def user_link(self, obj):
        return mark_safe(
            f"<a href=\"{reverse('admin:core_user_change', args=(obj.user.pk,))}\">{obj.user.email}</a>"
        )

    user_link.short_description = "Uživatel"

    def increase_school_year(self, request, queryset):
        for participant in queryset:
            GCH0, GCH1 = zip(*participant.GRADE_CHOICES)
            index = GCH0.index(participant.school_year)
            if index != 0:
                participant.school_year = participant.GRADE_CHOICES[index - 1][0]
                participant.save()

    increase_school_year.short_description = "Zvýšit ročník studia"


@admin.register(models.Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("nr", "title", "series", "school_year")
    search_fields = ("title", "nr", "series__grade__school_year")
    list_select_related = ("series__grade",)
    list_filter = ("series__grade",)

    def school_year(self, obj):
        return obj.series.grade.school_year

    school_year.short_description = "Školní rok"


@admin.register(models.GradeApplication)
class GradeApplicationAdmin(admin.ModelAdmin):
    search_fields = ("grade__school_year", "participant__user__email")
    list_select_related = (
        "grade",
        "participant__user",
    )
    actions = ["paste_school_grade"]
    autocomplete_fields = ("participant",)

    def paste_school_grade(self, request, queryset):
        for application in queryset:
            application.participant_current_grade = application.participant.school_year
            application.save()

    paste_school_grade.short_description = "Změnit ročník studia v přihlášce."


@admin.register(models.TaskSolutionSubmission)
class SolutionSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "task",
        "task_nr",
        "user",
        "series",
        "score",
        "submitted_at",
    )
    list_filter = (
        "task__series__grade",
        "task__series__series",
        "task__nr",
    )
    list_select_related = (
        "application__participant__user",
        "task__series",
    )
    autocomplete_fields = ("task", "application")
    readonly_fields = ("submitted_at",)
    ordering = ("application__participant__user__last_name",)
    search_fields = (
        "application__participant__user__last_name",
        "application__participant__user__first_name",
        "task__title",
        "task__nr",
    )

    def user(self, obj: models.TaskSolutionSubmission):
        return obj.application.participant.user

    user.short_description = "Uživatel"

    def series(self, obj: models.TaskSolutionSubmission):
        return obj.task.series

    series.short_description = "Série"

    def task_nr(self, obj: models.TaskSolutionSubmission):
        return obj.task.nr

    task_nr.short_description = "Č. úlohy"


@admin.register(models.Sticker)
class StickerAdmin(admin.ModelAdmin):
    search_fields = ("nr", "title")
    list_display = ("nr", "title", "handpicked", "assignment_limit")
    list_filter = ("handpicked", "assignment_limit")


@admin.register(models.StickerAssignment)
class StickerAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "participant_name",
        "sticker",
        "series_display",
        "awarded_for_submission",
        "event_display",
        "awarded_at",
        "assigned_after_publication",
    )
    list_filter = (
        "sticker",
        "ignore_limit",
        "assigned_after_publication",
        "awarded_in_series__grade",
    )
    list_select_related = (
        "participant__user",
        "sticker",
        "awarded_in_series__grade",
        "awarded_for_submission__task__series",
        "awarded_for_event",
    )
    search_fields = (
        "participant__user__last_name",
        "participant__user__first_name",
        "participant__user__email",
        "sticker__title",
    )
    autocomplete_fields = ("participant", "sticker", "awarded_for_submission")
    readonly_fields = ("awarded_at",)
    ordering = ("-awarded_at",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "awarded_in_series":
            field.label_from_instance = lambda obj: f"{obj.grade} – {obj.get_series_display()} série"
        elif db_field.name == "awarded_for_event":
            field.label_from_instance = lambda obj: f"{obj.title} ({obj.start_date.year})"
        return field

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        original_clean = form.clean

        def clean(self_form):
            cleaned_data = original_clean(self_form) if callable(original_clean) else self_form.cleaned_data
            sources = [
                cleaned_data.get("awarded_in_series"),
                cleaned_data.get("awarded_for_submission"),
                cleaned_data.get("awarded_for_event"),
            ]
            filled = sum(1 for s in sources if s)
            if filled > 1:
                raise forms.ValidationError(
                    "Vyberte nejvýše jeden zdroj přiřazení (série, řešení nebo akce)."
                )
            return cleaned_data

        form.clean = clean
        return form

    def participant_name(self, obj):
        return obj.participant.get_full_name()

    participant_name.short_description = "Řešitel"
    participant_name.admin_order_field = "participant__user__last_name"

    def series_display(self, obj):
        if obj.awarded_in_series:
            return f"{obj.awarded_in_series.grade} – {obj.awarded_in_series.get_series_display()} série"
        return "-"

    series_display.short_description = "Série"
    series_display.admin_order_field = "awarded_in_series"

    def event_display(self, obj):
        if obj.awarded_for_event:
            return f"{obj.awarded_for_event.title} ({obj.awarded_for_event.start_date.year})"
        return "-"

    event_display.short_description = "Akce"
    event_display.admin_order_field = "awarded_for_event"


class EventAttendeeInline(admin.TabularInline):
    model = models.EventAttendee
    readonly_fields = ("signup_date",)
    raw_id_fields = ("user",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[UserAdmin]:
        return super().get_queryset(request).select_related("user", "event")


class EventAdminForm(forms.ModelForm):
    class Meta:
        model = models.Event
        fields = "__all__"  # required in new versions

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "visible_to" in self.fields:
            self.fields["visible_to"].queryset = self.fields[
                "visible_to"
            ].queryset.order_by("last_name", "first_name", "email")


@admin.register(models.Event)
class EventAdmin(admin.ModelAdmin):
    search_fields = ("title",)
    list_display = (
        "title",
        "place",
        "start_date",
        "end_date",
        "capacity",
        "enlistment_enabled",
        "is_public",
        "publish_occupancy",
    )
    list_filter = ("is_public", "enlistment_enabled")
    inlines = (EventAttendeeInline,)
    date_hierarchy = "start_date"

    formfield_overrides = {
        TextField: {"widget": AdminMarkdownxWidget},
    }

    form = EventAdminForm


admin.site.register(Permission)
admin.site.register(models.User, UserAdmin)


class MetadataInline(admin.StackedInline):
    model = models.FlatPageMeta


class MarkdownFlatPageAdmin(FlatPageAdmin):
    inlines = (MetadataInline,)
    formfield_overrides = {
        TextField: {"widget": AdminMarkdownxWidget},
    }


admin.site.unregister(FlatPage)
admin.site.register(FlatPage, MarkdownFlatPageAdmin)


class AdminThumbnailSpec(ImageSpec):
    processors = [ResizeToFill(100, 100)]
    format = "JPEG"
    options = {"quality": 60}


def cached_admin_thumb(instance):
    cached = ImageCacheFile(AdminThumbnailSpec(instance.image))
    cached.generate()
    return cached


class TeamMemberAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "thumbnail",
    )
    thumbnail = AdminThumbnail(image_field=cached_admin_thumb)

    formfield_overrides = {
        TextField: {"widget": AdminMarkdownxWidget},
    }


admin.site.register(models.TeamMember, TeamMemberAdmin)


@admin.register(models.Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "style",
        "is_active",
        "only_authenticated",
        "valid_from",
        "valid_to",
        "dismissible",
        "created_at",
    )
    list_filter = ("is_active", "only_authenticated", "style", "dismissible")
    search_fields = ("message", "link_text", "link_url")
    readonly_fields = ("created_at", "updated_at")
    formfield_overrides = {
        TextField: {"widget": AdminMarkdownxWidget},
    }
    fieldsets = (
        (
            "Zpráva a styl",
            {
                "fields": ("message", "style", "is_active", "only_authenticated"),
            },
        ),
        (
            "Časové omezení (volitelné)",
            {
                "fields": ("valid_from", "valid_to"),
                "classes": ("collapse",),
                "description": "Pokud necháte prázdné, banner se zobrazuje neustále dokud je aktivní.",
            },
        ),
        (
            "Odkaz a chování",
            {
                "fields": ("link_url", "link_text", "dismissible"),
            },
        ),
        (
            "Systémové informace",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

