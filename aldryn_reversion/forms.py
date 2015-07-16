from django.core.exceptions import ValidationError
from django.forms import forms
from django.forms.fields import MultipleChoiceField
from django.forms.widgets import CheckboxSelectMultiple
from django.utils.encoding import force_text

from .utils import (
    get_translations_versions_for_object, get_conflict_fks_versions
)


class RecoverObjectWithTranslationForm(forms.Form):
    translations = MultipleChoiceField(
        widget=CheckboxSelectMultiple(),
        help_text='Please select translations to restore.',
        required=True)

    def __init__(self, *args, **kwargs):
        # prepare data for misc lookups
        self.revision = kwargs.pop('revision')
        self.obj = kwargs.pop('obj')
        self.obj_version = kwargs.pop('version')
        self.resolve_conflicts = kwargs.pop('resolve_conflicts')
        # do not check object which needs to be recovered
        versions = self.revision.version_set.exclude(pk=self.obj_version.pk)

        super(RecoverObjectWithTranslationForm, self).__init__(*args, **kwargs)

        translatable = hasattr(self.obj, 'translations')
        if translatable:
            translation_versions = get_translations_versions_for_object(
                self.obj, self.revision, versions)
            # update form
            self.fields['translations'] = MultipleChoiceField(
                widget=CheckboxSelectMultiple(),
                choices=[
                    (translation_version.pk, force_text(translation_version))
                    for translation_version in translation_versions])
        else:
            # do not show translations options if object is not translated
            self.fields.pop('translations')

    def clean(self):
        data = super(RecoverObjectWithTranslationForm, self).clean()
        # if there is self.resolve_conflicts do not count them as conflicts
        exclude = {'pk__in': [version.pk for version in self.resolve_conflicts]}
        conflict_fks_versions = get_conflict_fks_versions(
            self.obj, self.obj_version, self.revision,
            exclude=exclude)
        if bool(conflict_fks_versions):
            raise ValidationError('Cannot restore object, there is conflicts!',
                                  code='invalid')
        return data

    def save(self):
        # if there is self.resolve_conflicts revert those objects to avoid
        # integrity errors, because user cannot do that form admin
        # FIXME: Not tested yet
        for conflict in self.resolve_conflicts:
            conflict.revert()
        # revert main object
        self.obj_version.revert()
        # revert translations, if there is translations
        translations_pks = self.cleaned_data.get('translations', [])
        translation_versions = self.revision.version_set.filter(
            pk__in=translations_pks)
        for translation_version in translation_versions:
            translation_version.revert()
