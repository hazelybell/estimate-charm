# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).
"""Custom language code."""

__metaclass__ = type

__all__ = [
    'ICustomLanguageCode',
    'IHasCustomLanguageCodes',
    ]

from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    Int,
    Object,
    Set,
    TextLine,
    )
from zope.schema.interfaces import IObject

from lp import _
from lp.registry.interfaces.distribution import IDistribution
from lp.registry.interfaces.product import IProduct
from lp.registry.interfaces.sourcepackagename import ISourcePackageName


class ICustomLanguageCode(Interface):
    """`CustomLanguageCode` interface."""

    id = Int(title=_("ID"), required=True, readonly=True)
    product = Object(
        title=_("Product"), required=False, readonly=True, schema=IProduct)
    distribution = Object(
        title=_("Distribution"), required=False, readonly=True,
        schema=IDistribution)
    sourcepackagename = Object(
        title=_("Source package name"), required=False, readonly=True,
        schema=ISourcePackageName)
    language_code = TextLine(title=_("Language code"),
        description=_("Language code to treat as special."),
        required=True, readonly=False)
    language = Choice(
        title=_("Language"), required=False, readonly=False,
        vocabulary='Language',
        description=_("Language to map this code to.  "
            "Leave empty to drop translations for this code."))

    # Reference back to the IHasCustomLanguageCodes.
    translation_target = Object(
        title=_("Context this custom language code applies to"),
        required=True, readonly=True, schema=IObject)


class IHasCustomLanguageCodes(Interface):
    """A context that can have custom language codes attached.

    Implemented by `Product` and `SourcePackage`.
    """
    custom_language_codes = Set(
        title=_("Custom language codes"),
        description=_("Translations for these language codes are re-routed."),
        value_type=Object(schema=ICustomLanguageCode),
        required=False, readonly=False)

    has_custom_language_codes = Bool(
        title=_("There are custom language codes in this context."),
        readonly=True, required=True)

    def getCustomLanguageCode(language_code):
        """Retrieve `CustomLanguageCode` for `language_code`.

        :return: a `CustomLanguageCode`, or None.
        """

    def createCustomLanguageCode(language_code, language):
        """Create `CustomLanguageCode`.

        :return: the new `CustomLanguageCode` object.
        """

    def removeCustomLanguageCode(language_code):
        """Remove `CustomLanguageCode`.
        
        :param language_code: A `CustomLanguageCode` object.
        """
