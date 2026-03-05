from functools import partial

from django import forms
from django.template.defaultfilters import filesizeformat
from django.urls import reverse
from django_select2.forms import Select2MultipleWidget

from . import models
from .form_utils import FormHelper, Field, Layout, Column, Row, Submit, FileField


class CurrentGradeAppliationForm(forms.Form):
    applied = forms.BooleanField(initial="y", required=True, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        has_birth_date = kwargs.pop("has_birth_date", False)
        is_graduate = kwargs.pop("is_graduate", False)
        is_btn_disabled = (not has_birth_date) or is_graduate

        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("applied"),
            Submit(
                "submit",
                "Přihlásit se do ročníku",
                css_class="is-medium",
                disabled=is_btn_disabled,
            ),
        )
        self.helper.form_action = reverse("core:current_grade_application")


class SolutionSubmitForm(forms.Form):
    SOLUTION_MAX_UPLOAD_SIZE = 1024 * 1024 * 2  # 2MB
    # Add to your settings file
    SOLUTION_CONTENT_TYPES = ["application/pdf"]

    def __init__(self, *args, task, **kwargs):
        super().__init__(*args, **kwargs)

        def _clean_file(self, field_name):
            file = self.cleaned_data[field_name]

            if not file:
                return file

            if file.content_type not in self.SOLUTION_CONTENT_TYPES:
                raise forms.ValidationError("Vybere prosím soubor ve formátu PDF.")

            if file.size > self.SOLUTION_MAX_UPLOAD_SIZE:
                raise forms.ValidationError(
                    f"Maximální velikost souboru je {filesizeformat(self.SOLUTION_MAX_UPLOAD_SIZE)}. Vybraný soubor má velikost {filesizeformat(file.size)}."
                )

            return file

        self.fields[f"file_{task.pk}"] = FileField(
            label="Vyberte soubor s řešením",
            required=True,
            allow_empty_file=False,
        )

        setattr(
            self,
            f"clean_file_{task.pk}",
            partial(_clean_file, self=self, field_name=f"file_{task.pk}"),
        )

        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column(
                    Field(f"file_{task.pk}"), css_class="is-12-mobile is-10-desktop"
                ),
                Column(
                    Submit("submit", "Odeslat", css_class="is-outlined"),
                    css_class="is-12-mobile is-2-desktop has-text-right-desktop",
                ),
                css_class="is-mobile is-multiline",
            )
        )
        self.helper.form_action = (
            reverse("core:solution_submit") + f"?task_id={task.pk}"
        )


class SubmissionForm(forms.Form):
    def __init__(self, *args, participant, digital_submissions, tasks, **kwargs):
        super().__init__(*args, **kwargs)

        self.participant_obj = participant
        self.fields["participant"] = forms.IntegerField(widget=forms.HiddenInput)

        for t in tasks:
            self.fields[f"task_{t.id}"] = forms.BooleanField(
                required=False, disabled=t.id in digital_submissions
            )


class SubmissionOverviewFormSet(forms.BaseFormSet):
    def get_form_kwargs(self, index):
        return self.form_kwargs.get(str(index))


class ScoringForm(forms.ModelForm):
    stickers = forms.TypedMultipleChoiceField(
        coerce=int,
        widget=Select2MultipleWidget({"data-width": "100%"}),
        required=False,
    )

    def __init__(self, *args, max_score, sticker_choices, **kwargs):
        instance = kwargs.get("instance")
        if instance and instance.pk:
            initial = kwargs.setdefault("initial", {})
            try:
                # Use prefetched objects to avoid N+1 queries during template rendering
                initial["stickers"] = [sa.sticker_id for sa in instance.stickerassignment_set.all()]
            except AttributeError:
                initial["stickers"] = list(models.StickerAssignment.objects.filter(
                    awarded_for_submission=instance
                ).values_list("sticker_id", flat=True))

        super().__init__(*args, **kwargs)

        self.sticker_choices = sticker_choices

        self.fields["score"] = forms.DecimalField(
            label="",
            max_value=max_score,
            min_value=0,
            max_digits=5,
            decimal_places=2,
            required=False,
        )

        # Set the choices explicitly so TypedMultipleChoiceField can validate them without hitting the DB
        self.fields["stickers"].choices = [(s.pk, str(s)) for s in sticker_choices]

    def clean_stickers(self):
        # The base field already validates that the input IDs exist in self.fields["stickers"].choices
        # We just need to map them back to model instances for save_m2m compatibility
        selected_pks = self.cleaned_data.get("stickers", [])
        if not selected_pks:
            return []
            
        valid_stickers = []
        for pk_val in selected_pks:
            for s in self.sticker_choices:
                if s.pk == pk_val:
                    valid_stickers.append(s)
                    break
                    
        return valid_stickers

    def save(self, commit=True):
        instance = super().save(commit)
        if commit:
            self.save_stickers(instance)
            
        return instance
        
    def _save_m2m(self):
        super()._save_m2m()
        self.save_stickers(self.instance)
        
    def save_stickers(self, instance):
        if not instance or not instance.pk:
            return
            
        selected_stickers = self.cleaned_data.get("stickers", [])
        
        # Delete old assignments
        models.StickerAssignment.objects.filter(
            awarded_for_submission=instance
        ).exclude(sticker__in=selected_stickers).delete()
        
        # Determine series context from submission
        series = instance.task.series
        
        # Create new assignments
        for sticker in selected_stickers:
            models.StickerAssignment.objects.get_or_create(
                participant_id=instance.application.participant_id,
                sticker=sticker,
                awarded_for_submission=instance,
                defaults={
                    "awarded_in_series": series,
                    "assigned_after_publication": series.results_published,
                }
            )
