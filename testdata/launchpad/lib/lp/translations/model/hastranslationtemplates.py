# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Implementation class for objects that `POTemplate`s can belong to."""

__metaclass__ = type
__all__ = [
    'HasTranslationTemplatesMixin',
    ]

from storm.expr import (
    Count,
    Desc,
    )
from zope.interface import implements

from lp.services import helpers
from lp.translations.interfaces.hastranslationtemplates import (
    IHasTranslationTemplates,
    )
from lp.translations.model.pofile import POFile
from lp.translations.model.potemplate import POTemplate


class HasTranslationTemplatesMixin:
    """Helper class for implementing `IHasTranslationTemplates`."""
    implements(IHasTranslationTemplates)

    def getTemplatesCollection(self):
        """See `IHasTranslationTemplates`.

        To be provided by derived classes.
        """
        raise NotImplementedError(
            "Child class must provide getTemplatesCollection.")

    def getSharingPartner(self):
        """See `IHasTranslationTemplates`.

        To be provided by derived classes.
        """
        raise NotImplementedError(
            "Child class must provide getSharingPartner.")

    def _orderTemplates(self, result):
        """Apply the conventional ordering to a result set of templates."""
        return result.order_by(Desc(POTemplate.priority), POTemplate.name)

    def getCurrentTemplatesCollection(self, current_value=True):
        """See `IHasTranslationTemplates`."""
        return self.getTemplatesCollection().restrictCurrent(current_value)

    def getCurrentTranslationTemplates(self,
                                       just_ids=False,
                                       current_value=True):
        """See `IHasTranslationTemplates`."""
        if just_ids:
            selection = POTemplate.id
        else:
            selection = POTemplate

        collection = self.getCurrentTemplatesCollection(current_value)
        return self._orderTemplates(collection.select(selection))

    @property
    def has_translation_templates(self):
        """See `IHasTranslationTemplates`."""
        return bool(self.getTranslationTemplates().any())

    @property
    def has_current_translation_templates(self):
        """See `IHasTranslationTemplates`."""
        return bool(
            self.getCurrentTranslationTemplates(just_ids=True).any())

    @property
    def has_obsolete_translation_templates(self):
        """See `IHasTranslationTemplates`."""
        return bool(
            self.getCurrentTranslationTemplates(
                just_ids=True, current_value=False).any())

    @property
    def has_sharing_translation_templates(self):
        """See `IHasTranslationTemplates`."""
        other_side_obj = self.getSharingPartner()
        if other_side_obj is None:
            return False
        return other_side_obj.has_current_translation_templates

    def getCurrentTranslationFiles(self, just_ids=False):
        """See `IHasTranslationTemplates`."""
        if just_ids:
            selection = POFile.id
        else:
            selection = POFile

        collection = self.getCurrentTemplatesCollection()
        return collection.joinPOFile().select(selection)

    @property
    def has_translation_files(self):
        """See `IHasTranslationTemplates`."""
        return bool(
            self.getCurrentTranslationFiles(just_ids=True).any())

    def getTranslationTemplates(self):
        """See `IHasTranslationTemplates`."""
        return self._orderTemplates(self.getTemplatesCollection().select())

    def getTranslationTemplateByName(self, name):
        """See `IHasTranslationTemplates`."""
        return self.getTemplatesCollection().restrictName(name).select().one()

    def getTranslationTemplateFormats(self):
        """See `IHasTranslationTemplates`."""
        formats_query = self.getCurrentTranslationTemplates().order_by(
            'source_file_format').config(distinct=True)
        return helpers.shortlist(
            formats_query.values(POTemplate.source_file_format), 10)

    def getTemplatesAndLanguageCounts(self):
        """See `IHasTranslationTemplates`."""
        join = self.getTemplatesCollection().joinOuterPOFile()
        result = join.select(POTemplate, Count(POFile.id))
        return result.group_by(POTemplate)
