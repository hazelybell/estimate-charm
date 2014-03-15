# Copyright 2010-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes and logic for the checkwatches BugWatchUpdater."""

__metaclass__ = type
__all__ = [
    'BugWatchUpdater',
    ]

import sys

from lazr.lifecycle.event import ObjectCreatedEvent
from zope.component import getUtility
from zope.event import notify

from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.bugs.externalbugtracker.base import BugWatchUpdateError
from lp.bugs.interfaces.bug import IBugSet
from lp.bugs.interfaces.bugwatch import BugWatchActivityStatus
from lp.bugs.scripts.checkwatches.base import (
    commit_before,
    WorkingBase,
    )
from lp.bugs.scripts.checkwatches.utilities import (
    get_remote_system_oops_properties,
    )
from lp.registry.interfaces.person import PersonCreationRationale
from lp.services.mail.helpers import get_email_template
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp.publisher import canonical_url


class BugWatchUpdater(WorkingBase):
    """Handles the updating of a single BugWatch for checkwatches."""

    def __init__(self, parent, bug_watch, external_bugtracker):
        self.initFromParent(parent)
        self.bug_watch = bug_watch
        self.external_bugtracker = external_bugtracker

        # We save these for the sake of error reporting.
        self.remote_bug = self.bug_watch.remotebug
        self.local_bug = self.bug_watch.bug.id
        self.oops_properties = get_remote_system_oops_properties(
            self.external_bugtracker)
        self.oops_properties.extend([
            ('URL', self.bug_watch.url),
            ('bug_id', self.remote_bug),
            ('local_ids', str(self.local_bug))])

        self.can_import_comments = parent.can_import_comments
        self.can_push_comments = parent.can_push_comments
        self.can_back_link = parent.can_back_link

    @commit_before
    def updateBugWatch(self, new_remote_status, new_malone_status,
                       new_remote_importance, new_malone_importance):
        """Update the BugWatch."""
        with self.transaction:
            if new_malone_status is not None:
                self.bug_watch.updateStatus(
                    new_remote_status, new_malone_status)
            if new_malone_importance is not None:
                self.bug_watch.updateImportance(
                    new_remote_importance, new_malone_importance)
            # Only sync comments and backlink if the local bug isn't a
            # duplicate and the bug watch is associated with a bug task.
            # This helps us to avoid spamming both upstream and
            # ourselves.
            do_sync = (
                self.bug_watch.bug.duplicateof is None and
                len(self.bug_watch.bugtasks) > 0
                )

        error_message = None
        error_status = None
        oops_id = None
        if do_sync:
            try:
                if self.can_import_comments:
                    error_status = (
                        BugWatchActivityStatus.COMMENT_IMPORT_FAILED)
                    self.importBugComments()
                if self.can_push_comments:
                    error_status = BugWatchActivityStatus.COMMENT_PUSH_FAILED
                    self.pushBugComments()
                if self.can_back_link:
                    error_status = BugWatchActivityStatus.BACKLINK_FAILED
                    self.linkLaunchpadBug()
            except Exception as ex:
                error_message = str(ex)
                log_message = (
                    "Failure updating bug %r on %s (local bug: %s)" %
                    (self.remote_bug, self.external_bugtracker.baseurl,
                    self.local_bug))
                if isinstance(ex, BugWatchUpdateError):
                    self.logger.info('%s: %s' % (log_message, ex))
                else:
                    oops_id = self.error(log_message, self.oops_properties)
            else:
                error_status = None

        with self.transaction:
            self.bug_watch.addActivity(
                result=error_status, message=error_message, oops_id=oops_id)
            self.bug_watch.last_error_type = error_status

    @commit_before
    def importBugComments(self):
        """Import all the comments from the remote bug."""
        with self.transaction:
            local_bug_id = self.bug_watch.bug.id
            remote_bug_id = self.bug_watch.remotebug

        # Construct a list of the comment IDs we want to import; i.e.
        # those which we haven't already imported.
        all_comment_ids = self.external_bugtracker.getCommentIds(
            remote_bug_id)

        with self.transaction:
            comment_ids_to_import = [
                comment_id for comment_id in all_comment_ids
                if not self.bug_watch.hasComment(comment_id)]

        self.external_bugtracker.fetchComments(
            remote_bug_id, comment_ids_to_import)

        with self.transaction:
            previous_imported_comments = (
                self.bug_watch.getImportedBugMessages())
            is_initial_import = previous_imported_comments.count() == 0
            imported_comments = []

            for comment_id in comment_ids_to_import:
                displayname, email = (
                    self.external_bugtracker.getPosterForComment(
                        remote_bug_id, comment_id))

                if displayname is None and email is None:
                    # If we don't have a displayname or an email address
                    # then we can't create a Launchpad Person as the author
                    # of this comment. We raise an OOPS and continue.
                    self.warning(
                        "Unable to import remote comment author. No email "
                        "address or display name found.",
                        get_remote_system_oops_properties(
                            self.external_bugtracker),
                        sys.exc_info())
                    continue

                poster = self.bug_watch.bugtracker.ensurePersonForSelf(
                    displayname, email, PersonCreationRationale.BUGIMPORT,
                    "when importing comments for %s." % self.bug_watch.title)

                comment_message = (
                    self.external_bugtracker.getMessageForComment(
                        remote_bug_id, comment_id, poster))

                bug_message = self.bug_watch.addComment(
                    comment_id, comment_message)
                imported_comments.append(bug_message)

            if len(imported_comments) > 0:
                self.bug_watch_updater = (
                    getUtility(ILaunchpadCelebrities).bug_watch_updater)
                if is_initial_import:
                    notification_text = get_email_template(
                        'bugwatch-initial-comment-import.txt', 'bugs') % dict(
                            num_of_comments=len(imported_comments),
                            bug_watch_url=self.bug_watch.url)
                    comment_text_template = get_email_template(
                        'bugwatch-comment.txt', 'bugs')

                    for bug_message in imported_comments:
                        comment = bug_message.message
                        notification_text += comment_text_template % dict(
                            comment_date=comment.datecreated.isoformat(),
                            commenter=comment.owner.displayname,
                            comment_text=comment.text_contents,
                            comment_reply_url=canonical_url(comment))
                    notification_message = getUtility(IMessageSet).fromText(
                        subject=self.bug_watch.bug.followup_subject(),
                        content=notification_text,
                        owner=self.bug_watch_updater)
                    self.bug_watch.bug.addCommentNotification(
                        notification_message)
                else:
                    for bug_message in imported_comments:
                        notify(ObjectCreatedEvent(
                            bug_message,
                            user=self.bug_watch_updater))

            self.logger.info("Imported %(count)i comments for remote bug "
                "%(remotebug)s on %(bugtracker_url)s into Launchpad bug "
                "%(bug_id)s." %
                {'count': len(imported_comments),
                 'remotebug': remote_bug_id,
                 'bugtracker_url': self.external_bugtracker.baseurl,
                 'bug_id': local_bug_id})

    def _formatRemoteComment(self, message):
        """Format a comment for a remote bugtracker and return it."""
        comment_template = get_email_template(
            self.external_bugtracker.comment_template, 'bugs')

        return comment_template % {
            'launchpad_bug': self.bug_watch.bug.id,
            'comment_author': message.owner.displayname,
            'comment_body': message.text_contents,
            }

    @commit_before
    def pushBugComments(self):
        """Push Launchpad comments to the remote bug.

        :param self.external_bugtracker: An external bugtracker which
            implements `ISupportsCommentPushing`.
        :param self.bug_watch: The bug watch to which the comments should be
            pushed.
        """
        pushed_comments = 0

        with self.transaction:
            local_bug_id = self.bug_watch.bug.id
            remote_bug_id = self.bug_watch.remotebug
            unpushed_comments = list(self.bug_watch.unpushed_comments)

        # Loop over the unpushed comments for the bug watch.
        # We only push those comments that haven't been pushed
        # already. We don't push any comments not associated with
        # the bug watch.
        for unpushed_comment in unpushed_comments:
            with self.transaction:
                message = unpushed_comment.message
                message_rfc822msgid = message.rfc822msgid
                # Format the comment so that it includes information
                # about the Launchpad bug.
                formatted_comment = self._formatRemoteComment(message)

            remote_comment_id = (
                self.external_bugtracker.addRemoteComment(
                    remote_bug_id, formatted_comment,
                    message_rfc822msgid))

            assert remote_comment_id is not None, (
                "A remote_comment_id must be specified.")
            with self.transaction:
                unpushed_comment.remote_comment_id = remote_comment_id

            pushed_comments += 1

        if pushed_comments > 0:
            self.logger.info("Pushed %(count)i comments to remote bug "
                "%(remotebug)s on %(bugtracker_url)s from Launchpad bug "
                "%(bug_id)s" %
                {'count': pushed_comments,
                 'remotebug': remote_bug_id,
                 'bugtracker_url': self.external_bugtracker.baseurl,
                 'bug_id': local_bug_id})

    @commit_before
    def linkLaunchpadBug(self):
        """Link a Launchpad bug to a given remote bug."""
        with self.transaction:
            local_bug_id = self.bug_watch.bug.id
            local_bug_url = canonical_url(self.bug_watch.bug)
            remote_bug_id = self.bug_watch.remotebug

        current_launchpad_id = self.external_bugtracker.getLaunchpadBugId(
            remote_bug_id)

        if current_launchpad_id is None:
            # If no bug is linked to the remote bug, link this one and
            # then stop.
            self.external_bugtracker.setLaunchpadBugId(
                remote_bug_id, local_bug_id, local_bug_url)
            return

        elif current_launchpad_id == local_bug_id:
            # If the current_launchpad_id is the same as the ID of the bug
            # we're trying to link, we can stop.
            return

        else:
            # If the current_launchpad_id isn't the same as the one
            # we're trying to link, check that the other bug actually
            # links to the remote bug. If it does, we do nothing, since
            # the first valid link wins. Otherwise we link the bug that
            # we've been passed, overwriting the previous value of the
            # Launchpad bug ID for this remote bug.
            try:
                with self.transaction:
                    other_launchpad_bug = getUtility(IBugSet).get(
                        current_launchpad_id)
                    other_bug_watch = other_launchpad_bug.getBugWatch(
                        self.bug_watch.bugtracker, remote_bug_id)
            except NotFoundError:
                # If we can't find the bug that's referenced by
                # current_launchpad_id we simply set other_self.bug_watch to
                # None so that the Launchpad ID of the remote bug can be
                # set correctly.
                other_bug_watch = None

            if other_bug_watch is None:
                self.external_bugtracker.setLaunchpadBugId(
                    remote_bug_id, local_bug_id, local_bug_url)
