# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

__all__ = [
    'ProductReleaseAddDownloadFileView',
    'ProductReleaseAddView',
    'ProductReleaseFromSeriesAddView',
    'ProductReleaseContextMenu',
    'ProductReleaseDeleteView',
    'ProductReleaseEditView',
    'ProductReleaseNavigation',
    'ProductReleaseRdfView',
    ]

import mimetypes

from lazr.restful.interface import copy_field
from lazr.restful.utils import smartquote
from z3c.ptcompat import ViewPageTemplateFile
from zope.event import notify
from zope.formlib.form import FormFields
from zope.formlib.widgets import (
    TextAreaWidget,
    TextWidget,
    )
from zope.lifecycleevent import ObjectCreatedEvent
from zope.schema import Bool
from zope.schema.vocabulary import (
    SimpleTerm,
    SimpleVocabulary,
    )

from lp import _
from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadEditFormView,
    LaunchpadFormView,
    )
from lp.app.widgets.date import DateTimeWidget
from lp.registry.browser import (
    BaseRdfView,
    MilestoneOverlayMixin,
    RegistryDeleteViewMixin,
    )
from lp.registry.interfaces.productrelease import (
    IProductRelease,
    IProductReleaseFileAddForm,
    )
from lp.services.webapp import (
    canonical_url,
    ContextMenu,
    enabled_with_permission,
    Link,
    Navigation,
    stepthrough,
    )


class ProductReleaseNavigation(Navigation):

    usedfor = IProductRelease

    @stepthrough('+download')
    def download(self, name):
        return self.context.getFileAliasByName(name)

    @stepthrough('+file')
    def fileaccess(self, name):
        return self.context.getProductReleaseFileByName(name)


class ProductReleaseContextMenu(ContextMenu):

    usedfor = IProductRelease
    links = ('edit', 'add_file', 'download', 'delete')

    @enabled_with_permission('launchpad.Edit')
    def edit(self):
        text = 'Change release details'
        summary = "Edit this release"
        return Link('+edit', text, summary=summary, icon='edit')

    @enabled_with_permission('launchpad.Edit')
    def delete(self):
        text = 'Delete release'
        summary = "Delete release"
        return Link('+delete', text, summary=summary, icon='remove')

    @enabled_with_permission('launchpad.Edit')
    def add_file(self):
        text = 'Add download file'
        return Link('+adddownloadfile', text, icon='add')

    def download(self):
        text = 'Download RDF metadata'
        return Link('+rdf', text, icon='download')


class ProductReleaseAddViewBase(LaunchpadFormView):
    """Base class for creating a release from an existing or new milestone.

    Subclasses need to define the field_names a form action.
    """
    schema = IProductRelease

    custom_widget('datereleased', DateTimeWidget)
    custom_widget('release_notes', TextAreaWidget, height=7, width=62)
    custom_widget('changelog', TextAreaWidget, height=7, width=62)

    def _prependKeepMilestoneActiveField(self):
        keep_milestone_active_checkbox = FormFields(
            Bool(
                __name__='keep_milestone_active',
                title=_("Keep the %s milestone active." % self.context.name),
                description=_(
                    "Only select this if bugs or blueprints still need "
                    "to be targeted to this project release's milestone.")),
            render_context=self.render_context)
        self.form_fields = keep_milestone_active_checkbox + self.form_fields

    def _createRelease(self, milestone, data):
        """Create product release for this milestone."""
        newrelease = milestone.createProductRelease(
            self.user, changelog=data['changelog'],
            release_notes=data['release_notes'],
            datereleased=data['datereleased'])
        # Set Milestone.active to false, since bugs & blueprints
        # should not be targeted to a milestone in the past.
        if data.get('keep_milestone_active') is False:
            milestone.active = False
        self.next_url = canonical_url(newrelease.milestone)
        notify(ObjectCreatedEvent(newrelease))

    @property
    def label(self):
        """The form label."""
        return smartquote('Create a new release for %s' %
                          self.context.product.displayname)

    page_title = label

    @property
    def cancel_url(self):
        return canonical_url(self.context)


class ProductReleaseAddView(ProductReleaseAddViewBase):
    """Create a product release.

    Also, deactivate the milestone it is attached to.
    """

    field_names = [
        'datereleased',
        'release_notes',
        'changelog',
        ]

    def initialize(self):
        if self.context.product_release is not None:
            self.request.response.addErrorNotification(
                _("A project release already exists for this milestone."))
            self.request.response.redirect(
                canonical_url(self.context.product_release) + '/+edit')
        else:
            super(ProductReleaseAddView, self).initialize()

    def setUpFields(self):
        super(ProductReleaseAddView, self).setUpFields()
        if self.context.active is True:
            self._prependKeepMilestoneActiveField()

    @action(_('Create release'), name='create')
    def createRelease(self, action, data):
        self._createRelease(self.context, data)


class ProductReleaseFromSeriesAddView(ProductReleaseAddViewBase,
                                      MilestoneOverlayMixin):
    """Create a product release from an existing or new milestone.

    Also, deactivate the milestone it is attached to.
    """

    field_names = [
        'datereleased',
        'release_notes',
        'changelog',
        ]

    def setUpFields(self):
        super(ProductReleaseFromSeriesAddView, self).setUpFields()
        self._prependKeepMilestoneActiveField()
        self._prependMilestoneField()

    def _prependMilestoneField(self):
        """Add Milestone Choice field with custom terms."""
        terms = [
            SimpleTerm(milestone, milestone.name, milestone.name)
            for milestone in self.context.all_milestones
            if milestone.product_release is None]
        terms.insert(0, SimpleTerm(None, None, '- Select Milestone -'))
        milestone_field = FormFields(
            copy_field(
                IProductRelease['milestone'],
                __name__='milestone_for_release',
                vocabulary=SimpleVocabulary(terms)))
        self.form_fields = milestone_field + self.form_fields

    @action(_('Create release'), name='create')
    def createRelease(self, action, data):
        milestone = data['milestone_for_release']
        self._createRelease(milestone, data)


class ProductReleaseEditView(LaunchpadEditFormView):
    """Edit view for ProductRelease objects"""

    schema = IProductRelease
    field_names = [
        "datereleased",
        "release_notes",
        "changelog",
        ]

    custom_widget('datereleased', DateTimeWidget)
    custom_widget('release_notes', TextAreaWidget, height=7, width=62)
    custom_widget('changelog', TextAreaWidget, height=7, width=62)

    @property
    def label(self):
        """The form label."""
        return smartquote('Edit %s release details' % self.context.title)

    page_title = label

    @action('Change', name='change')
    def change_action(self, action, data):
        self.updateContextFromData(data)
        self.next_url = canonical_url(self.context)

    @property
    def cancel_url(self):
        return canonical_url(self.context)


class ProductReleaseRdfView(BaseRdfView):
    """A view that sets its mime-type to application/rdf+xml"""

    template = ViewPageTemplateFile('../templates/productrelease-rdf.pt')

    @property
    def filename(self):
        return '%s-%s-%s.rdf' % (
            self.context.product.name,
            self.context.productseries.name,
            self.context.version)


class ProductReleaseAddDownloadFileView(LaunchpadFormView):
    """A view for adding a file to an `IProductRelease`."""
    schema = IProductReleaseFileAddForm

    custom_widget('description', TextWidget, displayWidth=60)

    @property
    def label(self):
        """The form label."""
        return smartquote('Add a download file to %s' % self.context.title)

    page_title = label

    def validate(self, data):
        """See `LaunchpadFormView`."""
        if not self.context.can_have_release_files:
            self.addError('Only public projects can have download files.')
        file_name = None
        filecontent = self.request.form.get(self.widgets['filecontent'].name)
        if filecontent:
            file_name = filecontent.filename
        if file_name and self.context.hasReleaseFile(file_name):
            self.setFieldError(
                'filecontent',
                u"The file '%s' is already uploaded." % file_name)

    @action('Upload', name='add')
    def add_action(self, action, data):
        form = self.request.form
        file_upload = form.get(self.widgets['filecontent'].name)
        signature_upload = form.get(self.widgets['signature'].name)
        filetype = data['contenttype']
        # XXX: BradCrittenden 2007-04-26 bug=115215 Write a proper upload
        # widget.
        if file_upload is not None and len(data['description']) > 0:
            # XXX Edwin Grubbs 2008-09-10 bug=268680
            # Once python-magic is available on the production servers,
            # the content-type should be verified instead of trusting
            # the extension that mimetypes.guess_type() examines.
            content_type, encoding = mimetypes.guess_type(
                file_upload.filename)

            if content_type is None:
                content_type = "text/plain"

            # signature_upload is u'' if no file is specified in
            # the browser.
            if signature_upload:
                signature_filename = signature_upload.filename
                signature_content = data['signature']
            else:
                signature_filename = None
                signature_content = None

            release_file = self.context.addReleaseFile(
                filename=file_upload.filename,
                file_content=data['filecontent'],
                content_type=content_type,
                uploader=self.user,
                signature_filename=signature_filename,
                signature_content=signature_content,
                file_type=filetype,
                description=data['description'])

            self.request.response.addNotification(
                "Your file '%s' has been uploaded."
                % release_file.libraryfile.filename)

        self.next_url = canonical_url(self.context)

    @property
    def cancel_url(self):
        return canonical_url(self.context)


class ProductReleaseDeleteView(LaunchpadFormView, RegistryDeleteViewMixin):
    """A view for deleting an `IProductRelease`."""
    schema = IProductRelease
    field_names = []

    @property
    def label(self):
        """The form label."""
        return smartquote('Delete %s' % self.context.title)

    page_title = label

    @action('Delete Release', name='delete')
    def delete_action(self, action, data):
        series = self.context.productseries
        version = self.context.version
        self._deleteRelease(self.context)
        self.request.response.addInfoNotification(
            "Release %s deleted." % version)
        self.next_url = canonical_url(series)

    @property
    def cancel_url(self):
        return canonical_url(self.context)
