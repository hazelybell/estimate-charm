# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BugWatch',
    'BugWatchActivity',
    'BugWatchDeletionError',
    'BugWatchSet',
    ]

from datetime import datetime
import re
import urllib
from urlparse import urlunsplit

from lazr.lifecycle.event import ObjectModifiedEvent
from lazr.lifecycle.snapshot import Snapshot
from lazr.uri import find_uris_in_text
from pytz import utc
from sqlobject import (
    ForeignKey,
    SQLObjectNotFound,
    StringCol,
    )
from storm.expr import (
    Desc,
    Not,
    )
from storm.locals import (
    Int,
    Reference,
    Unicode,
    )
from storm.store import Store
from zope.component import getUtility
from zope.event import notify
from zope.interface import (
    implements,
    providedBy,
    )

from lp.app.errors import NotFoundError
from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.app.validators.email import valid_email
from lp.bugs.interfaces.bugtracker import (
    BugTrackerType,
    IBugTrackerSet,
    )
from lp.bugs.interfaces.bugwatch import (
    BUG_WATCH_ACTIVITY_SUCCESS_STATUSES,
    BugWatchActivityStatus,
    BugWatchCannotBeRescheduled,
    IBugWatch,
    IBugWatchActivity,
    IBugWatchSet,
    NoBugTrackerFound,
    UnrecognizedBugTrackerURL,
    )
from lp.bugs.model.bugmessage import BugMessage
from lp.bugs.model.bugtask import BugTask
from lp.registry.interfaces.person import validate_public_person
from lp.services.database import bulk
from lp.services.database.constants import UTC_NOW
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import SQLBase
from lp.services.database.stormbase import StormBase
from lp.services.helpers import (
    ensure_unicode,
    shortlist,
    )
from lp.services.messages.model.message import Message
from lp.services.webapp import (
    urlappend,
    urlsplit,
    )


BUG_TRACKER_URL_FORMATS = {
    BugTrackerType.BUGZILLA: 'show_bug.cgi?id=%s',
    BugTrackerType.DEBBUGS: 'cgi-bin/bugreport.cgi?bug=%s',
    BugTrackerType.GOOGLE_CODE: 'detail?id=%s',
    BugTrackerType.MANTIS: 'view.php?id=%s',
    BugTrackerType.ROUNDUP: 'issue%s',
    BugTrackerType.RT: 'Ticket/Display.html?id=%s',
    BugTrackerType.SOURCEFORGE: 'support/tracker.php?aid=%s',
    BugTrackerType.TRAC: 'ticket/%s',
    BugTrackerType.SAVANE: 'bugs/?%s',
    BugTrackerType.PHPPROJECT: 'bug.php?id=%s',
    }


WATCH_RESCHEDULE_THRESHOLD = 0.6


def get_bug_watch_ids(references):
    """Yield bug watch IDs from any given iterator.

    For each item in the given iterators, yields the ID if it provides
    IBugWatch, and yields if it is an integer. Everything else is
    discarded.
    """

    for reference in references:
        if IBugWatch.providedBy(reference):
            yield reference.id
        elif isinstance(reference, (int, long)):
            yield reference
        else:
            raise AssertionError(
                '%r is not a bug watch or an ID.' % (reference,))


class BugWatchDeletionError(Exception):
    """Raised when someone attempts to delete a linked watch."""


class BugWatch(SQLBase):
    """See `IBugWatch`."""
    implements(IBugWatch)
    _table = 'BugWatch'
    bug = ForeignKey(dbName='bug', foreignKey='Bug', notNull=True)
    bugtracker = ForeignKey(dbName='bugtracker',
                foreignKey='BugTracker', notNull=True)
    remotebug = StringCol(notNull=True)
    remotestatus = StringCol(notNull=False, default=None)
    remote_importance = StringCol(notNull=False, default=None)
    lastchanged = UtcDateTimeCol(notNull=False, default=None)
    lastchecked = UtcDateTimeCol(notNull=False, default=None)
    last_error_type = EnumCol(schema=BugWatchActivityStatus, default=None)
    datecreated = UtcDateTimeCol(notNull=True, default=UTC_NOW)
    owner = ForeignKey(
        dbName='owner', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)
    next_check = UtcDateTimeCol()

    @property
    def bugtasks(self):
        tasks = Store.of(self).find(BugTask, BugTask.bugwatch == self.id)
        tasks = tasks.order_by(Desc(BugTask.datecreated))
        return shortlist(tasks, 10, 100)

    @property
    def bugtasks_to_update(self):
        """Yield the bug tasks that are eligible for update."""
        for bugtask in self.bugtasks:
            # We don't update conjoined bug tasks; they must be
            # updated through their conjoined masters.
            if bugtask.conjoined_master is not None:
                continue
            # We don't update tasks of duplicate bugs.
            if bugtask.bug.duplicateof is not None:
                continue
            # Update this one.
            yield bugtask

    @property
    def title(self):
        """See `IBugWatch`."""
        return "%s #%s" % (self.bugtracker.title, self.remotebug)

    @property
    def url(self):
        """See `IBugWatch`."""
        bugtracker = self.bugtracker
        bugtrackertype = self.bugtracker.bugtrackertype

        if bugtrackertype == BugTrackerType.EMAILADDRESS:
            return bugtracker.baseurl
        elif bugtrackertype in BUG_TRACKER_URL_FORMATS:
            url_format = BUG_TRACKER_URL_FORMATS[bugtrackertype]
            return urlappend(bugtracker.baseurl,
                             url_format % self.remotebug)
        else:
            raise AssertionError(
                'Unknown bug tracker type %s' % bugtrackertype)

    @property
    def needscheck(self):
        """See `IBugWatch`."""
        return True

    def updateImportance(self, remote_importance, malone_importance):
        """See `IBugWatch`."""
        if self.remote_importance != remote_importance:
            self.remote_importance = remote_importance
            self.lastchanged = UTC_NOW
            # Sync the object in order to convert the UTC_NOW sql
            # constant to a datetime value.
            self.sync()
        for linked_bugtask in self.bugtasks_to_update:
            old_bugtask = Snapshot(
                linked_bugtask, providing=providedBy(linked_bugtask))
            linked_bugtask.transitionToImportance(
                malone_importance,
                getUtility(ILaunchpadCelebrities).bug_watch_updater)
            if linked_bugtask.importance != old_bugtask.importance:
                event = ObjectModifiedEvent(
                    linked_bugtask, old_bugtask, ['importance'],
                    user=getUtility(ILaunchpadCelebrities).bug_watch_updater)
                notify(event)

    def updateStatus(self, remote_status, malone_status):
        """See `IBugWatch`."""
        if self.remotestatus != remote_status:
            self.remotestatus = remote_status
            self.lastchanged = UTC_NOW
            # Sync the object in order to convert the UTC_NOW sql
            # constant to a datetime value.
            self.sync()
        for linked_bugtask in self.bugtasks_to_update:
            old_bugtask = Snapshot(
                linked_bugtask, providing=providedBy(linked_bugtask))
            linked_bugtask.transitionToStatus(
                malone_status,
                getUtility(ILaunchpadCelebrities).bug_watch_updater)
            # We don't yet support updating the assignee of bug watches.
            linked_bugtask.transitionToAssignee(None)
            if linked_bugtask.status != old_bugtask.status:
                event = ObjectModifiedEvent(
                    linked_bugtask, old_bugtask, ['status'],
                    user=getUtility(ILaunchpadCelebrities).bug_watch_updater)
                notify(event)

    def destroySelf(self):
        """See `IBugWatch`."""
        if (len(self.bugtasks) > 0 or
            not self.getImportedBugMessages().is_empty()):
            raise BugWatchDeletionError(
                "Can't delete bug watches linked to tasks or comments.")
        # Remove any BugWatchActivity entries for this bug watch.
        self.activity.remove()
        # XXX 2010-09-29 gmb bug=647103
        #     We flush the store to make sure that errors bubble up and
        #     are caught by the OOPS machinery.
        SQLBase.destroySelf(self)
        store = Store.of(self)
        store.flush()

    @property
    def unpushed_comments(self):
        """Return the unpushed comments for this `BugWatch`."""
        store = Store.of(self)
        bug_messages = store.find(
            BugMessage,
            BugMessage.message == Message.id,
            BugMessage.bug == self.bug,
            BugMessage.bugwatch == self,
            BugMessage.remote_comment_id == None)

        # Ordering by the id is only necessary to avoid randomness
        # caused by identical dates, which can break tests.
        return bug_messages.order_by(Message.datecreated, Message.id)

    def hasComment(self, comment_id):
        """See `IBugWatch`."""
        store = Store.of(self)
        bug_messages = store.find(
            BugMessage,
            BugMessage.bug == self.bug.id,
            BugMessage.bugwatch == self.id,
            BugMessage.remote_comment_id == comment_id)

        return bug_messages.any() is not None

    def addComment(self, comment_id, message):
        """See `IBugWatch`."""
        assert not self.hasComment(comment_id), ("Comment with ID %s has "
            "already been imported for %s." % (comment_id, self.title))

        # When linking the message we force the owner being used to the
        # Bug Watch Updater celebrity. This allows us to avoid trying to
        # assign karma to the authors of imported comments, since karma
        # should only be assigned for actions that occur within
        # Launchpad. See bug 185413 for more details.
        bug_watch_updater = getUtility(
            ILaunchpadCelebrities).bug_watch_updater
        bug_message = self.bug.linkMessage(
            message, bugwatch=self, user=bug_watch_updater,
            remote_comment_id=comment_id)
        return bug_message

    def getBugMessages(self, clauses=[]):
        return Store.of(self).find(
            BugMessage, BugMessage.bug == self.bug.id,
            BugMessage.bugwatch == self.id, *clauses)

    def getImportedBugMessages(self):
        """See `IBugWatch`."""
        return self.getBugMessages([BugMessage.remote_comment_id != None])

    def addActivity(self, result=None, message=None, oops_id=None):
        """See `IBugWatch`."""
        activity = BugWatchActivity()
        activity.bug_watch = self
        if result is None:
            # If no result is passed we assume that the activity
            # succeded and set the result field accordingly.
            activity.result = BugWatchActivityStatus.SYNC_SUCCEEDED
        else:
            activity.result = result
        if message is not None:
            activity.message = unicode(message)
        if oops_id is not None:
            activity.oops_id = unicode(oops_id)
        store = IStore(BugWatchActivity)
        store.add(activity)

    @property
    def activity(self):
        store = Store.of(self)
        return store.find(
            BugWatchActivity,
            BugWatchActivity.bug_watch == self).order_by(
                Desc('activity_date'))

    @property
    def can_be_rescheduled(self):
        """See `IBugWatch`."""
        if (self.next_check is not None and
            self.next_check <= datetime.now(utc)):
            # If the watch is already scheduled for a time in the past
            # (or for right now) it can't be rescheduled, since it
            # should be checked by the next checkwatches run anyway.
            return False

        if self.activity.is_empty():
            # Don't show the reschedule button if the watch has never
            # been checked.
            return False

        if self.activity[0].result in BUG_WATCH_ACTIVITY_SUCCESS_STATUSES:
            # If the last update was successful the watch can't be
            # rescheduled.
            return False

        if self.failed_activity.is_empty():
            # Don't show the reschedule button if the watch has never
            # failed.
            return False

        if self.failed_activity.count() == 1 and self.activity.count() == 1:
            # In cases where a watch has been updated once and failed,
            # we allow the user to reschedule it.
            return True

        # If the ratio is lower than the reschedule threshold, we
        # can show the button.
        failure_ratio = (
            float(self.failed_activity.count()) /
            self.activity.count())
        return failure_ratio <= WATCH_RESCHEDULE_THRESHOLD

    @property
    def failed_activity(self):
        return Store.of(self).find(
            BugWatchActivity,
            BugWatchActivity.bug_watch == self,
            Not(BugWatchActivity.result.is_in(
                BUG_WATCH_ACTIVITY_SUCCESS_STATUSES))).order_by(
                Desc('activity_date'))

    def setNextCheck(self, next_check):
        """See `IBugWatch`."""
        if not self.can_be_rescheduled:
            raise BugWatchCannotBeRescheduled()

        self.next_check = next_check

    def reset(self):
        """See `IBugWatch`."""
        self.last_error_type = None
        self.lastchanged = None
        self.lastchecked = None
        self.next_check = UTC_NOW
        self.remote_importance = None
        self.remotestatus = None


class BugWatchSet:
    """A set for BugWatch"""

    implements(IBugWatchSet)

    def __init__(self, bug=None):
        self.bugtracker_parse_functions = {
            BugTrackerType.BUGZILLA: self.parseBugzillaURL,
            BugTrackerType.DEBBUGS: self.parseDebbugsURL,
            BugTrackerType.EMAILADDRESS: self.parseEmailAddressURL,
            BugTrackerType.GOOGLE_CODE: self.parseGoogleCodeURL,
            BugTrackerType.MANTIS: self.parseMantisURL,
            BugTrackerType.PHPPROJECT: self.parsePHPProjectURL,
            BugTrackerType.ROUNDUP: self.parseRoundupURL,
            BugTrackerType.RT: self.parseRTURL,
            BugTrackerType.SAVANE: self.parseSavaneURL,
            BugTrackerType.SOURCEFORGE: self.parseSourceForgeLikeURL,
            BugTrackerType.TRAC: self.parseTracURL,
            }

    def get(self, watch_id):
        """See `IBugWatch`Set."""
        try:
            return BugWatch.get(watch_id)
        except SQLObjectNotFound:
            raise NotFoundError(watch_id)

    def search(self):
        return BugWatch.select()

    def fromText(self, text, bug, owner):
        """See `IBugWatchSet`."""
        newwatches = []
        # Let's find all the URLs and see if they are bug references.
        matches = list(find_uris_in_text(text))
        if len(matches) == 0:
            return []

        for url in matches:
            try:
                bugtracker, remotebug = self.extractBugTrackerAndBug(str(url))
            except NoBugTrackerFound as error:
                # We don't want to auto-create EMAILADDRESS bug trackers
                # based on mailto: URIs in comments.
                if error.bugtracker_type == BugTrackerType.EMAILADDRESS:
                    continue

                bugtracker = getUtility(IBugTrackerSet).ensureBugTracker(
                    error.base_url, owner, error.bugtracker_type)
                remotebug = error.remote_bug
            except UnrecognizedBugTrackerURL:
                # It doesn't look like a bug URL, so simply ignore it.
                continue

            # We don't create bug watches for EMAILADDRESS bug trackers
            # from mailto: URIs in comments, so in those cases we give
            # up.
            if bugtracker.bugtrackertype == BugTrackerType.EMAILADDRESS:
                continue

            if bug.getBugWatch(bugtracker, remotebug) is None:
                # This bug doesn't have such a bug watch, let's create
                # one.
                bugwatch = bug.addWatch(
                    bugtracker=bugtracker, remotebug=remotebug, owner=owner)
                newwatches.append(bugwatch)

        return newwatches

    def fromMessage(self, message, bug):
        """See `IBugWatchSet`."""
        watches = set()
        for messagechunk in message:
            if messagechunk.blob is not None:
                # we don't process attachments
                continue
            elif messagechunk.content is not None:
                # look for potential BugWatch URL's and create the trackers
                # and watches as needed
                watches = watches.union(self.fromText(messagechunk.content,
                    bug, message.owner))
            else:
                raise AssertionError('MessageChunk without content or blob.')
        return sorted(watches, key=lambda a: a.remotebug)

    def createBugWatch(self, bug, owner, bugtracker, remotebug):
        """See `IBugWatchSet`."""
        return BugWatch(
            bug=bug, owner=owner, datecreated=UTC_NOW, lastchanged=UTC_NOW,
            bugtracker=bugtracker, remotebug=remotebug)

    def parseBugzillaURL(self, scheme, host, path, query):
        """Extract the Bugzilla base URL and bug ID."""
        bug_page = 'show_bug.cgi'
        if not path.endswith(bug_page):
            return None
        if query.get('id'):
            # This is a Bugzilla URL.
            remote_bug = query['id']
        elif query.get('issue'):
            # This is a Issuezilla URL.
            remote_bug = query['issue']
        else:
            return None
        if remote_bug is None or not remote_bug.isdigit():
            return None
        base_path = path[:-len(bug_page)]
        base_url = urlunsplit((scheme, host, base_path, '', ''))
        return base_url, remote_bug

    def parseMantisURL(self, scheme, host, path, query):
        """Extract the Mantis base URL and bug ID."""
        bug_page = 'view.php'
        if not path.endswith(bug_page):
            return None
        remote_bug = query.get('id')
        if remote_bug is None or not remote_bug.isdigit():
            return None
        base_path = path[:-len(bug_page)]
        base_url = urlunsplit((scheme, host, base_path, '', ''))
        return base_url, remote_bug

    def parseDebbugsURL(self, scheme, host, path, query):
        """Extract the Debbugs base URL and bug ID."""
        bug_page = 'cgi-bin/bugreport.cgi'
        remote_bug = None

        if path.endswith(bug_page):
            remote_bug = query.get('bug')
            base_path = path[:-len(bug_page)]
        elif host == "bugs.debian.org":
            # Oy, what a hack. debian's tracker allows you to access
            # bugs by saying http://bugs.debian.org/400848, so support
            # that shorthand. The reason we need to do this special
            # check here is because otherwise /any/ URL that ends with
            # "/number" will appear to match a debbugs URL.
            remote_bug = path.split("/")[-1]
            base_path = ''
        else:
            return None

        if remote_bug is None or not remote_bug.isdigit():
            return None

        base_url = urlunsplit((scheme, host, base_path, '', ''))
        return base_url, remote_bug

    def parseRoundupURL(self, scheme, host, path, query):
        """Extract the RoundUp base URL and bug ID."""
        match = re.match(r'(.*/)issue(\d+)$', path)
        if not match:
            return None
        base_path = match.group(1)
        remote_bug = match.group(2)

        base_url = urlunsplit((scheme, host, base_path, '', ''))
        return base_url, remote_bug

    def parseRTURL(self, scheme, host, path, query):
        """Extract the RT base URL and bug ID."""

        # We use per-host regular expressions to account for those RT
        # hosts that we know use non-standard URLs for their tickets,
        # allowing us to parse them properly.
        host_expressions = {
            'default': r'(.*/)(Bug|Ticket)/Display.html',
            'rt.cpan.org': r'(.*/)Public/(Bug|Ticket)/Display.html'}

        if host in host_expressions:
            expression = host_expressions[host]
        else:
            expression = host_expressions['default']

        match = re.match(expression, path)
        if not match:
            return None

        base_path = match.group(1)
        remote_bug = query['id']
        if remote_bug is None or not remote_bug.isdigit():
            return None

        base_url = urlunsplit((scheme, host, base_path, '', ''))
        return base_url, remote_bug

    def parseTracURL(self, scheme, host, path, query):
        """Extract the Trac base URL and bug ID."""
        match = re.match(r'(.*/)ticket/(\d+)$', path)
        if not match:
            return None
        base_path = match.group(1)
        remote_bug = match.group(2)

        base_url = urlunsplit((scheme, host, base_path, '', ''))
        return base_url, remote_bug

    def parseSourceForgeLikeURL(self, scheme, host, path, query):
        """Extract the SourceForge-like base URLs and bug IDs.

        Both path and hostname are considered. If the hostname
        corresponds to one of the aliases for the SourceForge celebrity,
        that celebrity will be returned (there can be only one
        SourceForge instance in Launchpad).
        """
        # We're only interested in URLs that look like they come from a
        # *Forge bugtracker. The valid URL schemes are:
        # * /support/tracker.php
        # * /tracker/(index.php) (index.php part is optional)
        # * /tracker2/(index.php) (index.php part is optional)
        sf_path_re = re.compile(
            '^\/(support\/tracker\.php|tracker2?\/(index\.php)?)$')
        if (sf_path_re.match(path) is None):
            return None
        if not query.get('aid'):
            return None

        remote_bug = query['aid']
        if remote_bug is None or not remote_bug.isdigit():
            return None

        # There's only one global SF instance registered in Launchpad,
        # so we return that if the hostnames match.
        sf_tracker = getUtility(ILaunchpadCelebrities).sourceforge_tracker
        sf_hosts = [urlsplit(alias)[1] for alias in sf_tracker.aliases]
        sf_hosts.append(urlsplit(sf_tracker.baseurl)[2])
        if host in sf_hosts:
            return sf_tracker.baseurl, remote_bug
        else:
            base_url = urlunsplit((scheme, host, '/', '', ''))
            return base_url, remote_bug

    def parseSavaneURL(self, scheme, host, path, query):
        """Extract Savane base URL and bug ID."""
        # Savane bugs URLs are in the form /bugs/?<bug-id>, so we
        # exclude any path that isn't '/bugs/'. We also exclude query
        # string that have a length of more or less than one, since in
        # such cases we'd be taking a guess at the bug ID, which would
        # probably be wrong.
        if path != '/bugs/' or len(query) != 1:
            return None

        # There's only one global Savannah bugtracker registered with
        # Launchpad, so we return that one if the hostname matches.
        savannah_tracker = getUtility(ILaunchpadCelebrities).savannah_tracker
        savannah_hosts = [
            urlsplit(alias)[1] for alias in savannah_tracker.aliases]
        savannah_hosts.append(urlsplit(savannah_tracker.baseurl)[1])

        # The remote bug is actually a key in the query dict rather than
        # a value, so we simply use the first and only key we come
        # across as a best-effort guess.
        remote_bug = query.popitem()[0]
        if remote_bug is None or not remote_bug.isdigit():
            return None

        if host in savannah_hosts:
            return savannah_tracker.baseurl, remote_bug
        else:
            base_url = urlunsplit((scheme, host, '/', '', ''))
            return base_url, remote_bug

    def parseEmailAddressURL(self, scheme, host, path, query):
        """Extract an email address from a bug URL.

        This method will return (mailto:<email_address>, '') since email
        address bug trackers cannot have bug numbers. We return an empty
        string for the remote bug since BugWatch.remotebug cannot be
        None.
        """
        # We ignore anything that isn't a mailto URL.
        if scheme != 'mailto':
            return None

        # We also reject invalid email addresses.
        if not valid_email(path):
            return None

        return '%s:%s' % (scheme, path), ''

    def parsePHPProjectURL(self, scheme, host, path, query):
        """Extract a PHP project bug tracker base URL and bug ID."""
        # The URLs have the form bug.php?id=<bug-id>.
        if path != '/bug.php' or len(query) != 1:
            return None
        remote_bug = query.get('id')
        if remote_bug is None or not remote_bug.isdigit():
            return None
        base_url = urlunsplit((scheme, host, '/', '', ''))
        return base_url, remote_bug

    def parseGoogleCodeURL(self, scheme, host, path, query):
        """Extract a Google Code bug tracker base URL and bug ID."""
        if host != 'code.google.com':
            return None

        google_code_url_expression = re.compile(
            "(?P<base_path>\/p\/[a-z][-a-z0-9]+/issues)/detail")

        path_match = google_code_url_expression.match(path)
        if path_match is None:
            return None

        remote_bug = query.get('id')
        if remote_bug is None or not remote_bug.isdigit():
            return None

        tracker_path = path_match.groupdict()['base_path']
        base_url = urlunsplit((scheme, host, tracker_path, '', ''))
        return base_url, remote_bug

    def extractBugTrackerAndBug(self, url):
        """See `IBugWatchSet`."""
        for trackertype, parse_func in (
            self.bugtracker_parse_functions.items()):
            scheme, host, path, query_string, frag = urlsplit(url)
            query = {}
            for query_part in query_string.split('&'):
                key, value = urllib.splitvalue(query_part)
                query[key] = value

            bugtracker_data = parse_func(scheme, host, path, query)
            if not bugtracker_data:
                continue
            base_url, remote_bug = bugtracker_data
            # Check whether we have a registered bug tracker already.
            bugtracker = getUtility(IBugTrackerSet).queryByBaseURL(base_url)

            if bugtracker is not None:
                return bugtracker, remote_bug
            else:
                raise NoBugTrackerFound(base_url, remote_bug, trackertype)

        raise UnrecognizedBugTrackerURL(url)

    def getBugWatchesForRemoteBug(self, remote_bug, bug_watch_ids=None):
        """See `IBugWatchSet`."""
        query = IStore(BugWatch).find(
            BugWatch, BugWatch.remotebug == remote_bug)
        if bug_watch_ids is not None:
            query = query.find(BugWatch.id.is_in(bug_watch_ids))
        return query

    def bulkSetError(self, references, last_error_type=None):
        """See `IBugWatchSet`."""
        bug_watch_ids = set(get_bug_watch_ids(references))
        if len(bug_watch_ids) > 0:
            bug_watches_in_database = IStore(BugWatch).find(
                BugWatch, BugWatch.id.is_in(bug_watch_ids))
            bug_watches_in_database.set(
                lastchecked=UTC_NOW,
                last_error_type=last_error_type,
                next_check=None)

    def bulkAddActivity(self, references,
                        result=BugWatchActivityStatus.SYNC_SUCCEEDED,
                        oops_id=None):
        """See `IBugWatchSet`."""
        bulk.create(
            (BugWatchActivity.bug_watch_id, BugWatchActivity.result,
             BugWatchActivity.oops_id),
            [(bug_watch_id, result, ensure_unicode(oops_id))
             for bug_watch_id in set(get_bug_watch_ids(references))])


class BugWatchActivity(StormBase):
    """See `IBugWatchActivity`."""

    implements(IBugWatchActivity)

    __storm_table__ = 'BugWatchActivity'

    id = Int(primary=True)
    bug_watch_id = Int(name='bug_watch')
    bug_watch = Reference(bug_watch_id, BugWatch.id)
    activity_date = UtcDateTimeCol(notNull=True)
    result = EnumCol(enum=BugWatchActivityStatus, notNull=False)
    message = Unicode()
    oops_id = Unicode()
