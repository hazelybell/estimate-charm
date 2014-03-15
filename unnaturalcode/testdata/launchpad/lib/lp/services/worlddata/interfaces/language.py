# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Language interfaces."""

__metaclass__ = type

__all__ = [
    'ILanguage',
    'ILanguageSet',
    'TextDirection',
    ]

from lazr.enum import (
    DBEnumeratedType,
    DBItem,
    )
from lazr.lifecycle.snapshot import doNotSnapshot
from lazr.restful.declarations import (
    call_with,
    collection_default_content,
    export_as_webservice_collection,
    export_as_webservice_entry,
    export_read_operation,
    exported,
    operation_returns_collection_of,
    )
from zope.interface import (
    Attribute,
    Interface,
    )
from zope.interface.exceptions import Invalid
from zope.interface.interface import invariant
from zope.schema import (
    Bool,
    Choice,
    Field,
    Int,
    Set,
    TextLine,
    )


class TextDirection(DBEnumeratedType):
    """The base text direction for a language."""

    LTR = DBItem(0, """
        Left to Right

        Text is normally written from left to right in this language.
        """)

    RTL = DBItem(1, """
        Right to Left

        Text is normally written from left to right in this language.
        """)


class ILanguage(Interface):
    """A Language."""
    export_as_webservice_entry()

    id = Attribute("This Language ID.")

    code = exported(TextLine(
        title=u'The ISO 639 code',
        required=True))

    englishname = exported(
        TextLine(
            title=u'The English name',
            required=True),
        exported_as='english_name')

    nativename = TextLine(
        title=u'Native name',
        description=u'The name of this language in the language itself.',
        required=False)

    pluralforms = exported(
        Int(
            title=u'Number of plural forms',
            description=u'The number of plural forms this language has.',
            required=False),
        exported_as='plural_forms')

    guessed_pluralforms = Int(
        title=u"Number of plural forms, or a reasonable guess",
        required=False, readonly=True)

    pluralexpression = exported(
        TextLine(
            title=u'Plural form expression',
            description=(u'The expression that relates a number of items'
                         u' to the appropriate plural form.'),
            required=False),
        exported_as='plural_expression')

    translators = doNotSnapshot(Field(
        title=u'List of Person/Team that translate into this language.',
        required=True))

    translators_count = exported(
        Int(
            title=u"Total number of translators for this language.",
            readonly=True))

    translation_teams = Field(
        title=u'List of Teams that translate into this language.',
        required=True)

    countries = Set(
        title=u'Spoken in',
        description=u'List of countries this language is spoken in.',
        required=True,
        value_type=Choice(vocabulary="CountryName"))

    def addCountry(country):
        """Add a country to a list of countries this language is spoken in.

        Provided by SQLObject.
        """

    def removeCountry(country):
        """Remove country from list of countries this language is spoken in.

        Provided by SQLObject.
        """

    visible = exported(
        Bool(
            title=u'Visible',
            description=(
                u'Whether this language is visible by default.'),
            required=True))

    direction = exported(
        Choice(
            title=u'Text direction',
            description=u'The direction of text in this language.',
            required=True,
            vocabulary=TextDirection),
        exported_as='text_direction')

    displayname = TextLine(
        title=u'The displayname of the language',
        required=True,
        readonly=True)

    alt_suggestion_language = Attribute("A language which can reasonably "
        "be expected to have good suggestions for translations in this "
        "language.")

    dashedcode = TextLine(
        title=(u'The language code in a form suitable for use in HTML and'
               u' XML files.'),
        required=True,
        readonly=True)

    abbreviated_text_dir = TextLine(
        title=(u'The abbreviated form of the text direction, suitable'
               u' for use in HTML files.'),
        required=True,
        readonly=True)

    @invariant
    def validatePluralData(form_language):
        pair = (form_language.pluralforms, form_language.pluralexpression)
        if None in pair and pair != (None, None):
            raise Invalid(
                'The number of plural forms and the plural form expression '
                'must be set together, or not at all.')


class ILanguageSet(Interface):
    """The collection of languages.

    The standard get method will return only the visible languages.
    If you want to access all languages known to Launchpad, use
    the getAllLanguages method.
    """

    export_as_webservice_collection(ILanguage)

    @export_read_operation()
    @operation_returns_collection_of(ILanguage)
    @call_with(want_translators_count=True)
    def getAllLanguages(want_translators_count=False):
        """Return a result set of all ILanguages from Launchpad."""

    @collection_default_content(want_translators_count=True)
    def getDefaultLanguages(want_translators_count=False):
        """An API wrapper for `common_languages`"""

    common_languages = Attribute(
        "An iterator over languages that are not hidden.")

    def __iter__():
        """Returns an iterator over all languages."""

    def __getitem__(code):
        """Return the language with the given code.

        If there is no language with the give code,
        raise NotFoundError exception.
        """

    def get(language_id):
        """Return the language with the given id."""

    def getLanguageByCode(code):
        """Return the language with the given code or None."""

    def keys():
        """Return an iterator over the language codes."""

    def canonicalise_language_code(code):
        """Convert a language code to standard xx_YY form."""

    def codes_to_languages(codes):
        """Convert a list of ISO language codes to language objects.

        Unrecognised language codes are ignored.
        """

    def createLanguage(code, englishname, nativename=None, pluralforms=None,
                       pluralexpression=None, visible=True,
                       direction=TextDirection.LTR):
        """Return a new created language.

        :arg code: ISO 639 language code.
        :arg englishname: English name for the new language.
        :arg nativename: Native language name.
        :arg pluralforms: Number of plural forms.
        :arg pluralexpression: Plural form expression.
        :arg visible: Whether this language should be showed by default.
        :arg direction: Text direction, either 'left to right' or 'right to
            left'.
        """

    def search(text):
        """Return a result set of ILanguage that match the search."""
