# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Bug attachment views."""

__metaclass__ = type
__all__ = [
    'BugAttachmentContentCheck',
    'BugAttachmentFileNavigation',
    'BugAttachmentSetNavigation',
    'BugAttachmentEditView',
    'BugAttachmentURL',
    ]

from lazr.restful.utils import smartquote
from zope.component import (
    getMultiAdapter,
    getUtility,
    )
from zope.contenttype import guess_content_type
from zope.interface import implements

from lp.app.browser.launchpadform import (
    action,
    custom_widget,
    LaunchpadFormView,
    )
from lp.app.widgets.itemswidgets import LaunchpadBooleanRadioWidget
from lp.bugs.interfaces.bugattachment import (
    BugAttachmentType,
    IBugAttachment,
    IBugAttachmentEditForm,
    IBugAttachmentIsPatchConfirmationForm,
    IBugAttachmentSet,
    )
from lp.services.librarian.browser import (
    FileNavigationMixin,
    ProxiedLibraryFileAlias,
    )
from lp.services.librarian.interfaces import ILibraryFileAliasWithParent
from lp.services.webapp import (
    canonical_url,
    GetitemNavigation,
    Navigation,
    )
from lp.services.webapp.escaping import structured
from lp.services.webapp.interfaces import (
    ICanonicalUrlData,
    ILaunchBag,
    )


class BugAttachmentContentCheck:
    """A mixin class that checks the consistency of patch flag and file type.
    """

    def guessContentType(self, filename, file_content):
        """Guess the content type a file with the given name and content."""
        guessed_type, encoding = guess_content_type(
            name=filename, body=file_content)
        # Zope's guess_content_type() doesn't consider all the factors
        # we want considered.  So after we get its answer, we probe a
        # little further.  But we still don't look at the encoding nor
        # the file content, because we'd like to avoid reimplementing
        # 'patch'.  See bug #538219 for more.
        if (guessed_type == 'text/plain'
            and (filename.endswith('.diff')
                 or filename.endswith('.debdiff')
                 or filename.endswith('.patch'))):
            guessed_type = 'text/x-diff'
        return guessed_type

    def attachmentTypeConsistentWithContentType(
        self, patch_flag_set, filename, file_content):
        """Return True iff patch_flag is consistent with filename and content.
        """
        guessed_type = self.guessContentType(filename, file_content)
        # An XOR of "is the patch flag selected?" with "is the
        # guessed type not a diff?" tells us if the type selected
        # by the user matches the guessed type.
        return (patch_flag_set ^ (guessed_type != 'text/x-diff'))

    def nextUrlForInconsistentPatchFlags(self, attachment):
        """The next_url value used for an inconistent patch flag."""
        return canonical_url(attachment) + '/+confirm-is-patch'


class BugAttachmentSetNavigation(GetitemNavigation):

    usedfor = IBugAttachmentSet


# Despite declaring compliance with ICanonicalUrlData, the LaunchBag
# dependency means this tends towards the "not canonical at all" end of
# the canonicalness scale. Beware.
class BugAttachmentURL:
    """Bug URL creation rules."""
    implements(ICanonicalUrlData)

    rootsite = 'bugs'

    def __init__(self, context):
        self.context = context

    @property
    def inside(self):
        """Always relative to a traversed bugtask."""
        bugtask = getUtility(ILaunchBag).bugtask
        if bugtask is None:
            return self.context.bug
        else:
            return bugtask

    @property
    def path(self):
        """Return the path component of the URL."""
        return u"+attachment/%d" % self.context.id


class BugAttachmentEditView(LaunchpadFormView, BugAttachmentContentCheck):
    """Edit a bug attachment."""

    schema = IBugAttachmentEditForm
    field_names = ['title', 'patch', 'contenttype']

    def __init__(self, context, request):
        LaunchpadFormView.__init__(self, context, request)
        self.next_url = self.cancel_url = (
            canonical_url(ICanonicalUrlData(context).inside))

    @property
    def initial_values(self):
        attachment = self.context
        return dict(
            title=attachment.title,
            patch=attachment.type == BugAttachmentType.PATCH,
            contenttype=attachment.libraryfile.mimetype)

    @action('Change', name='change')
    def change_action(self, action, data):
        if data['patch']:
            new_type = BugAttachmentType.PATCH
        else:
            new_type = BugAttachmentType.UNSPECIFIED
        if new_type != self.context.type:
            filename = self.context.libraryfile.filename
            file_content = self.context.libraryfile.read()
            # We expect that users set data['patch'] to True only for
            # real patch data, indicated by guessed_content_type ==
            # 'text/x-diff'. If there are inconsistencies, we don't
            # set the value automatically. Instead, we lead the user to
            # another form where we ask him if he is sure about his
            # choice of the patch flag.
            new_type_consistent_with_guessed_type = (
                self.attachmentTypeConsistentWithContentType(
                    new_type == BugAttachmentType.PATCH, filename,
                    file_content))
            if new_type_consistent_with_guessed_type:
                self.context.type = new_type
            else:
                self.next_url = self.nextUrlForInconsistentPatchFlags(
                    self.context)

        if data['title'] != self.context.title:
            self.context.title = data['title']

        if self.context.libraryfile.mimetype != data['contenttype']:
            lfa_with_parent = getMultiAdapter(
                (self.context.libraryfile, self.context),
                ILibraryFileAliasWithParent)
            lfa_with_parent.mimetype = data['contenttype']

    @action('Delete Attachment', name='delete')
    def delete_action(self, action, data):
        libraryfile_url = ProxiedLibraryFileAlias(
            self.context.libraryfile, self.context).http_url
        self.request.response.addInfoNotification(structured(
            'Attachment "<a href="%(url)s">%(name)s</a>" has been deleted.',
            url=libraryfile_url, name=self.context.title))
        self.context.removeFromBug(user=self.user)

    @property
    def label(self):
        return smartquote('Edit attachment "%s"') % self.context.title

    page_title = 'Edit attachment'


class BugAttachmentPatchConfirmationView(LaunchpadFormView):
    """Confirmation of the "patch" flag setting.

    If the user sets the "patch" flag to a value that is inconsistent
    with the result of a call of guess_content_type() for this
    attachment, we show this view to ask the user if he is sure
    about his selection.
    """

    schema = IBugAttachmentIsPatchConfirmationForm

    custom_widget('patch', LaunchpadBooleanRadioWidget)

    def __init__(self, context, request):
        LaunchpadFormView.__init__(self, context, request)
        self.next_url = self.cancel_url = (
            canonical_url(ICanonicalUrlData(context).inside))

    def initialize(self):
        super(BugAttachmentPatchConfirmationView, self).initialize()
        self.widgets['patch'].setRenderedValue(self.is_patch)

    @property
    def label(self):
        return smartquote('Confirm attachment type of "%s"') % (
            self.context.title)

    page_title = 'Confirm attachment type'

    @action('Change', name='change')
    def change_action(self, action, data):
        current_patch_setting = self.context.type == BugAttachmentType.PATCH
        if data['patch'] != current_patch_setting:
            if data['patch']:
                self.context.type = BugAttachmentType.PATCH
                #xxxxxxxxxx adjust content type!
                # xxx use mixin, together with BugAttachmnetEditView
            else:
                self.context.type = BugAttachmentType.UNSPECIFIED

    @property
    def is_patch(self):
        """True if this attachment contains a patch, else False."""
        return self.context.type == BugAttachmentType.PATCH


class BugAttachmentFileNavigation(Navigation, FileNavigationMixin):
    """Traversal to +files/${filename}."""

    usedfor = IBugAttachment
