# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Common file format interfaces shared across all formats."""


from zope.interface import Interface
from zope.schema import (
    Bool,
    Choice,
    Datetime,
    Int,
    List,
    Object,
    Set,
    Text,
    TextLine,
    )

from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )


__metaclass__ = type

__all__ = [
    'ITranslationFileData',
    'ITranslationHeaderData',
    'ITranslationMessageData',
    'TranslationImportExportBaseException',
    ]


class TranslationImportExportBaseException(Exception):
    """Base exception for all import/export exceptions."""


class ITranslationHeaderData(Interface):
    """Translation header interface."""

    is_fuzzy = Bool(
        title=u'A flag indicating whether the header needs to be edited',
        required=True, readonly=True)

    template_creation_date = Datetime(
        title=u'When was created the template used in this file.',
        required=True, readonly=True)

    translation_revision_date = Datetime(
        title=u'When the translation resource was last revised or None.',
        required=True)

    language_team = TextLine(
        title=u'The language team in charge of this translation.',
        required=True, readonly=True)

    has_plural_forms = Bool(
        title=u'Whether this file contains plural forms.', required=True)

    number_plural_forms = Int(
        title=u'Number of plural forms.', required=True)

    plural_form_expression = TextLine(
        title=u'The plural form expression defined in this file or None.',
        required=True)

    charset = TextLine(
        title=u'Charset used to encode the content in its native form.',
        required=True)

    launchpad_export_date = Datetime(
        title=u'When this file was last exported from Launchpad or None.',
        required=True)

    comment = Text(
        title=u'Header comment',
        description=u'''
            It usually has copyright information and list of contributors.
            ''',
        required=True)

    def getRawContent():
        """Return header raw content in its native file format."""

    def updateFromTemplateHeader(template_header):
        """Update header with some content from the given template header.

        :param template_header: An `ITranslationHeaderData` for an
            `IPOTemplate`.

        The fields copied depend on the file format.
        """

    def getLastTranslator():
        """Return a tuple of name and email for last translator.

        name and/or email would be None if there is no such information.
        """

    def setLastTranslator(email, name=None):
        """Set last translator information.

        :param email: A string with the email address for last translator.
        :param name: The name for the last translator or None.
        """


class ITranslationMessageData(Interface):
    """Translation message interface."""

    context = Text(
        title=u'The context of the message.',
        required=True, readonly=True)

    msgid_singular = Text(
        title=u'The singular msgid of the message.', required=True,
        readonly=True)

    singular_text = Text(
        title=(
            u'The message singular text. Usually matches msgid_singular.'),
            required=False, readonly=True)

    msgid_plural = Text(
        title=u'The plural msgid of the message or None.',
        required=True, readonly=True)

    plural_text = Text(
        title=(
            u'The message plural text. Usually matches msgid_plural.'),
            required=False, readonly=True)

    translations = List(
        title=u'The translations of the message.', required=True,
        readonly=True)

    comment = Text(
        title=u'Comments added by a translator.', required=True,
        readonly=True)

    source_comment = Text(
        title=u'Comments added by the developer to help translators.',
        required=True, readonly=True)

    file_references = Text(
        title=u'File references from where this message was extracted."',
        required=True, readonly=True)

    flags = Set(
        title=u'Message flags needed to validate its translation.',
        required=True, readonly=True)

    is_obsolete = Bool(
        title=u"Is this message obsolete?", required=True, readonly=True)


class ITranslationFileData(Interface):
    """Parsed translation template file interface."""
    format = Choice(
        title=u"This file's translation file format.", required=True,
        vocabulary=TranslationFileFormat)

    header = Object(
        title=u'An `ITranslationHeaderData` for the parsed file.',
        required=True, schema=ITranslationHeaderData)

    messages = List(
        title=u'ITranslationMessageData objects included in the parsed file.',
        required=True, readonly=True)

    path = TextLine(
        title=u'The path directory where this file is stored.',
        required=True, readonly=True)

    translation_domain = TextLine(
        title=u'Translation domain used for this translation file',
        description=u'''
            It would be used to find its content on the file system, when
            its associated application is executed.
            ''',
        required=True, readonly=True)

    is_template = Bool(
        title=u"Is this entry a translation template?", required=True,
        readonly=True)

    language_code = TextLine(
        title=u'Language iso code for this translation file',
        description=u'''
            Language iso code for this translation file or None either if it's
            unknown or is_template flag is set.
            ''',
        required=True, readonly=True)

    syntax_warnings = Set(
        title=u"Syntax warnings", required=False, readonly=True)
