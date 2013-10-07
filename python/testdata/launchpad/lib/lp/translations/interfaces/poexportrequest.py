# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'IPOExportRequestSet',
    'IPOExportRequest'
    ]

from zope.interface import Interface
from zope.schema import (
    Datetime,
    Int,
    Object,
    )

from lp.registry.interfaces.person import IPerson
from lp.translations.interfaces.pofile import IPOFile
from lp.translations.interfaces.potemplate import IPOTemplate
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )


class IPOExportRequestSet(Interface):
    entry_count = Int(
        title=u'Number of entries waiting in the queue.',
        required=True, readonly=True)

    def estimateBacklog():
        """Return approximate age of oldest request on the export queue."""

    def addRequest(person, potemplates=None, pofiles=None,
                   format=TranslationFileFormat.PO):
        """Add a request to export a set of files.

        :param potemplates: PO template or list of PO templates to export, or
            `None`.
        :param pofiles: A list of PO files to export.
        """

    def getRequest():
        """Get the next request from the queue.

        Returns a tuple containing:
         * The person who made the request.
         * A list of POFiles and/or POTemplates that are to be exported.
         * The requested `TranslationFileFormat`.
         * The list of request record ids making up this request.

        The objects are all read-only objects from the slave store.  The
        request ids list should be passed to `removeRequest` when
        processing of the request completes.
        """

    def removeRequest(request_ids):
        """Remove a request off the queue.

        :param request_ids: A list of request record ids as returned by
            `getRequest`.
        """


class IPOExportRequest(Interface):
    person = Object(
        title=u'The person who made the request.',
        required=True, readonly=True, schema=IPerson)

    date_created = Datetime(
        title=u"Request's creation timestamp.", required=True, readonly=True)

    potemplate = Object(
        title=u'The translation template to which the requested file belong.',
        required=True, readonly=True, schema=IPOTemplate)

    pofile = Object(
        title=u'The translation file requested, if any.',
        required=True, readonly=True, schema=IPOFile)
