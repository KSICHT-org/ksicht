import tempfile

from django.core.files.base import File
from django.db import migrations, models

from ksicht.pdf import prepare_submission_for_export


def prepare_export_ready_files_forwards(apps, schema_editor):
    TaskSolutionSubmission = apps.get_model("core", "TaskSolutionSubmission")

    for submission in TaskSolutionSubmission.objects.filter(file__isnull=False).filter(
        models.Q(file_for_export_normal__isnull=True)
        | models.Q(file_for_export_duplex__isnull=True)
    ):
        if submission.file:
            user_full_name = f"{submission.application.participant.user.first_name} {submission.application.participant.user.last_name}"
            user_full_name = user_full_name.strip()
            participant_full_name = (
                user_full_name or submission.application.participant.user.email
            )

            file_normal, file_duplex = prepare_submission_for_export(
                in_file=submission.file,
                label=f"Řešitel: {participant_full_name}       Úloha č. {submission.task.nr}".encode(
                    "utf8"
                ),
            )

            with tempfile.TemporaryFile() as tf:
                file_normal.write(tf)
                submission.file_for_export_normal.save(
                    f"submission_{submission.application.pk}_{submission.task.nr}_normal.pdf",
                    File(tf),
                )

            with tempfile.TemporaryFile() as tf:
                file_duplex.write(tf)
                submission.file_for_export_duplex.save(
                    f"submission_{submission.application.pk}_{submission.task.nr}_duplex.pdf",
                    File(tf),
                )

            submission.save()


def prepare_export_ready_files_backwards(apps, schema_editor): ...


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_auto_20211121_0900"),
    ]

    operations = [
        migrations.RunPython(
            prepare_export_ready_files_forwards, prepare_export_ready_files_backwards
        ),
    ]
