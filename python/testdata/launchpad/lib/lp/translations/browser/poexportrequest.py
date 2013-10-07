# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""View class for requesting translation exports."""

__metaclass__ = type
__all__ = ['BaseExportView']


from datetime import timedelta

from zope.component import getUtility

from lp import _
from lp.app.browser.tales import DurationFormatterAPI
from lp.services.propertycache import cachedproperty
from lp.services.webapp import (
    canonical_url,
    LaunchpadView,
    )
from lp.translations.interfaces.hastranslationtemplates import (
    IHasTranslationTemplates,
    )
from lp.translations.interfaces.poexportrequest import IPOExportRequestSet
from lp.translations.interfaces.translationexporter import (
    ITranslationExporter,
    )
from lp.translations.interfaces.translationfileformat import (
    TranslationFileFormat,
    )


class BaseExportView(LaunchpadView):
    """Base class for PO export views."""

    @cachedproperty
    def uses_translations(self):
        return self.context.has_current_translation_templates

    @property
    def export_queue_status(self):
        """Summary of queue status."""
        queue_size = self.request_set.entry_count
        estimated_backlog = self.request_set.estimateBacklog()

        size_text = self.describeQueueSize(queue_size)
        backlog_text = self.describeBacklog(estimated_backlog)

        return " ".join((size_text, backlog_text))

    def describeQueueSize(self, queue_size):
        """Return string describing the given queue size."""
        if queue_size == 0:
            return "The export queue is currently empty."
        elif queue_size == 1:
            return "There is 1 file request on the export queue."
        else:
            return (
                "There are %d file requests on the export queue."
                % queue_size)

    def describeBacklog(self, estimated_backlog):
        """Return string describing the current export backlog."""
        threshold = timedelta(minutes=10)
        if estimated_backlog is None or estimated_backlog < threshold:
            return ""

        formatter = DurationFormatterAPI(estimated_backlog)
        time_string = formatter.approximateduration()
        return "The backlog is approximately %s." % time_string

    def getDefaultFormat(self):
        """Overridable: return default file format to use for the export."""
        if not IHasTranslationTemplates.providedBy(self.context):
            raise NotImplementedError(
                'Subclass not implementing `IHasTranslationsTemplates` '
                'interface.  Either override getDefaultFormat implementation '
                'or implement `IHasTranslationsTemplates`.')

        templates = self.context.getCurrentTranslationTemplates()
        if not bool(templates.any()):
            return None
        formats = self.context.getTranslationTemplateFormats()
        format = formats[0]
        if len(formats) > 1:
            self.request.response.addInfoNotification(
                "This package has templates with different native "
                "file formats.  If you proceed, all translations will be "
                "exported in the single format you specify.")
        return format

    def processForm(self):
        """Return templates and translations requested to be exported.

        Overridable in a child class.  Must do one of:
        a. Add an error notification to the page and return `None`
        b. Return a tuple of two iterables or None, of requested templates
           and of requested pofiles IDs.
        c. Redirect and return `None`.
        """
        if not IHasTranslationTemplates.providedBy(self.context):
            raise NotImplementedError(
                'Subclass not implementing `IHasTranslationsTemplates` '
                'interface.  Either override getDefaultFormat implementation '
                'or implement `IHasTranslationsTemplates`.')

        translation_templates_ids = (
            self.context.getCurrentTranslationTemplates(just_ids=True))
        pofiles_ids = self.context.getCurrentTranslationFiles(just_ids=True)
        if not bool(pofiles_ids.any()):
            pofiles_ids = None
        return (translation_templates_ids, pofiles_ids)

    def getExportFormat(self):
        """Optional overridable: The requested export format."""
        return self.request.form.get("format")

    def initialize(self):
        self.request_set = getUtility(IPOExportRequestSet)

        # Ask our derived class to figure out the default file format for this
        # export.  We do that here because the method may issue warnings,
        # which must be attached to our response early on.
        self.default_format = self.getDefaultFormat()

        if self.request.method != "POST":
            return

        bad_format_message = _("Please select a valid format for download.")
        format_name = self.getExportFormat()
        if format_name is None:
            self.request.response.addErrorNotification(bad_format_message)
            return
        try:
            format = TranslationFileFormat.items[format_name]
        except KeyError:
            self.request.response.addErrorNotification(bad_format_message)
            return

        requested_files = self.processForm()
        if requested_files is None:
            return

        templates, pofiles = requested_files
        if not templates and not pofiles:
            self.request.response.addErrorNotification(
                "Please select at least one translation or template.")
        else:
            self.request_set.addRequest(self.user, templates, pofiles, format)
            self.nextURL()

    def nextURL(self):
        self.request.response.addInfoNotification(_(
            "Your request has been received. Expect to receive an email "
            "shortly."))
        self.request.response.redirect(
            canonical_url(self.context, rootsite='translations'))

    def formats(self):
        """Return a list of formats available for translation exports."""

        class BrowserFormat:

            def __init__(self, title, value, is_default=False):
                self.title = title
                self.value = value
                self.is_default = is_default

        translation_exporter = getUtility(ITranslationExporter)
        exporters = translation_exporter.getExportersForSupportedFileFormat(
            self.default_format)
        for exporter in exporters:
            format = exporter.format
            if format == self.default_format:
                is_default = True
            else:
                is_default = False
            yield BrowserFormat(format.title, format.name, is_default)
