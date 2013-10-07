# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'XpiHeader',
    ]

try:
    import xml.etree.cElementTree as cElementTree
except ImportError:
    import cElementTree
from email.Utils import parseaddr
from StringIO import StringIO

from zope.interface import implements

from lp.translations.interfaces.translationcommonformat import (
    ITranslationHeaderData,
    )
from lp.translations.interfaces.translationimporter import (
    TranslationFormatInvalidInputError,
    TranslationFormatSyntaxError,
    )


class XpiHeader:
    implements(ITranslationHeaderData)

    def __init__(self, header_content):
        self._raw_content = header_content
        self.is_fuzzy = False
        self.template_creation_date = None
        self.translation_revision_date = None
        self.language_team = None
        self.has_plural_forms = False
        self.number_plural_forms = 0
        self.plural_form_expression = None
        self.charset = 'UTF-8'
        self.launchpad_export_date = None
        self.comment = None

        if isinstance(header_content, str):
            try:
                self._text = header_content.decode(self.charset)
            except UnicodeDecodeError:
                raise TranslationFormatInvalidInputError, (
                    "XPI header is not encoded in %s." % self.charset)
        else:
            assert isinstance(header_content, unicode), (
                "XPI header text is neither str nor unicode.")
            self._text = header_content

    def getRawContent(self):
        """See `ITranslationHeaderData`."""
        return self._text

    def updateFromTemplateHeader(self, template_header):
        """See `ITranslationHeaderData`."""
        # Nothing to do for this format.
        return

    def getLastTranslator(self):
        """See `ITranslationHeaderData`."""
        last_name, last_email = None, None
        contributor_tag = "{http://www.mozilla.org/2004/em-rdf#}contributor"
        # Both cElementTree and elementtree fail when trying to parse
        # proper unicode strings.  Use our raw input instead.
        try:
            parse = cElementTree.iterparse(StringIO(self._raw_content))
            for event, elem in parse:
                if elem.tag == contributor_tag:
                    # An XPI header can list multiple contributors, but
                    # here we care only about the latest one listed as a
                    # well-formed name and email address.
                    name, email = parseaddr(elem.text)
                    if name != '' and '@' in email:
                        last_name, last_email = name, email
        except SyntaxError as exception:
            raise TranslationFormatSyntaxError(
                filename='install.rdf', line_number=exception.lineno,
                message=exception.msg)

        return last_name, last_email

    def setLastTranslator(self, email, name=None):
        """Set last translator information.

        :param email: A string with the email address for last translator.
        :param name: The name for the last translator or None.
        """
        # Nothing to do for this format.
        return

