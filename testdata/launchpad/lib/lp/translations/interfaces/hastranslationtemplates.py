# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Interface for objects that translation templates can belong to."""

__metaclass__ = type
__all__ = [
    'IHasTranslationTemplates',
    ]

from lazr.restful.declarations import (
    export_read_operation,
    operation_for_version,
    operation_returns_collection_of,
    )
from zope.interface import Interface
from zope.schema import Bool

from lp import _


class IHasTranslationTemplates(Interface):
    """An entity that has translation templates attached.

    Examples include `ISourcePackage`, `IDistroSeries`, and `IProductSeries`.
    """

    has_translation_templates = Bool(
        title=_("Does this object have any translation templates?"),
        readonly=True)

    has_current_translation_templates = Bool(
        title=_("Does this object have current translation templates?"),
        readonly=True)

    has_obsolete_translation_templates = Bool(
        title=_("Does this object have obsolete translation templates?"),
        readonly=True)

    has_sharing_translation_templates = Bool(
        title=_("Does this object have sharing translation templates?"),
        readonly=True)

    has_translation_files = Bool(
        title=_("Does this object have translation files?"),
        readonly=True)

    def getTemplatesCollection():
        """Return templates as a `TranslationTemplatesCollection`.

        The collection selects all `POTemplate`s attached to the
        translation target that implements this interface.
        """

    def getSharingPartner():
        """Return the object on the other side of the packaging link.

        Return the object that is sharing translations with this one on the
        other side of a packaging link. It must also implement this interface.
        """

    def getCurrentTemplatesCollection():
        """Return `TranslationTemplatesCollection` of current templates.

        A translation template is considered active when
        `IPOTemplate`.iscurrent flag is set to True.
        """

    def getCurrentTranslationTemplates(just_ids=False):
        """Return an iterator over all active translation templates.

        :param just_ids: If True, return only the `POTemplate.id` rather
            than the full `POTemplate`.  Used to save time on retrieving
            and deserializing the objects from the database.

        A translation template is considered active when
        `IPOTemplate`.iscurrent is set to True.
        """

    def getCurrentTranslationFiles(just_ids=False):
        """Return an iterator over all active translation files.

        A translation file is active if it's attached to an
        active translation template.
        """

    @export_read_operation()
    @operation_returns_collection_of(Interface)
    @operation_for_version('beta')
    def getTranslationTemplates():
        """Return an iterator over all its translation templates.

        The returned templates are either obsolete or current.

        :return: A sequence of `IPOTemplate`.
        """

    def getTranslationTemplateByName(name):
        """Return the template with the given name or None."""

    def getTranslationTemplateFormats():
        """A list of native formats for all current translation templates.
        """

    def getTemplatesAndLanguageCounts():
        """List tuples of `POTemplate` and its language count.

        A template's language count is the number of `POFile`s that
        exist for it.
        """
