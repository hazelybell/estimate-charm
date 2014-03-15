# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'ExportResult',
    'process_queue',
    ]

import os
from StringIO import StringIO
import traceback

import psycopg2
from zope.component import (
    getAdapter,
    getUtility,
    )

from lp.registry.interfaces.productseries import IProductSeries
from lp.registry.interfaces.sourcepackage import ISourcePackage
from lp.services.config import config
from lp.services.database.policy import SlaveOnlyDatabasePolicy
from lp.services.librarian.interfaces import ILibraryFileAliasSet
from lp.services.mail.helpers import (
    get_contact_email_addresses,
    get_email_template,
    )
from lp.services.mail.sendmail import simple_sendmail
from lp.services.webapp import canonical_url
from lp.translations.interfaces.poexportrequest import IPOExportRequestSet
from lp.translations.interfaces.pofile import IPOFile
from lp.translations.interfaces.potemplate import IPOTemplate
from lp.translations.interfaces.translationcommonformat import (
    ITranslationFileData,
    )
from lp.translations.interfaces.translationexporter import (
    ITranslationExporter,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )


class ExportResult:
    """The results of a translation export request.

    This class has three main attributes:

     - person: The person requesting this export.
     - url: The Librarian URL for any successfully exported files.
     - failure: Failure gotten while exporting.
    """

    def __init__(self, person, requested_exports, logger):
        self.person = person
        self.url = None
        self.failure = None
        self.logger = logger
        self.exported_file = None

        self.requested_exports = list(requested_exports)
        export_requested_at = self._getExportRequestOrigin()
        self.name = self._getShortRequestName(export_requested_at)

        self.request_url = canonical_url(
            export_requested_at,
            rootsite='translations') + '/+export'

    def _getShortRequestName(self, request):
        """Return a short request name for use in email subjects."""
        if IPOFile.providedBy(request):
            title = '%s translation of %s' % (
                request.language.englishname,
                request.potemplate.name)
            productseries = request.potemplate.productseries
            distroseries = request.potemplate.distroseries
            sourcepackagename = request.potemplate.sourcepackagename
        elif IPOTemplate.providedBy(request):
            title = '%s template' % (request.name)
            productseries = request.productseries
            distroseries = request.distroseries
            sourcepackagename = request.sourcepackagename
        elif IProductSeries.providedBy(request):
            title = None
            productseries = request
            distroseries = None
            sourcepackagename = None
        elif ISourcePackage.providedBy(request):
            title = None
            productseries = None
            distroseries = request.distroseries
            sourcepackagename = request.sourcepackagename
        else:
            raise AssertionError(
                "We can not figure out short name for this translation "
                "export origin.")

        if productseries is not None:
            root = '%s %s' % (
                productseries.product.displayname,
                productseries.name)
        else:
            root = '%s %s %s' % (
                distroseries.distribution.displayname,
                distroseries.displayname,
                sourcepackagename.name)
        if title is not None:
            return '%s - %s' % (root, title)
        else:
            return root

    def _getExportRequestOrigin(self):
        """Figure out where an export request was made."""
        # Determine all objects that export request could have
        # originated on.
        export_requested_at = None
        pofiles = set()
        implicit_potemplates = set()
        direct_potemplates = set()
        productseries = set()
        sourcepackages = set()

        last_template_name = None
        for request in self.requested_exports:
            if IPOTemplate.providedBy(request):
                # If we are exporting a template, add it to
                # the list of directly requested potemplates.
                potemplate = request
                direct_potemplates.add(potemplate)
            else:
                # Otherwise, we are exporting a POFile.
                potemplate = request.potemplate
                implicit_potemplates.add(potemplate)
                pofiles.add(request)
            if potemplate.displayname != last_template_name:
                self.logger.debug(
                    'Exporting objects for %s, related to template %s'
                    % (self.person.displayname, potemplate.displayname))
                last_template_name = potemplate.displayname

            # Determine productseries or sourcepackage for any
            # productseries/sourcepackage an export was requested at.
            if potemplate.productseries is not None:
                productseries.add(potemplate.productseries)
            elif potemplate.sourcepackagename is not None:
                sourcepackage = potemplate.distroseries.getSourcePackage(
                    potemplate.sourcepackagename)
                sourcepackages.add(sourcepackage)
            else:
                raise AssertionError(
                    "Requesting a translation export which belongs to "
                    "neither a ProductSeries nor a SourcePackage.")

        if len(pofiles) == 1 and len(direct_potemplates) == 0:
            # One POFile was requested.
            export_requested_at = pofiles.pop()
        elif len(pofiles) == 0 and len(direct_potemplates) == 1:
            # A POTemplate was requested.
            export_requested_at = direct_potemplates.pop()
        elif len(pofiles) + len(direct_potemplates) >= 2:
            # More than one file was requested.
            all_potemplates = implicit_potemplates.union(direct_potemplates)
            if len(all_potemplates) == 1:
                # It's all part of a single POTemplate.
                export_requested_at = all_potemplates.pop()
            else:
                # More than one POTemplate: request was made on
                # either ProductSeries or SourcePackage.
                if len(sourcepackages) > 0:
                    export_requested_at = sourcepackages.pop()
                elif len(productseries) > 0:
                    export_requested_at = productseries.pop()

        if IPOTemplate.providedBy(export_requested_at):
            if len(sourcepackages) > 0:
                container = sourcepackages.pop()
            elif len(productseries) > 0:
                container = productseries.pop()
            else:
                raise AssertionError(
                    "Requesting a translation export which belongs to "
                    "neither a ProductSeries nor a SourcePackage.")
            if container.getCurrentTranslationTemplates().count() == 1:
                export_requested_at = container

        return export_requested_at

    def _getRequestedExportsNames(self):
        """Return a list of display names for requested exports."""
        requested_names = []
        for translation_object in self.requested_exports:
            if IPOTemplate.providedBy(translation_object):
                request_name = translation_object.displayname
            else:
                request_name = translation_object.title
            requested_names.append(request_name)

        return requested_names

    def _getFailureEmailBody(self):
        """Send an email notification about the export failing."""
        template = get_email_template(
            'poexport-failure.txt', 'translations')
        return template % {
            'person': self.person.displayname,
            'request_url': self.request_url,
            }

    def _getFailedRequestsDescription(self):
        """Return a printable description of failed export requests."""
        failed_requests = self._getRequestedExportsNames()
        if len(failed_requests) > 0:
            failed_requests_text = 'Failed export request included:\n'
            failed_requests_text += '\n'.join(
                '  * ' + request for request in failed_requests)
        else:
            failed_requests_text = 'There were no export requests.'
        return failed_requests_text

    def _getAdminFailureNotificationEmailBody(self):
        """Send an email notification about failed export to admins."""
        template = get_email_template(
            'poexport-failure-admin-notification.txt', 'translations')
        failed_requests = self._getFailedRequestsDescription()
        return template % {
            'person': self.person.displayname,
            'person_id': self.person.name,
            'request_url': self.request_url,
            'failure_message': self.failure,
            'failed_requests': failed_requests,
            }

    def _getUnicodeDecodeErrorEmailBody(self):
        """Send an email notification to admins about UnicodeDecodeError."""
        template = get_email_template(
            'poexport-failure-unicodedecodeerror.txt',
            'translations')
        failed_requests = self._getFailedRequestsDescription()
        return template % {
            'person': self.person.displayname,
            'person_id': self.person.name,
            'request_url': self.request_url,
            'failed_requests': failed_requests,
            }

    def _getSuccessEmailBody(self):
        """Send an email notification about the export working."""
        template = get_email_template(
            'poexport-success.txt', 'translations')
        return template % {
            'person': self.person.displayname,
            'download_url': self.url,
            'request_url': self.request_url,
            }

    def setExportFile(self, exported_file):
        """Attach an exported file to the result, for upload to the Librarian.

        After this is set, `upload` will perform the actual upload.  The two
        actions are separated so as to isolate write access to the database.

        :param exported_file: An `IExportedTranslationFile` containing the
            exported data.
        """
        self.exported_file = exported_file

    def upload(self, logger=None):
        """Upload exported file as set with `setExportFile` to the Librarian.

        If no file has been set, do nothing.
        """
        if self.exported_file is None:
            # There's nothing to upload.
            return

        if self.exported_file.path is None:
            # The exported path is unknown, use translation domain as its
            # filename.
            assert self.exported_file.file_extension, (
                'File extension must have a value!.')
            path = 'launchpad-export.%s' % self.exported_file.file_extension
        else:
            # Convert the path to a single file name so it's noted in
            # librarian.
            path = self.exported_file.path.replace(os.sep, '_')

        alias_set = getUtility(ILibraryFileAliasSet)
        alias = alias_set.create(
            name=path, size=self.exported_file.size, file=self.exported_file,
            contentType=self.exported_file.content_type)

        self.url = alias.http_url
        if logger is not None:
            logger.info("Stored file at %s" % self.url)

    def notify(self):
        """Send a notification email to the given person about the export.

        If there is a failure, a copy of the email is also sent to the
        Launchpad error mailing list for debugging purposes.
        """
        if self.failure is None and self.url is not None:
            # There is no failure, so we have a full export without
            # problems.
            body = self._getSuccessEmailBody()
        elif self.failure is not None and self.url is None:
            body = self._getFailureEmailBody()
        elif self.failure is not None and self.url is not None:
            raise AssertionError(
                'We cannot have a URL for the export and a failure.')
        else:
            raise AssertionError('On success, an exported URL is expected.')

        recipients = list(get_contact_email_addresses(self.person))

        for recipient in [str(recipient) for recipient in recipients]:
            simple_sendmail(
                from_addr=config.rosetta.notification_address,
                to_addrs=[recipient],
                subject='Launchpad translation download: %s' % self.name,
                body=body)

        if self.failure is None:
            # There are no errors, so nothing else to do here.
            return

        # The export process had errors that we should notify admins about.
        try:
            admins_email_body = self._getAdminFailureNotificationEmailBody()
        except UnicodeDecodeError:
            # Unfortunately this happens sometimes: invalidly-encoded data
            # makes it into the exception description, possibly from error
            # messages printed by msgfmt.  Before we can fix that, we need to
            # know what exports suffer from this problem.
            admins_email_body = self._getUnicodeDecodeErrorEmailBody()

        simple_sendmail(
            from_addr=config.rosetta.notification_address,
            to_addrs=[config.launchpad.errors_address],
            subject=(
                'Launchpad translation download errors: %s' % self.name),
            body=admins_email_body)

    def addFailure(self):
        """Store an exception that broke the export."""
        # Get the trace back that produced this failure.
        exception = StringIO()
        traceback.print_exc(file=exception)
        exception.seek(0)
        # And store it.
        self.failure = exception.read()


def generate_translationfiledata(file_list, format):
    """Generate `TranslationFileData` objects for POFiles/templates in list.

    This builds each `TranslationFileData` in memory only when it's needed, so
    the memory usage for an export doesn't accumulate.
    """
    if format == TranslationFileFormat.POCHANGED:
        adaptername = 'changed_messages'
    else:
        adaptername = 'all_messages'

    for file in file_list:
        yield getAdapter(file, ITranslationFileData, adaptername)


def process_request(person, objects, format, logger):
    """Process a request for an export of Launchpad translation files.

    After processing the request a notification email is sent to the requester
    with the URL to retrieve the file (or the tarball, in case of a request of
    multiple files) and information about files that we failed to export (if
    any).
    """
    # Keep as much work off the master store as possible, so we avoid
    # opening unnecessary transactions there.  It could be a while
    # before we get to the commit.
    translation_exporter = getUtility(ITranslationExporter)
    requested_objects = list(objects)

    result = ExportResult(person, requested_objects, logger)

    try:
        exported_file = translation_exporter.exportTranslationFiles(
            generate_translationfiledata(requested_objects, format),
            target_format=format)
    except (KeyboardInterrupt, SystemExit):
        # We should never catch KeyboardInterrupt or SystemExit.
        raise
    except psycopg2.Error:
        # It's a DB exception, we don't catch it either, the export
        # should be done again in a new transaction.
        raise
    except:
        # The export for the current entry failed with an unexpected
        # error, we add the entry to the list of errors.
        result.addFailure()
    else:
        result.setExportFile(exported_file)

    return result


def process_queue(transaction_manager, logger):
    """Process all requests in the translation export queue.

    Each item is removed from the queue as it is processed.
    """
    request_set = getUtility(IPOExportRequestSet)
    no_request = (None, None, None, None)

    request = request_set.getRequest()
    while request != no_request:

        # This can take a long time.  Make sure we don't open any
        # transactions on the master store before we really need to.
        transaction_manager.commit()
        with SlaveOnlyDatabasePolicy():
            person, objects, format, request_ids = request
            result = process_request(person, objects, format, logger)

        # Almost done.  Now we can go back to using the master database
        # where needed.
        result.upload(logger=logger)
        result.notify()

        request_set.removeRequest(request_ids)
        transaction_manager.commit()

        request = request_set.getRequest()
