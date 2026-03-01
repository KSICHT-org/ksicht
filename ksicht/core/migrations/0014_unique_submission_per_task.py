"""
Schema migration to enforce unique (application, task) on TaskSolutionSubmission.

Must run AFTER 0013_deduplicate_submissions to ensure no duplicates exist.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_deduplicate_submissions"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="tasksolutionsubmission",
            unique_together={("application", "task")},
        ),
    ]
