import django.db.migrations.operations.special
import django.db.models.deletion
from django.db import migrations, models


def migrate_stickers(apps, schema_editor):
    from ksicht.core.models import GradeSeries
    from ksicht.core.stickers.services import grant_stickers_for_series
    
    # 1. Automatic & Event stickers — skip limits because historically stickers
    # could be assigned multiple times. Limits only apply going forward.
    for series in GradeSeries.objects.filter(results_published=True).order_by("grade__start_date", "series"):
        grant_stickers_for_series(series, skip_limits=True)
        
    # 2. Manual submission stickers from old M2M field
    HistoricalTaskSolutionSubmission = apps.get_model("core", "TaskSolutionSubmission")
    HistoricalStickerAssignment = apps.get_model("core", "StickerAssignment")
    
    for sub in HistoricalTaskSolutionSubmission.objects.exclude(stickers__isnull=True).prefetch_related('stickers'):
        for sticker in sub.stickers.all():
            HistoricalStickerAssignment.objects.get_or_create(
                participant_id=sub.application.participant_id,
                sticker_id=sticker.id,
                awarded_for_submission_id=sub.id
            )

def set_ignore_limit(apps, schema_editor):
    StickerAssignment = apps.get_model('core', 'StickerAssignment')
    StickerAssignment.objects.all().update(ignore_limit=True)

def reverse_set_ignore_limit(apps, schema_editor):
    StickerAssignment = apps.get_model('core', 'StickerAssignment')
    StickerAssignment.objects.all().update(ignore_limit=False)

class Migration(migrations.Migration):
    dependencies = [
        ('core', '0014_unique_submission_per_task'),
    ]

    operations = [
        # Add assignment_limit field to Sticker
        migrations.AddField(
            model_name="sticker",
            name="assignment_limit",
            field=models.CharField(
                choices=[
                    ("unlimited", "Neomezeně"),
                    ("once_per_grade", "Jednou za ročník"),
                    ("once_in_lifetime", "Jednou za život"),
                ],
                db_index=True,
                default="unlimited",
                max_length=20,
                verbose_name="Omezení přiřazení",
            ),
        ),
        # Add db_index to handpicked field
        migrations.AlterField(
            model_name='sticker',
            name='handpicked',
            field=models.BooleanField(db_index=True, default=True, verbose_name='Přiřazována ručně'),
        ),
        # Create StickerAssignment model
        migrations.CreateModel(
            name='StickerAssignment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('awarded_at', models.DateTimeField(auto_now_add=True)),
                ('ignore_limit', models.BooleanField(default=False, help_text='If true, this assignment does not count against the assignment limit (used for historical stickers).')),
                ('assigned_after_publication', models.BooleanField(default=False, help_text='If true, this sticker was assigned after the series results were already published.')),
                ('awarded_for_event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.event')),
                ('awarded_for_submission', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.tasksolutionsubmission')),
                ('awarded_in_series', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='core.gradeseries')),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sticker_assignments', to='core.participant')),
                ('sticker', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='core.sticker')),
            ],
            options={
                'verbose_name': 'Přiřazená nálepka',
                'verbose_name_plural': 'Přiřazené nálepky',
                'ordering': ('-awarded_at',),
                'constraints': [models.UniqueConstraint(condition=models.Q(('awarded_in_series__isnull', False)), fields=('participant', 'sticker', 'awarded_in_series'), name='unique_sticker_per_series'), models.UniqueConstraint(condition=models.Q(('awarded_for_submission__isnull', False)), fields=('participant', 'sticker', 'awarded_for_submission'), name='unique_sticker_per_submission'), models.UniqueConstraint(condition=models.Q(('awarded_for_event__isnull', False)), fields=('participant', 'sticker', 'awarded_for_event'), name='unique_sticker_per_event')],
            },
        ),
        # Backfill historical sticker assignments
        migrations.RunPython(
            code=migrate_stickers,
            reverse_code=django.db.migrations.operations.special.RunPython.noop,
        ),
        # Remove old M2M stickers field from TaskSolutionSubmission
        migrations.RemoveField(
            model_name='tasksolutionsubmission',
            name='stickers',
        ),
        # Mark all backfilled assignments as historical (ignore_limit=True)
        migrations.RunPython(
            code=set_ignore_limit,
            reverse_code=reverse_set_ignore_limit,
        ),
    ]
