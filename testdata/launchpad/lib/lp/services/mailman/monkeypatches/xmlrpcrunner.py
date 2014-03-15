# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""XMLRPC runner for querying Launchpad."""

__all__ = [
    'get_mailing_list_api_proxy',
    'handle_proxy_error',
    'XMLRPCRunner',
    ]

from cStringIO import StringIO
from datetime import (
    datetime,
    timedelta,
    )
import errno
import os
from random import shuffle
import shutil
import socket
import sys
import tarfile
import traceback
import xmlrpclib

from Mailman import (
    Errors,
    mm_cfg,
    Utils,
    )
from Mailman.LockFile import TimeOutError
from Mailman.Logging.Syslog import syslog
from Mailman.MailList import MailList
from Mailman.Queue.Runner import Runner
from Mailman.Queue.sbcache import get_switchboard

from lp.services.webapp.errorlog import ErrorReportingUtility
from lp.services.xmlrpc import Transport


COMMASPACE = ', '


# Mapping from modifiable attributes as they are named by the xmlrpc
# interface, to the attribute names on the MailList instances.
attrmap = {
    'welcome_message': 'welcome_msg',
    }


def get_mailing_list_api_proxy():
    return xmlrpclib.ServerProxy(
        mm_cfg.XMLRPC_URL, transport=Transport(timeout=mm_cfg.XMLRPC_TIMEOUT))


def log_exception(message, *args):
    """Write the current exception traceback into the Mailman log file.

    This is really just a convenience function for a refactored chunk of
    common code.

    :param message: The message to appear in the xmlrpc and error logs. It
        may be a format string.
    :param args: Optional arguments to be interpolated into a format string.
    """
    error_utility = ErrorReportingUtility()
    error_utility.configure(section_name='mailman')
    error_utility.raising(sys.exc_info())
    out_file = StringIO()
    traceback.print_exc(file=out_file)
    traceback_text = out_file.getvalue()
    syslog('xmlrpc', message, *args)
    syslog('error', message, *args)
    syslog('error', traceback_text)


def handle_proxy_error(error, msg=None, msgdata=None):
    """Log the error and enqueue the message if needed.

    :param error: The error to log.
    :param msg: An optional Mailman.Message to re-enqueue.
    :param msgdata: The message data to enque with the message.
    :raise DiscardMessage: When a message is enqueued.
    """
    if isinstance(error, (xmlrpclib.ProtocolError, socket.error)):
        log_exception('Cannot talk to Launchpad:\n%s', error)
    else:
        log_exception('Launchpad exception: %s', error)
    if msg is not None:
        queue = get_switchboard(mm_cfg.INQUEUE_DIR)
        queue.enqueue(msg, msgdata)
        raise Errors.DiscardMessage


class XMLRPCRunner(Runner):
    """A Mailman 'queue runner' for talking to the Launchpad XMLRPC service.
    """

    # We increment this every time we see an actual change in the data coming
    # from Launchpad.  We write this to the xmlrpc log file for better
    # synchronization with the integration tests.  It's not used for any other
    # purpose.
    def __init__(self, slice=None, numslices=None):
        """Create a faux runner which checks into Launchpad occasionally.

        Every XMLRPC_SLEEPTIME number of seconds, this runner wakes up and
        connects to a Launchpad XMLRPC service to see if there's anything for
        it to do.  slice and numslices are ignored, but required by the
        Mailman queue runner framework.
        """
        self.SLEEPTIME = mm_cfg.XMLRPC_SLEEPTIME
        # Instead of calling the superclass's __init__() method, just
        # initialize the two attributes that are actually used.  The reason
        # for this is that the XMLRPCRunner doesn't have a queue so it
        # shouldn't be trying to create a Switchboard instance.  Still, it
        # needs a dummy _kids and _stop attributes for the rest of the runner
        # to work.  We're using runners in a more general sense than Mailman 2
        # is designed for.
        self._kids = {}
        self._stop = False
        self._proxy = get_mailing_list_api_proxy()
        # Ensure that the log file exists, mostly for the test suite.
        syslog('xmlrpc', 'XMLRPC runner starting')
        self.heartbeat_frequency = timedelta(minutes=5)
        self.last_heartbeat = None
        self._heartbeat()

    def _oneloop(self):
        """Check to see if there's anything for Mailman to do.

        Mailman makes an XMLRPC connection to Launchpad to see if there are
        any mailing lists to create, modify or deactivate.  It also requests
        updates to list subscriptions.  This method is called periodically by
        the base class's main loop.

        This method always returns 0 to indicate to the base class's main loop
        that it should sleep for a while after calling this method.
        """
        methods = (
            self._check_list_actions, self._get_subscriptions,
            self._check_held_messages)
        try:
            for method in methods:
                if self._shortcircuit():
                    # The runner was  shutdown during the long network call.
                    break
                method()
        except:
            # Log the exception and report an OOPS.
            log_exception('Unexpected XMLRPCRunner exception')
        else:
            self._heartbeat()
        # Snooze for a while.
        return 0

    def _heartbeat(self):
        """Add a heartbeat to the log for a monitor to watch."""
        now = datetime.now()
        last_heartbeat = self.last_heartbeat
        if (last_heartbeat is None
            or now - last_heartbeat >= self.heartbeat_frequency):
            syslog('xmlrpc', '--MARK--')
            self.last_heartbeat = now

    def _log(self, exc):
        """Log the exception in a log file and as an OOPS."""
        Runner._log(self, exc)
        error_utility = ErrorReportingUtility()
        error_utility.configure(section_name='mailman')
        error_utility.raising(sys.exc_info())

    def _check_list_actions(self):
        """See if there are any list actions to perform."""
        try:
            actions = self._proxy.getPendingActions()
        except (xmlrpclib.ProtocolError, socket.error) as error:
            log_exception('Cannot talk to Launchpad:\n%s', error)
            return
        except xmlrpclib.Fault as error:
            log_exception('Launchpad exception: %s', error)
            return
        if actions:
            syslog('xmlrpc', 'Received these actions: %s',
                   COMMASPACE.join(actions))
        else:
            return
        # There are three actions that can currently be taken.  A create
        # action creates a mailing list, possibly with some defaults, a modify
        # changes the settings on some existing mailing list, and a deactivate
        # means that the list should be deactivated.  This latter doesn't have
        # a directly corresponding semantic at the Mailman layer -- if a
        # mailing list exists, it's activated.  We'll take it to mean that the
        # list should be deleted, but its archives should remain.
        statuses = {}
        if 'create' in actions:
            self._create_or_reactivate(actions['create'], statuses)
            del actions['create']
        if 'modify' in actions:
            self._modify(actions['modify'], statuses)
            del actions['modify']
        if 'deactivate' in actions:
            self._deactivate(actions['deactivate'], statuses)
            del actions['deactivate']
        if 'unsynchronized' in actions:
            self._resynchronize(actions['unsynchronized'], statuses)
            del actions['unsynchronized']
        # Any other keys should be ignored because they specify actions that
        # we know nothing about.  We'll log them to Mailman's log files
        # though.
        if actions:
            syslog('xmlrpc', 'Invalid xmlrpc action keys: %s',
                   COMMASPACE.join(actions))
        # Report the statuses to Launchpad.  Do this individually so as to
        # reduce the possibility that a bug in Launchpad causes the reporting
        # all subsequent mailing lists statuses to fail.  The reporting of
        # status triggers synchronous operations in Launchpad, such as
        # notifying team admins that their mailing list is ready, and those
        # operations could fail for spurious reasons.  That shouldn't affect
        # the status reporting for any other list.  This is a little more
        # costly, but it's not that bad.
        for team_name, (action, status) in statuses.items():
            this_status = {team_name: status}
            try:
                self._proxy.reportStatus(this_status)
                syslog('xmlrpc', '[%s] %s: %s' % (team_name, action, status))
            except (xmlrpclib.ProtocolError, socket.error) as error:
                log_exception('Cannot talk to Launchpad:\n%s', error)
            except xmlrpclib.Fault as error:
                log_exception('Launchpad exception: %s', error)

    def _update_list_subscriptions(self, list_name, subscription_info):
        """Update the subscription information for a single mailing list.

        :param list_name: The name of the mailing list to update.
        :type list_name: string
        :param subscription_info: The mailing list's new subscription
            information.
        :type subscription_info: a list of 4-tuples containing the address,
            real name, flags, and status of each person in the list's
            subscribers.
        """
        ## syslog('xmlrpc', '%s subinfo: %s', list_name, subscription_info)
        # Start with an unlocked list.
        mlist = MailList(list_name, lock=False)
        # Create a mapping of email address to the member's real name,
        # flags, and status.  Note that flags is currently unused.
        member_map = dict((address, (realname, flags, status))
                          for address, realname, flags, status
                          in subscription_info)
        # In Mailman parlance, the 'member key' is the lower-cased
        # address.  We need a mapping from the member key to
        # case-preserved address for all future members of the list.
        key_to_case_preserved = dict((address.lower(), address)
                                     for address in member_map)
        # The following modifications to membership may be made:
        # - Current members whose address is changing case
        # - New members who need to be added to the mailing list
        # - Old members who need to be removed from the mailing list
        # - Current members whose settings are being changed
        #
        # Start by getting the case-folded membership sets of all current
        # and future members.
        current_members = set(mlist.getMembers())
        future_members = set(key_to_case_preserved)
        # Additions are all those addresses in future_members who are not
        # in current_members.
        additions = future_members - current_members
        # Deletions are all those addresses in current_members who are not
        # in future_members.
        deletions = current_members - future_members
        # Any address in both current and future members is either
        # changing case, updating settings, or both.
        updates = current_members & future_members
        # If there's nothing to do, just skip this list.
        if not additions and not deletions and not updates:
            # Why did we get here?  This list should not have shown up in
            # getMembershipInformation().
            syslog('xmlrpc',
                   'Strange subscription information for list: %s',
                   list_name)
            return
        # Lock the list and make the modifications.  Don't worry if the list
        # couldn't be locked, we'll just log that and try again the next time
        # through the loop.  Eventually any existing lock will expire anyway.
        try:
            mlist.Lock(2)
        except TimeOutError:
            syslog('xmlrpc',
                   'Could not lock the list to update subscriptions: %s',
                   list_name)
            return
        try:
            # Handle additions first.
            if len(additions) > 0:
                syslog('xmlrpc', 'Adding to %s: %s', list_name, additions)
            for address in additions:
                # When adding the new member, be sure to use the
                # case-preserved email address.
                original_address = key_to_case_preserved[address]
                realname, flags, status = member_map[original_address]
                mlist.addNewMember(original_address, realname=realname)
                mlist.setDeliveryStatus(original_address, status)
            # Handle deletions next.
            if len(deletions) > 0:
                syslog('xmlrpc', 'Removing from %s: %s', list_name, deletions)
            for address in deletions:
                mlist.removeMember(address)
            # Updates can be either a settings update, a change in the
            # case of the subscribed address, or both.
            found_updates = []
            for address in updates:
                # See if the case is changing.
                current_address = mlist.getMemberCPAddress(address)
                future_address = key_to_case_preserved[address]
                if current_address != future_address:
                    mlist.changeMemberAddress(address, future_address)
                    found_updates.append('%s -> %s' %
                                         (address, future_address))
                # flags are ignored for now.
                realname, flags, status = member_map[future_address]
                if realname != mlist.getMemberName(address):
                    mlist.setMemberName(address, realname)
                    found_updates.append('%s new name: %s' %
                                         (address, realname))
                if status != mlist.getDeliveryStatus(address):
                    mlist.setDeliveryStatus(address, status)
                    found_updates.append('%s new status: %s' %
                                         (address, status))
            if len(found_updates) > 0:
                syslog('xmlrpc', 'Membership updates for %s: %s',
                       list_name, found_updates)
            # We're done, so flush the changes for this mailing list.
            mlist.Save()
        finally:
            mlist.Unlock()

    def _get_subscriptions(self):
        """Get the latest subscription information."""
        # First, calculate the names of the active mailing lists.
        lists = sorted(list_name
                       for list_name in Utils.list_names()
                       if list_name != mm_cfg.MAILMAN_SITE_LIST)
        # Batch the subscription requests in order to reduce the possibility
        # of timeouts in the XMLRPC server.  Note that we cannot eliminate
        # timeouts, which will cause an entire batch to fail.  To reduce the
        # possibility that the same batch of teams will always fail, we
        # shuffle the list of team names so the batches will always be
        # different.
        shuffle(lists)
        while lists:
            if self._shortcircuit():
                # Stop was called during a long network call.
                return
            batch = lists[:mm_cfg.XMLRPC_SUBSCRIPTION_BATCH_SIZE]
            lists = lists[mm_cfg.XMLRPC_SUBSCRIPTION_BATCH_SIZE:]
            ## syslog('xmlrpc', 'batch: %s', batch)
            ## syslog('xmlrpc', 'lists: %s', lists)
            # Get the information for this batch of mailing lists.
            try:
                info = self._proxy.getMembershipInformation(batch)
            except (xmlrpclib.ProtocolError, socket.error) as error:
                log_exception('Cannot talk to Launchpad: %s', error)
                syslog('xmlrpc', 'batch: %s', batch)
                continue
            except xmlrpclib.Fault as error:
                log_exception('Launchpad exception: %s', error)
                syslog('xmlrpc', 'batch: %s', batch)
                continue
            for list_name in info:
                subscription_info = info[list_name]
                # The subscription info for a mailing list can be None,
                # meaning that there are no subscribers or allowed posters.
                # The latter can only happen if there are no active team
                # members, and that can only happen when the owner has been
                # specifically deactivate for some reason.  This is not an
                # error condition.
                if subscription_info is not None:
                    self._update_list_subscriptions(
                        list_name, subscription_info)

    def _create_or_reactivate(self, actions, statuses):
        """Process mailing list creation and reactivation actions.

        actions is a sequence of (team_name, initializer) tuples where the
        team_name is the name of the mailing list to create and initializer is
        a dictionary of initial custom values to set on the new mailing list.

        statuses is a dictionary mapping team names to one of the strings
        'success' or 'failure'.
        """
        for team_name, initializer in actions:
            # This is a set of attributes defining the defaults for lists
            # created under Launchpad's control.  We need to map attribute
            # names as Launchpad sees them to attribute names on the MailList
            # object.
            list_defaults = {}
            # Verify that the initializer variables are what we expect.
            for key in attrmap:
                if key in initializer:
                    list_defaults[attrmap[key]] = initializer[key]
                    del initializer[key]
            if initializer:
                # Reject this list creation request.
                statuses[team_name] = ('create', 'failure')
                syslog('xmlrpc', 'Unexpected create settings: %s',
                       COMMASPACE.join(initializer))
                continue
            # Either the mailing list was deactivated at one point, or it
            # never existed in the first place.  Look for a backup tarfile; if
            # it exists, this is a reactivation, otherwise it is the initial
            # creation.
            tgz_file_name = os.path.join(
                mm_cfg.VAR_PREFIX, 'backups', team_name + '.tgz')
            try:
                tgz_file = tarfile.open(tgz_file_name, 'r:gz')
            except IOError as error:
                if error.errno != errno.ENOENT:
                    raise
                # The archive tarfile does not exist, meaning this is the
                # initial creation request.
                action = 'created'
                status = self._create(team_name)
            else:
                # This is a reactivation request.  Unpack the archived tarball
                # into the lists directory.
                action = 'reactivated'
                status = self._reactivate(team_name, tgz_file)
                tgz_file.close()
                if status:
                    os.remove(tgz_file_name)
            # If the list was successfully created or reactivated, apply
            # defaults.  Otherwise, set the failure status and return.
            if not status:
                syslog('xmlrpc', 'An error occurred; the list was not %s: %s',
                       action, team_name)
                statuses[team_name] = ('reactivate', 'failure')
                return
            self._apply_list_defaults(team_name, list_defaults)
            statuses[team_name] = ('create/reactivate', 'success')

    def _apply_list_defaults(self, team_name, list_defaults):
        """Apply mailing list defaults and tie the new list into the MTA."""
        mlist = MailList(team_name)
        try:
            for key, value in list_defaults.items():
                setattr(mlist, key, value)
            # Do MTA specific creation steps.
            if mm_cfg.MTA:
                modname = 'Mailman.MTA.' + mm_cfg.MTA
                __import__(modname)
                sys.modules[modname].create(mlist, quiet=True)
            mlist.Save()
        finally:
            mlist.Unlock()

    def _reactivate(self, team_name, tgz_file):
        """Reactivate an archived mailing list from backup file."""
        lists_dir = os.path.join(mm_cfg.VAR_PREFIX, 'lists')
        # Temporarily change to the top level `lists` directory, since all the
        # tar files have paths relative to that.
        old_cwd = os.getcwd()
        try:
            os.chdir(lists_dir)
            tgz_file.extractall()
        finally:
            os.chdir(old_cwd)
        syslog('xmlrpc', '%s: %s', lists_dir, os.listdir(lists_dir))
        return True

    def _create(self, team_name):
        """Create a new mailing list."""
        # Create the mailing list and set the defaults.
        mlist = MailList()
        try:
            # Use a fake list admin password; Mailman will never be
            # administered from its web u/i.  Nor will the mailing list
            # require an owner that's different from the site owner.  Also by
            # default, only English is supported.
            try:
                mlist.Create(team_name,
                             mm_cfg.SITE_LIST_OWNER,
                             ' no password ')
                # Additional hard coded list defaults.
                # - Personalize regular delivery so that we can VERP these.
                # - Turn off RFC 2369 headers; we'll do them differently
                # - enable $-string substitutions in headers/footers
                mlist.personalize = 1
                mlist.include_rfc2369_headers = False
                mlist.use_dollar_strings = True
                mlist.held_message_ids = {}
                mlist.Save()
                # Now create the archive directory for MHonArc.
                path = os.path.join(mm_cfg.VAR_PREFIX, 'mhonarc', team_name)
                os.makedirs(path)
            # We have to use a bare except here because of the legacy string
            # exceptions that Mailman can raise.
            except:
                log_exception('List creation error for team: %s', team_name)
                return False
            else:
                return True
        finally:
            mlist.Unlock()

    def _modify(self, actions, statuses):
        """Process mailing list modification actions.

        actions is a sequence of (team_name, modifications) tuples where the
        team_name is the name of the mailing list to create and modifications
        is a dictionary of values to set on the mailing list.

        statuses is a dictionary mapping team names to one of the strings
        'success' or 'failure'.
        """
        for team_name, modifications in actions:
            # First, validate the modification keywords.
            list_settings = {}
            for key in attrmap:
                if key in modifications:
                    list_settings[attrmap[key]] = modifications[key]
                    del modifications[key]
            if modifications:
                statuses[team_name] = ('modify', 'failure')
                syslog('xmlrpc', 'Unexpected modify settings: %s',
                       COMMASPACE.join(modifications))
                continue
            try:
                mlist = MailList(team_name)
                try:
                    for key, value in list_settings.items():
                        setattr(mlist, key, value)
                    mlist.Save()
                finally:
                    mlist.Unlock()
            # We have to use a bare except here because of the legacy string
            # exceptions that Mailman can raise.
            except:
                log_exception(
                    'List modification error for team: %s', team_name)
                statuses[team_name] = ('modify', 'failure')
            else:
                statuses[team_name] = ('modify', 'success')

    def _deactivate(self, actions, statuses):
        """Process mailing list deactivation actions.

        actions is a sequence of team names for the mailing lists to
        deactivate.

        statuses is a dictionary mapping team names to one of the strings
        'success' or 'failure'.
        """
        for team_name in actions:
            try:
                mlist = MailList(team_name, lock=False)
                if mm_cfg.MTA:
                    modname = 'Mailman.MTA.' + mm_cfg.MTA
                    __import__(modname)
                    sys.modules[modname].remove(mlist, quiet=True)
                # The archives are always persistent, so all we need to do to
                # deactivate a list is to delete the 'lists/team_name'
                # directory.  However, in order to support easy reactivation,
                # and to provide a backup in case of error, we create a gzip'd
                # tarball of the list directory.
                lists_dir = os.path.join(mm_cfg.VAR_PREFIX, 'lists')
                # To make reactivation easier, we temporarily cd to the
                # $var/lists directory and make the tarball from there.
                old_cwd = os.getcwd()
                # XXX BarryWarsaw 2007-08-02: Should we watch out for
                # collisions on the tar file name?  This can only happen if
                # the team is resurrected but the old archived tarball backup
                # wasn't removed.
                tgz_file_name = os.path.join(
                    mm_cfg.VAR_PREFIX, 'backups', team_name + '.tgz')
                tgz_file = tarfile.open(tgz_file_name, 'w:gz')
                try:
                    os.chdir(lists_dir)
                    # .add() works recursively by default.
                    tgz_file.add(team_name)
                    # Now delete the list's directory.
                    shutil.rmtree(team_name)
                finally:
                    tgz_file.close()
                    os.chdir(old_cwd)
            # We have to use a bare except here because of the legacy string
            # exceptions that Mailman can raise.
            except:
                log_exception('List deletion error for team: %s', team_name)
                statuses[team_name] = ('deactivate', 'failure')
            else:
                statuses[team_name] = ('deactivate', 'success')

    def _check_held_messages(self):
        """See if any held messages have been accepted or rejected."""
        try:
            dispositions = self._proxy.getMessageDispositions()
        except (xmlrpclib.ProtocolError, socket.error) as error:
            log_exception('Cannot talk to Launchpad:\n%s', error)
            return
        except xmlrpclib.Fault as error:
            log_exception('Launchpad exception: %s', error)
            return
        if dispositions:
            syslog('xmlrpc',
                   'Received dispositions for these message-ids: %s',
                   COMMASPACE.join(dispositions))
        else:
            return
        # For each message that has been acted upon in Launchpad, handle the
        # message in here in Mailman.  We need to resort the dispositions so
        # that we can handle all of them for a particular mailing list at the
        # same time.
        by_list = {}
        for message_id, (team_name, action) in dispositions.items():
            accepts, declines, discards = by_list.setdefault(
                team_name, ([], [], []))
            if action == 'accept':
                accepts.append(message_id)
            elif action == 'decline':
                declines.append(message_id)
            elif action == 'discard':
                discards.append(message_id)
            else:
                syslog('xmlrpc',
                       'Skipping invalid disposition "%s" for message-id: %s',
                       action, message_id)
        # Now cycle through the dispositions for every mailing list.
        for team_name in by_list:
            try:
                mlist = MailList(team_name)
            except Errors.MMUnknownListError:
                log_exception(
                    'Skipping dispositions for unknown list: %s', team_name)
                continue
            try:
                accepts, declines, discards = by_list[team_name]
                for message_id in accepts:
                    request_id = mlist.held_message_ids.pop(message_id, None)
                    if request_id is None:
                        syslog('xmlrpc', 'Missing accepted message-id: %s',
                               message_id)
                    else:
                        mlist.HandleRequest(request_id, mm_cfg.APPROVE)
                        syslog('xmlrpc', 'Approved: %s', message_id)
                for message_id in declines:
                    request_id = mlist.held_message_ids.pop(message_id, None)
                    if request_id is None:
                        syslog('xmlrpc', 'Missing declined message-id: %s',
                               message_id)
                    else:
                        mlist.HandleRequest(request_id, mm_cfg.REJECT)
                        syslog('xmlrpc', 'Rejected: %s', message_id)
                for message_id in discards:
                    request_id = mlist.held_message_ids.pop(message_id, None)
                    if request_id is None:
                        syslog('xmlrpc', 'Missing declined message-id: %s',
                               message_id)
                    else:
                        mlist.HandleRequest(request_id, mm_cfg.DISCARD)
                        syslog('xmlrpc', 'Discarded: %s', message_id)
                mlist.Save()
            finally:
                mlist.Unlock()

    def _resynchronize(self, actions, statuses):
        """Process resynchronization actions.

        actions is a sequence of 2-tuples specifying what needs to be
        resynchronized.  The tuple is of the form (listname, current-status).

        statuses is a dictionary mapping team names to one of the strings
        'success' or 'failure'.
        """
        syslog('xmlrpc', 'resynchronizing: %s',
               COMMASPACE.join(sorted(name for (name, status) in actions)))
        for name, status in actions:
            # There's no way to really know whether the original action
            # succeeded or not, however, it's unlikely that an action would
            # fail leaving the mailing list in a usable state.  Therefore, if
            # the list is loadable and lockable, we'll say it succeeded.
            try:
                mlist = MailList(name)
            except Errors.MMUnknownListError:
                # The list doesn't exist on the Mailman side, so if its status
                # is CONSTRUCTING, we can create it now.
                if status == 'constructing':
                    if self._create(name):
                        statuses[name] = ('resynchronize', 'success')
                    else:
                        statuses[name] = ('resynchronize', 'failure')
                else:
                    # Any other condition leading to an unknown list is a
                    # failure state.
                    statuses[name] = ('resynchronize', 'failure')
            except:
                # Any other exception is also a failure.
                statuses[name] = ('resynchronize', 'failure')
                log_exception('Mailing list does not load: %s', name)
            else:
                # The list loaded just fine, so it successfully
                # resynchronized.  Be sure to unlock it!
                mlist.Unlock()
                statuses[name] = ('resynchronize', 'success')
