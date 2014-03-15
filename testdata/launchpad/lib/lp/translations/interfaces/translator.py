# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'IAdminTranslator',
    'IEditTranslator',
    'ITranslator',
    'ITranslatorSet',
    ]

from zope.interface import Interface
from zope.schema import (
    Choice,
    Datetime,
    Int,
    )

from lp import _
from lp.services.fields import (
    PublicPersonChoice,
    URIField,
    )


class IEditTranslator(Interface):
    """Set of translator attributes that the translator can edit himself as
    well as being editable by the translation group owner.

    Translators can edit the data in their `ITranslator` entry.
    Currently this is just the documentation URL.
    """

    style_guide_url = URIField(
        title=_('Translation guidelines'), required=False,
        allowed_schemes=['http', 'https', 'ftp'],
        allow_userinfo=False,
        description=_("The URL of the translation team guidelines "
                      "to be followed by this particular translation team. "
                      "Can be any of the http://, https://, or ftp:// links.")
        )


class IAdminTranslator(Interface):
    """Set of attributes that can only be edited by the owner of the
    translation group this translator is part of.

    These attributes let you add translators to translation groups and set
    the languages that the translators are responsible for. These are all
    administrative tasks.
    """

    id = Int(
            title=_('Translator ID'), required=True, readonly=True,
            )
    datecreated = Datetime(
            title=_('Date Appointed'), required=True, readonly=True,
            )
    translationgroup = Choice(title=_('Translation Group'), required=True,
        vocabulary='TranslationGroup', description=_("The translation group "
        "in which the translation team (individual supervisor) is being "
        "appointed."))
    language = Choice(title=_('Language'), required=True,
        vocabulary='Language', description=_("The language that this "
        "team or person will be responsible for."))
    translator = PublicPersonChoice(
        title=_('Translator'), required=True,
        vocabulary='ValidPersonOrTeam',
        description=_("The translation team (or individual supervisor) to "
            "be responsible for the language in this group."))


class ITranslator(IEditTranslator, IAdminTranslator):
    """A member of a `TranslationGroup`.

    This is the aggregation of all the attributes for a translator.

    This is not the same thing as what the UI calls a 'translator'. A
    translator there is any logged-in Launchpad user, since any such user can
    suggest or enter translation. An `ITranslator` is a person or team who
    coordinates translation work done in a language.
    """


class ITranslatorSet(Interface):
    """A container for `ITranslator`s."""

    def new(translationgroup, language, translator, style_guide_url):
        """Create a new `ITranslator` for a `TranslationGroup`."""

    def getByTranslator(translator):
        """Return all entries for a certain translator."""
