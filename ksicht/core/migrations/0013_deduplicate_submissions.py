"""
Data migration to deduplicate TaskSolutionSubmission rows.

For each (application, task) pair with multiple submissions, keeps the best one
using this priority:
1. Has a score set (was graded)
2. Has stickers assigned
3. Has file_for_export_normal (was processed for export)
4. Fallback: latest submitted_at

Deletes the rest (including their files from storage).
"""

from django.db import migrations


def deduplicate_submissions(apps, schema_editor):
    TaskSolutionSubmission = apps.get_model("core", "TaskSolutionSubmission")

    # Find all (application, task) pairs with duplicates
    from django.db.models import Count

    duplicates = (
        TaskSolutionSubmission.objects.values("application_id", "task_id")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
    )

    for dup in duplicates:
        submissions = list(
            TaskSolutionSubmission.objects.filter(
                application_id=dup["application_id"],
                task_id=dup["task_id"],
            ).order_by("-submitted_at")
        )

        # Pick the best submission to keep
        keeper = None

        # Priority 1: has a score
        for s in submissions:
            if s.score is not None:
                keeper = s
                break

        # Priority 2: has stickers
        if keeper is None:
            for s in submissions:
                if s.stickers.exists():
                    keeper = s
                    break

        # Priority 3: has export file
        if keeper is None:
            for s in submissions:
                if s.file_for_export_normal:
                    keeper = s
                    break

        # Priority 4: latest submitted_at (first in the list, already sorted)
        if keeper is None:
            keeper = submissions[0]

        # Delete all others
        for s in submissions:
            if s.pk != keeper.pk:
                # Delete associated files from storage
                if s.file:
                    s.file.delete(save=False)
                if s.file_for_export_normal:
                    s.file_for_export_normal.delete(save=False)
                if s.file_for_export_duplex:
                    s.file_for_export_duplex.delete(save=False)
                s.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_alter_gradeapplication_participant_current_grade_and_more"),
    ]

    operations = [
        migrations.RunPython(
            deduplicate_submissions,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
