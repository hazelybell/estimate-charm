# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Debbugs ExternalBugTracker utility."""

__metaclass__ = type
__all__ = [
    'DebBugs',
    'DebBugsDatabaseNotFound'
    ]

from datetime import datetime
import email
from email.Utils import (
    mktime_tz,
    parseaddr,
    parsedate_tz,
    )
import os.path

import pytz
import transaction
from zope.component import getUtility
from zope.interface import implements

from lp.bugs.externalbugtracker import (
    BATCH_SIZE_UNLIMITED,
    BugNotFound,
    BugTrackerConnectError,
    ExternalBugTracker,
    InvalidBugId,
    UnknownRemoteStatusError,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.externalbugtracker import (
    ISupportsBugImport,
    ISupportsCommentImport,
    ISupportsCommentPushing,
    UNKNOWN_REMOTE_IMPORTANCE,
    )
from lp.bugs.scripts import debbugs
from lp.services.config import config
from lp.services.database.isolation import ensure_no_transaction
from lp.services.mail.sendmail import simple_sendmail
from lp.services.messages.interfaces.message import IMessageSet
from lp.services.webapp import urlsplit


debbugsstatusmap = {'open':      BugTaskStatus.NEW,
                    'forwarded': BugTaskStatus.CONFIRMED,
                    'done':      BugTaskStatus.FIXRELEASED}


class DebBugsDatabaseNotFound(BugTrackerConnectError):
    """The Debian bug database was not found."""


class DebBugs(ExternalBugTracker):
    """A class that deals with communications with a debbugs db."""

    implements(
        ISupportsBugImport, ISupportsCommentImport, ISupportsCommentPushing)

    # We don't support different versions of debbugs.
    version = None
    debbugs_pl = os.path.join(
        os.path.dirname(debbugs.__file__), 'debbugs-log.pl')

    # Because we keep a local copy of debbugs, we remove the batch_size
    # limit so that all debbugs watches that need checking will be
    # checked each time checkwatches runs.
    batch_size = BATCH_SIZE_UNLIMITED

    def __init__(self, baseurl, db_location=None):
        super(DebBugs, self).__init__(baseurl)
        # debbugs syncing can be enabled/disabled separately.
        self.sync_comments = (
            self.sync_comments and
            config.checkwatches.sync_debbugs_comments)

        if db_location is None:
            self.db_location = config.malone.debbugs_db_location
        else:
            self.db_location = db_location

        if not os.path.exists(os.path.join(self.db_location, 'db-h')):
            raise DebBugsDatabaseNotFound(
                self.db_location, '"db-h" not found.')

        # The debbugs database is split in two parts: a current
        # database, which is kept under the 'db-h' directory, and
        # the archived database, which is kept under 'archive'. The
        # archived database is used as a fallback, as you can see in
        # getRemoteStatus
        self.debbugs_db = debbugs.Database(
            self.db_location, self.debbugs_pl)
        if os.path.exists(os.path.join(self.db_location, 'archive')):
            self.debbugs_db_archive = debbugs.Database(
                self.db_location, self.debbugs_pl, subdir="archive")

    def getCurrentDBTime(self):
        """See `IExternalBugTracker`."""
        # We don't know the exact time for the Debbugs server, but we
        # trust it being correct.
        return datetime.now(pytz.timezone('UTC'))

    def initializeRemoteBugDB(self, bug_ids):
        """See `ExternalBugTracker`.

        This method is overridden (and left empty) here to avoid breakage when
        the continuous bug-watch checking spec is implemented.
        """

    def convertRemoteImportance(self, remote_importance):
        """See `ExternalBugTracker`.

        This method is implemented here as a stub to ensure that
        existing functionality is preserved. As a result,
        BugTaskImportance.UNKNOWN will always be returned.
        """
        return BugTaskImportance.UNKNOWN

    def convertRemoteStatus(self, remote_status):
        """Convert a debbugs status to a Malone status.

        A debbugs status consists of either two or three parts,
        separated with space; the status and severity, followed by
        optional tags. The tags are also separated with a space
        character.
        """
        parts = remote_status.split(' ')
        if len(parts) < 2:
            raise UnknownRemoteStatusError(remote_status)

        status = parts[0]
        tags = parts[2:]

        # For the moment we convert only the status, not the severity.
        try:
            malone_status = debbugsstatusmap[status]
        except KeyError:
            raise UnknownRemoteStatusError(remote_status)
        if status == 'open':
            confirmed_tags = [
                'help', 'confirmed', 'upstream', 'fixed-upstream']
            fix_committed_tags = ['pending', 'fixed', 'fixed-in-experimental']
            if 'moreinfo' in tags:
                malone_status = BugTaskStatus.INCOMPLETE
            for confirmed_tag in confirmed_tags:
                if confirmed_tag in tags:
                    malone_status = BugTaskStatus.CONFIRMED
                    break
            for fix_committed_tag in fix_committed_tags:
                if fix_committed_tag in tags:
                    malone_status = BugTaskStatus.FIXCOMMITTED
                    break
            if 'wontfix' in tags:
                malone_status = BugTaskStatus.WONTFIX

        return malone_status

    def _findBug(self, bug_id):
        if not bug_id.isdigit():
            raise InvalidBugId(
                "Debbugs bug number not an integer: %s" % bug_id)
        try:
            debian_bug = self.debbugs_db[int(bug_id)]
        except KeyError:
            # If we couldn't find it in the main database, there's
            # always the archive.
            try:
                debian_bug = self.debbugs_db_archive[int(bug_id)]
            except KeyError:
                raise BugNotFound(bug_id)

        return debian_bug

    def _loadLog(self, debian_bug):
        """Load the debbugs comment log for a given bug.

        This method is analogous to _findBug() in that if the comment
        log cannot be loaded from the main database it will attempt to
        load the log from the archive database.

        If no comment log can be found, a debbugs.LogParseFailed error
        will be raised.
        """
        # If we can't find the log in the main database we try the
        # archive.
        try:
            self.debbugs_db.load_log(debian_bug)
        except debbugs.LogParseFailed:
            # If there is no log for this bug in the archive a
            # LogParseFailed error will be raised. However, we let that
            # propagate upwards since we need to make the callsite deal
            # with the fact that there's no log to parse.
            self.debbugs_db_archive.load_log(debian_bug)

    def getRemoteImportance(self, bug_id):
        """See `ExternalBugTracker`.

        This method is implemented here as a stub to ensure that
        existing functionality is preserved. As a result,
        UNKNOWN_REMOTE_IMPORTANCE will always be returned.
        """
        return UNKNOWN_REMOTE_IMPORTANCE

    def getRemoteStatus(self, bug_id):
        """See ExternalBugTracker."""
        debian_bug = self._findBug(bug_id)
        if not debian_bug.severity:
            # 'normal' is the default severity in debbugs.
            severity = 'normal'
        else:
            severity = debian_bug.severity
        new_remote_status = ' '.join(
            [debian_bug.status, severity] + debian_bug.tags)
        return new_remote_status

    def getBugReporter(self, remote_bug):
        """See ISupportsBugImport."""
        debian_bug = self._findBug(remote_bug)
        reporter_name, reporter_email = parseaddr(debian_bug.originator)
        return reporter_name, reporter_email

    def getBugTargetName(self, remote_bug):
        """See ISupportsBugImport."""
        debian_bug = self._findBug(remote_bug)
        return debian_bug.package

    def getBugSummaryAndDescription(self, remote_bug):
        """See ISupportsBugImport."""
        debian_bug = self._findBug(remote_bug)
        return debian_bug.subject, debian_bug.description

    def getCommentIds(self, remote_bug_id):
        """See `ISupportsCommentImport`."""
        debian_bug = self._findBug(remote_bug_id)
        self._loadLog(debian_bug)

        comment_ids = []
        for comment in debian_bug.comments:
            parsed_comment = email.message_from_string(comment)

            # It's possible for the same message to appear several times
            # in a DebBugs comment log, since each control command in a
            # message results in that message being recorded once
            # against the bug that the command affects. We only want to
            # know about the comment once, though.  We also discard
            # comments with no date, since we can't import those
            # correctly.
            comment_date = self._getDateForComment(parsed_comment)
            if (comment_date is not None and
                parsed_comment['message-id'] not in comment_ids):
                comment_ids.append(parsed_comment['message-id'])

        return comment_ids

    def fetchComments(self, remote_bug_id, comment_ids):
        """See `ISupportsCommentImport`."""
        # This method does nothing since DebBugs bugs are stored locally
        # and their comments don't need to be pre-fetched. It exists
        # purely to ensure that CheckwatchesMaster doesn't choke on it.
        pass

    def getPosterForComment(self, remote_bug_id, comment_id):
        """See `ISupportsCommentImport`."""
        debian_bug = self._findBug(remote_bug_id)
        self._loadLog(debian_bug)

        for comment in debian_bug.comments:
            parsed_comment = email.message_from_string(comment)
            if parsed_comment['message-id'] == comment_id:
                return parseaddr(parsed_comment['from'])

    def _getDateForComment(self, parsed_comment):
        """Return the correct date for a comment.

        :param parsed_comment: An `email.Message.Message` instance
            containing a parsed DebBugs comment.
        :return: The correct date to use for the comment contained in
            `parsed_comment`. If a date is specified in a Received
            header on `parsed_comment` that we can use, return that.
            Otherwise, return the Date field of `parsed_comment`.
        """
        # Check for a Received: header on the comment and use
        # that to get the date, if possible. We only use the
        # date received by this host (nominally bugs.debian.org)
        # since that's the one that's likely to be correct.
        received_headers = parsed_comment.get_all('received')
        if received_headers is not None:
            host_name = urlsplit(self.baseurl)[1]

            received_headers = [
                header for header in received_headers
                if host_name in header]

        # If there are too many - or too few - received headers then
        # something's gone wrong and we default back to using
        # the Date field.
        if received_headers is not None and len(received_headers) == 1:
            received_string = received_headers[0]
            received_by, date_string = received_string.split(';', 2)
        else:
            date_string = parsed_comment['date']

        # We parse the date_string if we can, otherwise we just return
        # None.
        if date_string is not None:
            date_with_tz = parsedate_tz(date_string)
            timestamp = mktime_tz(date_with_tz)
            msg_date = datetime.fromtimestamp(timestamp,
                tz=pytz.timezone('UTC'))
        else:
            msg_date = None

        return msg_date

    def getMessageForComment(self, remote_bug_id, comment_id, poster):
        """See `ISupportsCommentImport`."""
        debian_bug = self._findBug(remote_bug_id)
        self._loadLog(debian_bug)

        for comment in debian_bug.comments:
            parsed_comment = email.message_from_string(comment)
            if parsed_comment['message-id'] == comment_id:
                msg_date = self._getDateForComment(parsed_comment)
                message = getUtility(IMessageSet).fromEmail(comment, poster,
                    parsed_message=parsed_comment, date_created=msg_date)

                transaction.commit()
                return message

    @ensure_no_transaction
    def addRemoteComment(self, remote_bug, comment_body, rfc822msgid):
        """Push a comment to the remote DebBugs instance.

        See `ISupportsCommentPushing`.
        """
        debian_bug = self._findBug(remote_bug)

        # We set the subject to "Re: <bug subject>" in the same way that
        # a mail client would.
        subject = "Re: %s" % debian_bug.subject
        host_name = urlsplit(self.baseurl)[1]
        to_addr = "%s@%s" % (remote_bug, host_name)

        headers = {'Message-Id': rfc822msgid}

        # We str()ify to_addr since simple_sendmail expects ASCII
        # strings and gets awfully upset when it gets a unicode one.
        sent_msg_id = simple_sendmail(
            'debbugs@bugs.launchpad.net', [str(to_addr)], subject,
            comment_body, headers=headers)

        # We add angle-brackets to the sent_msg_id because
        # simple_sendmail strips them out. We want to remain consistent
        # with debbugs, which uses angle-brackets in its message IDS (as
        # does Launchpad).
        return "<%s>" % sent_msg_id

    def getRemoteProduct(self, remote_bug):
        """Return the remote product for a bug.

        See `IExternalBugTracker`.
        """
        # For DebBugs, we want to return the package name associated
        # with the bug. Since getBugTargetName() does this already we
        # simply call that.
        return self.getBugTargetName(remote_bug)
