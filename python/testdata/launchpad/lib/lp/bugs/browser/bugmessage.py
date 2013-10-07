# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""IBugMessage-related browser view classes."""

__metaclass__ = type
__all__ = [
    'BugMessageAddFormView',
    ]

from StringIO import StringIO

from zope.component import getUtility

from lp.app.browser.launchpadform import (
    action,
    LaunchpadFormView,
    )
from lp.bugs.browser.bugattachment import BugAttachmentContentCheck
from lp.bugs.interfaces.bugmessage import IBugMessageAddForm
from lp.bugs.interfaces.bugwatch import IBugWatchSet
from lp.services.webapp import canonical_url


class BugMessageAddFormView(LaunchpadFormView, BugAttachmentContentCheck):
    """Browser view class for adding a bug comment/attachment."""

    schema = IBugMessageAddForm
    initial_focus_widget = None

    @property
    def label(self):
        return 'Add a comment or attachment to bug #%d' % self.context.bug.id

    @property
    def page_title(self):
        return self.label

    @property
    def initial_values(self):
        return dict(subject=self.context.bug.followup_subject())

    @property
    def action_url(self):
        # override the default form action url to to go the addcomment
        # page for processing instead of the default which would be the
        # bug index page.
        return "%s/+addcomment" % canonical_url(self.context)

    def validate(self, data):

        # Ensure either a comment or filecontent was provide, but only
        # if no errors have already been noted.
        if len(self.errors) == 0:
            comment = data.get('comment') or u''
            filecontent = data.get('filecontent', None)
            if not comment.strip() and not filecontent:
                self.addError("Either a comment or attachment "
                              "must be provided.")

    @action(u"Post Comment", name='save')
    def save_action(self, action, data):
        """Add the comment and/or attachment."""

        bug = self.context.bug

        # Subscribe to this bug if the checkbox exists and was selected
        if data.get('email_me'):
            bug.subscribe(self.user, self.user)

        # XXX: Bjorn Tillenius 2005-06-16:
        # Write proper FileUpload field and widget instead of this hack.
        file_ = self.request.form.get(self.widgets['filecontent'].name)

        message = None
        if data['comment'] or file_:
            bugwatch_id = data.get('bugwatch_id')
            if bugwatch_id is not None:
                bugwatch = getUtility(IBugWatchSet).get(bugwatch_id)
            else:
                bugwatch = None
            message = bug.newMessage(subject=data.get('subject'),
                                     content=data['comment'],
                                     owner=self.user,
                                     bugwatch=bugwatch)

            # A blank comment with only a subect line is always added
            # when the user attaches a file, so show the add comment
            # feedback message only when the user actually added a
            # comment.
            if data['comment']:
                self.request.response.addNotification(
                    "Thank you for your comment.")

        self.next_url = canonical_url(self.context)
        if file_:

            # Slashes in filenames cause problems, convert them to dashes
            # instead.
            filename = file_.filename.replace('/', '-')

            # if no description was given use the converted filename
            file_description = None
            if 'attachment_description' in data:
                file_description = data['attachment_description']
            if not file_description:
                file_description = filename

            # Process the attachment.
            # If the patch flag is not consistent with the result of
            # the guess made in attachmentTypeConsistentWithContentType(),
            # we use the guessed type and lead the user to a page
            # where he can override the flag value, if Launchpad's
            # guess is wrong.
            patch_flag_consistent = (
                self.attachmentTypeConsistentWithContentType(
                    data['patch'], filename, data['filecontent']))
            if not patch_flag_consistent:
                guessed_type = self.guessContentType(
                    filename, data['filecontent'])
                is_patch = guessed_type == 'text/x-diff'
            else:
                is_patch = data['patch']
            attachment = bug.addAttachment(
                owner=self.user, data=StringIO(data['filecontent']),
                filename=filename, description=file_description,
                comment=message, is_patch=is_patch)

            if not patch_flag_consistent:
                self.next_url = self.nextUrlForInconsistentPatchFlags(
                    attachment)

            self.request.response.addNotification(
                "Attachment %s added to bug." % filename)

    def shouldShowEmailMeWidget(self):
        """Should the subscribe checkbox be shown?"""
        return not self.context.bug.isSubscribed(self.user)
