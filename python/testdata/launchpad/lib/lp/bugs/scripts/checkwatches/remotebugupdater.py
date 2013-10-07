# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Classes and logic for the remote bug updater."""

__metaclass__ = type
__all__ = [
    'RemoteBugUpdater',
    ]

from zope.component import getUtility

from lp.bugs.externalbugtracker.base import (
    BugNotFound,
    InvalidBugId,
    PrivateRemoteBug,
    UnknownRemoteValueError,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.bugs.interfaces.bugwatch import (
    BugWatchActivityStatus,
    IBugWatchSet,
    )
from lp.bugs.interfaces.externalbugtracker import (
    ISupportsBackLinking,
    ISupportsCommentImport,
    ISupportsCommentPushing,
    UNKNOWN_REMOTE_IMPORTANCE,
    UNKNOWN_REMOTE_STATUS,
    )
from lp.bugs.scripts.checkwatches.base import (
    commit_before,
    WorkingBase,
    )
from lp.bugs.scripts.checkwatches.bugwatchupdater import BugWatchUpdater
from lp.bugs.scripts.checkwatches.utilities import (
    get_bugwatcherrortype_for_error,
    get_remote_system_oops_properties,
    )
from lp.services.database.constants import UTC_NOW


class RemoteBugUpdater(WorkingBase):

    def __init__(self, parent, external_bugtracker, remote_bug,
                 bug_watch_ids, unmodified_remote_ids, server_time):
        self.initFromParent(parent)
        self.external_bugtracker = external_bugtracker
        self.bug_tracker_url = external_bugtracker.baseurl
        self.remote_bug = remote_bug
        self.bug_watch_ids = bug_watch_ids
        self.unmodified_remote_ids = unmodified_remote_ids

        self.error_type_messages = {
            BugWatchActivityStatus.INVALID_BUG_ID:
                ("Invalid bug %(bug_id)r on %(base_url)s "
                 "(local bugs: %(local_ids)s)."),
            BugWatchActivityStatus.BUG_NOT_FOUND:
                ("Didn't find bug %(bug_id)r on %(base_url)s "
                 "(local bugs: %(local_ids)s)."),
            BugWatchActivityStatus.PRIVATE_REMOTE_BUG:
                ("Remote bug %(bug_id)r on %(base_url)s is private "
                 "(local bugs: %(local_ids)s)."),
            }
        self.error_type_message_default = (
            "remote bug: %(bug_id)r; "
            "base url: %(base_url)s; "
            "local bugs: %(local_ids)s"
            )

        # Whether we can import and / or push comments is determined
        # on a per-bugtracker-type level.
        self.can_import_comments = (
            ISupportsCommentImport.providedBy(external_bugtracker) and
            external_bugtracker.sync_comments)
        self.can_push_comments = (
            ISupportsCommentPushing.providedBy(external_bugtracker) and
            external_bugtracker.sync_comments)
        self.can_back_link = (
            ISupportsBackLinking.providedBy(external_bugtracker) and
            external_bugtracker.sync_comments)

        if self.can_import_comments and server_time is None:
            self.can_import_comments = False
            self.warning(
                "Comment importing supported, but server time can't be "
                "trusted. No comments will be imported.")

    def _getBugWatchesForRemoteBug(self):
        """Return a list of bug watches for the current remote bug.

        The returned watches will all be members of `self.bug_watch_ids`.

        This method exists primarily to be overridden during testing.
        """
        return list(
            getUtility(IBugWatchSet).getBugWatchesForRemoteBug(
                self.remote_bug, self.bug_watch_ids))

    @commit_before
    def updateRemoteBug(self):
        with self.transaction:
            bug_watches = self._getBugWatchesForRemoteBug()
            # If there aren't any bug watches for this remote bug,
            # just log a warning and carry on.
            if len(bug_watches) == 0:
                self.warning(
                    "Spurious remote bug ID: No watches found for "
                    "remote bug %s on %s" % (
                        self.remote_bug, self.external_bugtracker.baseurl))
                return
            # Mark them all as checked.
            for bug_watch in bug_watches:
                bug_watch.lastchecked = UTC_NOW
                bug_watch.next_check = None
            # Return if this one is definitely unmodified.
            if self.remote_bug in self.unmodified_remote_ids:
                return
            # Save the remote bug URL for error reporting.
            remote_bug_url = bug_watches[0].url
            # Save the list of local bug IDs for error reporting.
            local_ids = ", ".join(
                str(bug_id) for bug_id in sorted(
                    watch.bug.id for watch in bug_watches))

        try:
            new_remote_status = None
            new_malone_status = None
            new_remote_importance = None
            new_malone_importance = None
            error = None
            oops_id = None

            try:
                new_remote_status = (
                    self.external_bugtracker.getRemoteStatus(
                        self.remote_bug))
                new_malone_status = self._convertRemoteStatus(
                    new_remote_status)
                new_remote_importance = (
                    self.external_bugtracker.getRemoteImportance(
                        self.remote_bug))
                new_malone_importance = self._convertRemoteImportance(
                    new_remote_importance)
            except (InvalidBugId, BugNotFound, PrivateRemoteBug) as ex:
                error = get_bugwatcherrortype_for_error(ex)
                message = self.error_type_messages.get(
                    error, self.error_type_message_default)
                self.logger.info(
                    message % {
                        'bug_id': self.remote_bug,
                        'base_url': self.external_bugtracker.baseurl,
                        'local_ids': local_ids,
                        })
                # Set the error and activity on all bug watches
                with self.transaction:
                    getUtility(IBugWatchSet).bulkSetError(
                        bug_watches, error)
                    getUtility(IBugWatchSet).bulkAddActivity(
                        bug_watches, result=error)
            else:
                # Assuming nothing's gone wrong, we can now deal with
                # each BugWatch in turn.
                for bug_watch in bug_watches:
                    bug_watch_updater = BugWatchUpdater(
                        self, bug_watch, self.external_bugtracker)
                    bug_watch_updater.updateBugWatch(
                        new_remote_status, new_malone_status,
                        new_remote_importance, new_malone_importance)
        except Exception as error:
            # Send the error to the log.
            oops_id = self.error(
                "Failure updating bug %r on %s (local bugs: %s)." %
                        (self.remote_bug, self.bug_tracker_url, local_ids),
                properties=[
                    ('URL', remote_bug_url),
                    ('bug_id', self.remote_bug),
                    ('local_ids', local_ids)] +
                    get_remote_system_oops_properties(
                        self.external_bugtracker))
            # We record errors against the bug watches and update
            # their lastchecked dates so that we don't try to
            # re-check them every time checkwatches runs.
            error_type = get_bugwatcherrortype_for_error(error)
            with self.transaction:
                getUtility(IBugWatchSet).bulkSetError(
                    bug_watches, error_type)
                getUtility(IBugWatchSet).bulkAddActivity(
                    bug_watches, result=error_type, oops_id=oops_id)

    def _convertRemoteStatus(self, remote_status):
        """Convert a remote status to a Launchpad one and return it."""
        return self._convertRemoteValue(
            self.external_bugtracker.convertRemoteStatus,
            UNKNOWN_REMOTE_STATUS, BugTaskStatus.UNKNOWN, remote_status)

    def _convertRemoteImportance(self, remote_importance):
        """Convert a remote importance to a Launchpad one and return it."""
        return self._convertRemoteValue(
            self.external_bugtracker.convertRemoteImportance,
            UNKNOWN_REMOTE_IMPORTANCE, BugTaskImportance.UNKNOWN,
            remote_importance)

    def _convertRemoteValue(self, conversion_method, remote_unknown,
                            launchpad_unknown, remote_value):
        """Convert a remote bug value to a Launchpad value and return it.

        :param conversion_method: A method returning the Launchpad value
            corresponding to the given remote value.
        :param remote_unknown: The remote value which indicates an unknown
            value.
        :param launchpad_unknown: The Launchpad value which indicates an
            unknown value.
        :param remote_value: The remote value to be converted.

        If the remote value cannot be mapped to a Launchpad value,
        launchpad_unknown will be returned and a warning will be logged.
        """
        # We don't bother trying to convert remote_unknown.
        if remote_value == remote_unknown:
            return launchpad_unknown

        try:
            launchpad_value = conversion_method(remote_value)
        except UnknownRemoteValueError as e:
            # We log the warning, since we need to know about values
            # that we don't handle correctly.
            self.logger.info(
                "Unknown remote %s '%s' for bug %r on %s." %
                (e.field_name, remote_value, self.remote_bug,
                 self.bug_tracker_url))
            launchpad_value = launchpad_unknown

        return launchpad_value
