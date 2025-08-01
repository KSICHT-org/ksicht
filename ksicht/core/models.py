from datetime import date, datetime
from decimal import Decimal
import logging
from operator import attrgetter
import tempfile
from typing import List, Optional
import uuid

from cuser.models import AbstractCUser
from django import forms
from django.contrib.auth.models import Group as UserGroup
from django.core.files.base import File
from django.core.validators import MinValueValidator
from django.db import models
from django.dispatch import receiver
from django.urls import reverse
from django.utils.text import slugify
from django_registration.signals import user_activated
from imagekit.models import ImageSpecField
from imagekit.processors import ResizeToFill
import pydash as py_

from ksicht.pdf import prepare_submission_for_export
from .constants import SCHOOLS_CHOICES


logger = logging.getLogger(__name__)


class User(AbstractCUser):
    def __str__(self):
        return f"{self.get_full_name()} <{self.get_username()}>"

    def is_participant(self):
        return Participant.objects.filter(user=self).exists()

    def is_applied_in_current_grade(self):
        current_date = date.today()
        current_grade = Grade.objects.filter(
            start_date__lte=current_date, end_date__gte=current_date
        ).first()

        return GradeApplication.objects.filter(
             grade=current_grade, participant=self.participant_profile
        ).exists()


@receiver(user_activated)
def create_grade_application(sender, user: User, **kwargs):
    if not user.is_participant():
        logger.error("User %r has been activated but has no participant profile", user)
        return

    if current_grade := Grade.objects.get_current():
        user.participant_profile.applications.add(current_grade)


class GradeManager(models.Manager):
    def get_current(self, current=None):
        current_date = current or date.today()
        return self.filter(
            start_date__lte=current_date, end_date__gte=current_date
        ).first()

    def archive(self, current=None):
        current_date = current or date.today()
        return self.filter(end_date__lt=current_date)


def default_grade_school_year():
    current_year = date.today()
    return f"{current_year.year}/{current_year.year + 1}"


def default_grade_start():
    return date(date.today().year, 8, 1)


def default_grade_end():
    return date(date.today().year + 1, 7, 31)


class Grade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_year = models.CharField(
        verbose_name="Školní rok",
        max_length=50,
        null=False,
        db_index=True,
        unique=True,
        default=default_grade_school_year,
    )
    errata = models.TextField(verbose_name="Errata", null=False, blank=True)
    start_date = models.DateField(
        verbose_name="Začíná",
        null=False,
        blank=False,
        db_index=True,
        default=default_grade_start,
    )
    end_date = models.DateField(
        verbose_name="Končí",
        null=False,
        blank=False,
        db_index=True,
        default=default_grade_end,
    )

    objects = GradeManager()

    class Meta:
        verbose_name = "Ročník"
        verbose_name_plural = "Ročníky"
        ordering = ("-end_date",)

    @property
    def is_in_progress(self):
        return self.start_date <= date.today() <= self.end_date

    def __str__(self):
        return str(self.school_year)

    def full_clean(self, exclude=None, validate_unique=True):
        """Validate the grade.

        Make sure 'valid_through' does not overlap."""
        super().full_clean(exclude, validate_unique)

        if self.start_date is not None and self.end_date is not None:
            g = (
                Grade.objects.filter(
                    models.Q(
                        start_date__lte=self.start_date,
                        end_date__gte=self.start_date,
                    )
                    | models.Q(
                        start_date__lte=self.end_date,
                        end_date__gte=self.end_date,
                    )
                )
                .exclude(pk=self.pk)
                .first()
            )

            if g:
                raise forms.ValidationError(
                    f"Datum konání se překrývá s ročníkem '{g}'."
                )

    def prefetch_series(self):
        if not hasattr(self, "_prefetched_series"):
            self._prefetched_series = self.series.all().prefetch_related(
                "tasks", "attachments"
            )
        return self._prefetched_series

    def get_current_series(self):
        """Return first series that can still accept solution submissions from participants."""
        return (
            py_.chain(list(self.prefetch_series()))
            .filter(attrgetter("accepts_solution_submissions"))
            .sort(key=attrgetter("submission_deadline"))
            .head()
            .value()
        )

    def get_previous_series(self):
        """Return last series that has been closed.

        This is useful for staff to get what needs to be worked with easily."""
        return (
            py_.chain(list(self.prefetch_series()))
            .filter(lambda s: not s.accepts_solution_submissions)
            .sort(key=attrgetter("submission_deadline"))
            .reverse()
            .head()
            .value()
        )

    def get_future_series(self):
        """Get all future series, e.g. those that will come after the current one."""
        current_series = self.get_current_series()

        if not current_series:
            return []

        return [
            s
            for s in self.prefetch_series()
            if s.submission_deadline > current_series.submission_deadline
        ]


class GradeSeries(models.Model):
    SERIES_CHOICES = (
        ("1", "1."),
        ("2", "2."),
        ("3", "3."),
        ("4", "4."),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grade = models.ForeignKey(
        Grade, verbose_name="Ročník", on_delete=models.CASCADE, related_name="series"
    )
    series = models.CharField(
        verbose_name="Série",
        max_length=1,
        choices=SERIES_CHOICES,
        null=False,
        db_index=True,
    )
    expected_publish_date = models.DateField(
        verbose_name="Předpokládané datum zvěřejnění zadání", null=True, blank=True
    )
    submission_deadline = models.DateTimeField(
        verbose_name="Deadline pro odeslání řešení", null=False
    )
    task_file = models.FileField(
        verbose_name="Brožura", upload_to="rocniky/zadani/", null=True, blank=True
    )
    results_published = models.BooleanField(
        verbose_name="Zveřejnit výsledky",
        null=False,
        blank=False,
        default=False,
        db_index=True,
    )

    class Meta:
        unique_together = ("grade", "series")
        verbose_name = "Série"
        verbose_name_plural = "Série"
        ordering = ("grade", "series")
        permissions = (
            ("series_task_envelopes_printout", "Export obálek pro školy se zadáním"),
            ("series_solution_envelopes_printout", "Export obálek s řešením"),
        )

    def __str__(self):
        return f"{self.get_series_display()} série"

    def get_absolute_url(self):
        return reverse(
            "core:series_detail", kwargs={"pk": self.pk, "grade_id": self.grade_id}
        )

    def is_expected_publish_date_passed(self):
        return self.expected_publish_date and self.expected_publish_date < datetime.now().date()

    @property
    def accepts_solution_submissions(self):
        return self.task_file is not None and self.submission_deadline > datetime.now(
            self.submission_deadline.tzinfo
        )

    def get_rankings(
        self,
        exclude_submissionless: bool = True,
        _applications_cache: Optional[List["GradeApplication"]] = None,
        _tasks_cache: Optional[List["Task"]] = None,
        _submissions_cache: Optional[List["TaskSolutionSubmission"]] = None,
    ):
        """Calculate results for series.

        Adds detailed task listing for individual series tasks and a grand total with total score so far
        (this series and the previous ones).

        :param exclude_submissionless: Whether to exclude applications without any submission
        :param _applications_cache: Optional cache of applications to use instead of fetching them from DB,
            please note that `exclude_submissionless` is ignored when this is provided.
        :param _tasks_cache: Optional cache of tasks to use instead of fetching them from DB.
        :param _submissions_cache: Optional cache of submissions to use instead of fetching them from DB.
        :return: Dictionary with `max_score` and `listing` keys where `listing` is a list of tuples
            with application, task scores and total score.
        """
        # Only applications with an actual solution submission
        if _applications_cache is None:
            applications = self.grade.applications.select_related(
                "participant__user"
            ).order_by("created_at")

            if exclude_submissionless:
                applications = applications.exclude(solution_submissions=None)
        else:
            applications = _applications_cache

        tasks = _tasks_cache or self.tasks.all()

        if _submissions_cache is None:
            submissions = TaskSolutionSubmission.objects.filter(
                application__grade=self.grade, task__series__series__lte=self.series
            )
        else:
            submissions = [
                s
                for s in _submissions_cache
                if int(s.task.series.series) <= int(self.series)
            ]

        scoring_dict = {
            a: {"by_tasks": {t: None for t in tasks}, "total": Decimal("0")}
            for a in applications
        }

        def _find_application(app_id):
            return py_.find(applications, lambda a: a.pk == app_id)

        def _find_task(task_id):
            return py_.find(tasks, lambda t: t.pk == task_id)

        for s in submissions:
            a = _find_application(s.application_id)
            t = _find_task(s.task_id)

            if t:
                scoring_dict[a]["by_tasks"][t] = s.score

            scoring_dict[a]["total"] += s.score or Decimal("0")

        scoring = [
            (application, scores["by_tasks"], scores["total"])
            for (application, scores) in scoring_dict.items()
        ]

        # Attach ranks
        sorted_scoring = [
            # (application, rank, task scores, total score)
            (row[0], index + 1, row[1], row[2])
            for (index, row) in enumerate(
                sorted(scoring, key=lambda r: r[2], reverse=True)
            )
        ]

        return {
            "max_score": Task.objects.filter(
                series__grade=self.grade, series__series__lte=self.series
            ).aggregate(models.Sum("points"))["points__sum"],
            "listing": sorted_scoring,
        }

    def tasks_with_submission_count(self):
        return (
            self.tasks.all()
            .annotate(submission_count=models.Count("solution_submissions"))
            .order_by("nr")
        )


class GradeSeriesAttachment(models.Model):
    title = models.CharField(verbose_name="Název", max_length=255, null=False)
    file = models.FileField(
        verbose_name="Soubor", upload_to="rocniky/prilohy/", null=False, blank=False
    )
    series = models.ForeignKey(
        GradeSeries,
        verbose_name="Série",
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    class Meta:
        verbose_name = "Příloha série"
        verbose_name_plural = "Přílohy sérií"
        ordering = ("series", "title")

    def __str__(self):
        return str(self.title)


class Task(models.Model):
    NR_CHOICES = (
        ("1", "1."),
        ("2", "2."),
        ("3", "3."),
        ("4", "4."),
        ("5", "5."),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    series = models.ForeignKey(
        GradeSeries,
        verbose_name="Série",
        on_delete=models.PROTECT,
        related_name="tasks",
    )
    nr = models.CharField(
        verbose_name="Číslo úlohy",
        max_length=1,
        choices=NR_CHOICES,
        null=False,
        db_index=True,
    )
    title = models.CharField(verbose_name="Název", max_length=150, null=False)
    points = models.PositiveIntegerField(
        verbose_name="Max. počet bodů",
        null=False,
        blank=False,
        validators=(MinValueValidator(1),),
    )

    class Meta:
        verbose_name = "Úloha"
        verbose_name_plural = "Úlohy"
        ordering = ("series", "nr")
        permissions = (("solution_export", "Export odevzdaných úloh"),)

    def __str__(self):
        return str(self.title)


class ParticipantManager(models.Manager):
    def active_in_series(self, current_series):
        """Return active participants for series.

        - Everyone who has submitted a solution
        - Everyone who has filed a GradeApplication after the previous
          GradeSeries deadline and before the current GradeSeries deadline
        """
        grade = current_series.grade
        grade.prefetch_series()
        grade_series = list(grade.series.all())

        current_series_index = grade_series.index(current_series)

        # All applications in grade with some submission
        applications_with_submission = GradeApplication.objects.filter(
            grade=grade,
        ).exclude(solution_submissions=None)

        # Has applied in this grade and has some submission
        query = models.Q(gradeapplication__in=applications_with_submission)

        if current_series_index != 0:
            previous_series = grade_series[current_series_index - 1]

            # Has applied after previous series
            applications_in_deadline_range = GradeApplication.objects.filter(
                grade=grade,
                created_at__range=(
                    previous_series.submission_deadline,
                    current_series.submission_deadline,
                ),
            )

            query = query | models.Q(
                gradeapplication__in=applications_in_deadline_range
            )

        return self.filter(query).distinct()


class Participant(models.Model):
    COUNTRY_CHOICES = (
        ("other", "-- jiný --"),
        ("cz", "Česko"),
        ("sk", "Slovensko"),
    )
    GRADE_CHOICES = (
        ("5", "absolvent"),
        ("4", "SŠ, 4."),
        ("3", "SŠ, 3."),
        ("2", "SŠ, 2."),
        ("1", "SŠ, 1."),
        ("0", "ZŠ, 9."),
        ("-1", "ZŠ, 8."),
        ("-2", "ZŠ, 7."),
        ("-3", "ZŠ, 6."),
        # ("l", "nižší"),
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="participant_profile",
    )

    phone = models.CharField(
        verbose_name="Telefon", max_length=20, null=True, blank=True
    )
    birth_date = models.DateField(
        verbose_name="Datum narození",
        max_length=20,
        null=True,
        blank=True,
    )
    street = models.CharField(
        verbose_name="Ulice a číslo popisné/orientační", max_length=100, null=False
    )
    city = models.CharField(verbose_name="Obec", max_length=100, null=False)
    zip_code = models.CharField(verbose_name="PSČ", max_length=10, null=False)
    country = models.CharField(
        verbose_name="Stát", max_length=10, null=False, choices=COUNTRY_CHOICES
    )

    school = models.CharField(
        verbose_name="Škola",
        max_length=80,
        null=False,
        choices=SCHOOLS_CHOICES,
    )
    school_year = models.CharField(
        verbose_name="Ročník",
        max_length=5,
        null=False,
        choices=GRADE_CHOICES,
    )

    school_alt_name = models.CharField(
        verbose_name="Název školy", max_length=80, null=True, blank=True
    )
    school_alt_street = models.CharField(
        verbose_name="Ulice školy", max_length=100, null=True, blank=True
    )
    school_alt_city = models.CharField(
        verbose_name="Obec školy", max_length=100, null=True, blank=True
    )
    school_alt_zip_code = models.CharField(
        verbose_name="PSČ školy", max_length=10, null=True, blank=True
    )

    brochures_by_mail = models.BooleanField(
        verbose_name="Zasílat brožury poštou", default=True
    )

    applications = models.ManyToManyField(
        Grade,
        verbose_name="Přihlášky",
        related_name="participants",
        blank=True,
        through="GradeApplication",
    )

    objects = ParticipantManager()

    class Meta:
        verbose_name = "Řešitel"
        verbose_name_plural = "Řešitelé"

    @property
    def school_name(self):
        return (
            self.get_school_display()
            if self.school != "--jiná--"
            else self.school_alt_name
        )

    def __str__(self):
        return f"Profil účastníka pro <{self.user}>"

    def get_full_name(self):
        return f"{self.user.get_full_name() or self.user.email}"

class GradeApplication(models.Model):
    GRADE_CHOICES = (
        ("5", "absolvent"),
        ("4", "SŠ, 4."),
        ("3", "SŠ, 3."),
        ("2", "SŠ, 2."),
        ("1", "SŠ, 1."),
        ("0", "ZŠ, 9."),
        ("-1", "ZŠ, 8."),
        ("-2", "ZŠ, 7."),
        ("-3", "ZŠ, 6."),
        #("l", "nižší"),
    )

    grade = models.ForeignKey(
        Grade, on_delete=models.CASCADE, related_name="applications"
    )
    participant = models.ForeignKey(Participant, on_delete=models.PROTECT)
    participant_current_grade = models.CharField(
        verbose_name="Ročník", max_length=10, null=True, choices=GRADE_CHOICES
    )
    created_at = models.DateTimeField(verbose_name="Datum vytvoření", auto_now_add=True)

    class Meta:
        verbose_name = "Přihláška do ročníku"
        verbose_name_plural = "Přihlášky do ročníku"

    def __str__(self):
        return f"Přihláška <{self.participant.user}> do ročníku <{self.grade}> z {self.created_at}"


class TaskSolutionSubmission(models.Model):
    application = models.ForeignKey(
        GradeApplication,
        verbose_name="Přihláška",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name="solution_submissions",
    )
    task = models.ForeignKey(
        Task,
        verbose_name="Úloha",
        null=False,
        blank=False,
        on_delete=models.PROTECT,
        related_name="solution_submissions",
    )
    # If file is NULL, it means that the solution has been submitted by post
    file = models.FileField(
        verbose_name="Soubor s řešením",
        upload_to="rocniky/reseni/",
        null=True,
        blank=True,
    )
    file_for_export_normal = models.FileField(
        verbose_name="Soubor s řešením připravený pro export (bez duplexu)",
        upload_to="rocniky/reseni-pro-export/",
        null=True,
        blank=True,
    )
    file_for_export_duplex = models.FileField(
        verbose_name="Soubor s řešením připravený pro export (s duplexem)",
        upload_to="rocniky/reseni-pro-export/",
        null=True,
        blank=True,
    )
    score = models.DecimalField(
        verbose_name="Skóre", max_digits=5, decimal_places=2, null=True, blank=True
    )
    submitted_at = models.DateTimeField(verbose_name="Datum nahrání", auto_now_add=True)
    stickers = models.ManyToManyField(
        "Sticker", blank=True, related_name="solution_uses"
    )

    class Meta:
        verbose_name = "Odevzdané řešení"
        verbose_name_plural = "Odevzdaná řešení"
        permissions = (
            ("change_solution_submission_presence", "Úprava stavu odevzdání řešení"),
            ("scoring", "Bodování"),
        )

    def __str__(self):
        return f"Řešení <{self.task}> pro přihlášku <{self.application_id}>"

    def delete(self, *args, **kwargs):
        self.file.delete()
        super().delete(*args, **kwargs)

    def can_delete(self, user: User) -> bool:
        """Tell whether given user can delete this submission at this time."""
        solution_change_allowed = self.task.series.accepts_solution_submissions
        is_solution_author = self.application.participant.user == user

        return is_solution_author and solution_change_allowed

    def prepare_for_export(self):
        """Use uploaded file to prepare export-ready variants (normal and duplex)."""
        logger.info(
            "Prepare uploaded file from application %r and task %r for export",
            self.application.id,
            self.task.nr,
        )

        if self.file:
            file_normal, file_duplex = prepare_submission_for_export(
                in_file=self.file,
                label=f"Řešitel: {self.application.participant.get_full_name()}       Úloha č. {self.task.nr}".encode(
                    "utf8"
                ),
            )

            with tempfile.TemporaryFile() as tf:
                file_normal.write(tf)
                self.file_for_export_normal.save(
                    f"submission_{self.application.pk}_{self.task.nr}_normal.pdf",
                    File(tf),
                )

            with tempfile.TemporaryFile() as tf:
                file_duplex.write(tf)
                self.file_for_export_duplex.save(
                    f"submission_{self.application.pk}_{self.task.nr}_duplex.pdf",
                    File(tf),
                )

            logger.debug("Export versions prepared OK")
            file_duplex.close()
            file_normal.close()
        else:
            logger.warning("Export version prepare failed - no valid file available")


class StickerManager(models.Manager):
    def get_by_natural_key(self, nr):
        return self.get(nr=nr)


class Sticker(models.Model):
    title = models.CharField(
        verbose_name="Název", max_length=255, null=False, blank=False
    )
    description = models.TextField(verbose_name="Popis", null=True, blank=True)
    nr = models.PositiveSmallIntegerField(
        verbose_name="Číslo", null=False, db_index=True, unique=True
    )
    handpicked = models.BooleanField(
        verbose_name="Přiřazován ručně", default=True, null=False, db_index=True
    )

    objects = StickerManager()

    class Meta:
        verbose_name = "Nálepka"
        verbose_name_plural = "Nálepky"
        ordering = ("nr", "title")

    def __str__(self):
        return f"{self.nr} - {self.title}"

    def natural_key(self):
        return (self.nr,)


class EventAttendee(models.Model):
    user = models.ForeignKey(User, verbose_name="Účastník", on_delete=models.CASCADE)
    event = models.ForeignKey(
        "core.Event", verbose_name="Akce", on_delete=models.CASCADE
    )
    signup_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Datum přihlášky",
        help_text="Bude využito při vyhodnocování náhradníků.",
    )
    user_birth_date = models.DateField(
        verbose_name="Poskytnuté datum narození",
        help_text="Hodnota v momentě přihlášení na akci.",
        null=True,
        blank=True,
    )
    user_phone = models.CharField(
        verbose_name="Poskytnuté telefonní číslo",
        help_text="Hodnota v momentě přihlášení na akci.",
        max_length=20,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Přihláška na akci"
        verbose_name_plural = "Přihlášky na akce"
        ordering = ("signup_date",)
        unique_together = ("user", "event")

    def __str__(self):
        return f"{self.user.get_full_name()} chce jet na {self.event}"


class EventQuerySet(models.QuerySet):
    def visible_to(self, user):
        if user is not None and user.is_authenticated:
            return self.filter(models.Q(is_public=True) | models.Q(visible_to=user))
        return self.filter(is_public=True)

    def future(self, current=None):
        current_date = current or date.today()
        return self.filter(end_date__gte=current_date)

    def past(self, current=None):
        current_date = current or date.today()
        return self.filter(end_date__lt=current_date)

    def accepting_enlistments(self, current=None):
        return self.filter(enlistment_enabled=True)


class Event(models.Model):
    title = models.CharField(verbose_name="Název", max_length=150, null=False)
    description = models.TextField(verbose_name="Popis", null=False, blank=True)
    place = models.CharField(verbose_name="Místo konání", max_length=150, null=True)
    start_date = models.DateField(
        verbose_name="Začíná",
        null=False,
        blank=False,
        db_index=True,
    )
    end_date = models.DateField(
        verbose_name="Končí",
        null=False,
        blank=False,
        db_index=True,
    )
    capacity = models.PositiveSmallIntegerField(
        verbose_name="Doporučený max. počet účastníků", null=True, blank=True
    )
    enlistment_message = models.TextField(
        verbose_name="Zpráva po přihlášení", null=False, blank=True
    )
    enlistment_enabled = models.BooleanField(
        verbose_name="Přihlášení je umožněno", default=False
    )
    require_birth_date = models.BooleanField(
        verbose_name="Vyžadovat vyplnění data narození",
        help_text="Pokud je zaškrtnuto, účastník bude muset nejprve ve svém profilu vyplnit datum narození. Vyplněná "
        "hodnota bude pak uložena u přihlášky pro případ, že účastník hodnotu posléze opět smaže.",
        default=False,
    )
    require_phone_number = models.BooleanField(
        verbose_name="Vyžadovat vyplnění telefonního čísla",
        help_text="Pokud je zaškrtnuto, účastník bude muset nejprve ve svém profilu vyplnit telefonní číslo. Vyplněná "
        "hodnota bude pak uložena u přihlášky pro případ, že účastník hodnotu posléze opět smaže.",
        default=False,
    )
    is_public = models.BooleanField(
        verbose_name="Veřejná akce",
        help_text="Neveřejné akce se zobrazí jen níže uvedeným osobám.",
        default=True,
    )
    publish_occupancy = models.BooleanField(
        verbose_name="Zveřejnit počet účastníků",
        help_text="Pokud je zaškrtnuto, u akce se zobrazí kapacita i aktuální "
        "obsazenost.",
        default=True,
    )
    attendees = models.ManyToManyField(
        User, verbose_name="Účastníci", blank=True, through=EventAttendee
    )
    visible_to = models.ManyToManyField(
        User,
        verbose_name="Viditelné pro tyto uživatele",
        help_text="Využijte pro neveřejné akce. Pokud je akce neveřejná, bude "
        "se zobrazovat jen zde vybraným uživatelům. U veřejných akcí se "
        "nezohledňuje.",
        related_name="private_events",
        blank=True,
    )
    reward_stickers = models.ManyToManyField(
        Sticker,
        verbose_name="Nálepky pro účastníky",
        blank=True,
        help_text="Každý účastník získá zvolené nálepky. Uděleny budou v rámci "
        "série, která datumově následuje po akci.",
        related_name="event_uses",
    )

    objects = EventQuerySet.as_manager()

    class Meta:
        verbose_name = "Akce"
        verbose_name_plural = "Akce"
        ordering = ("-start_date",)
        permissions = (("export_event_attendees", "Export účastníků akce"),)

    def __str__(self):
        return str(self.title)

    def _build_url(self, name):
        return reverse(name, kwargs={"pk": self.pk, "slug": slugify(self.title)})

    def get_absolute_url(self):
        return self._build_url("core:event_detail")

    def get_enlist_url(self):
        return self._build_url("core:event_enlist")

    def get_export_url(self):
        return self._build_url("core:event_attendees_export")

    @property
    def is_accepting_enlistments(self):
        return self.enlistment_enabled and date.today() <= self.end_date


class FlatPageMeta(models.Model):
    flatpage = models.OneToOneField(
        to="flatpages.FlatPage",
        on_delete=models.CASCADE,
        verbose_name="Stránka",
        related_name="metadata",
    )
    title = models.CharField("Titulek", max_length=255, blank=True)
    keywords = models.CharField(
        "Klíčová slova", help_text="Oddělujte čárkou", max_length=150, blank=True
    )
    description = models.TextField("Krátký popis", blank=True)
    allowed_groups = models.ManyToManyField(
        UserGroup,
        verbose_name="Povoleno pro tyto skupiny",
        help_text="Pokud zde něco zvolíte, stránka bude dostupná pouze pro "
        "uvedené skupiny. Pokud chcete nechat stránku dostupnou pro řešitele, "
        "nevyplňujte zde nic.",
        blank=True,
    )

    class Meta:
        verbose_name = "Metadata statické stránky"
        verbose_name_plural = "Metadata statických stránek"

    def __str__(self):
        return f"Metadata pro {self.flatpage}"

    def is_accessible_for(self, user):
        """Decide whether user should be allowed to display this page."""
        allowed_groups = self.allowed_groups.all()

        if len(allowed_groups) > 0 and (
            not user.is_authenticated
            or (
                not user.is_superuser
                and all(g not in allowed_groups for g in user.groups.all())
            )
        ):
            return False

        return True


class TeamMember(models.Model):
    name = models.CharField("Jméno", max_length=255)
    role = models.CharField("Role", blank=True, max_length=150)
    bio = models.TextField("Krátké představení", null=False, blank=False)
    image = models.ImageField(
        verbose_name="Obrázek",
        help_text="Použijte čtvercový formát",
        upload_to="lide/",
        null=False,
        blank=False,
    )
    image_thumbnail = ImageSpecField(
        source="image",
        processors=[ResizeToFill(700, 700)],
        format="JPEG",
        options={"quality": 70},
    )
    order = models.PositiveIntegerField(
        verbose_name="Pořadí",
        help_text="Čím nižší, tím dříve v seznamu.",
        default=0,
    )
    url_fb = models.URLField("Odkaz Facebook", blank=True)
    url_ig = models.URLField("Odkaz na Instagram", blank=True)
    url_other = models.URLField("Odkaz na vlastní web", blank=True)

    class Meta:
        verbose_name = "Člen KSICHT týmu"
        verbose_name_plural = "Členové KSICHT týmu"
        ordering = ("order",)

    def __str__(self):
        return str(self.name)
