# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'BugSubscriptionFilter',
    'BugSubscriptionFilterInformationType',
    'BugSubscriptionFilterImportance',
    'BugSubscriptionFilterMute',
    'BugSubscriptionFilterStatus',
    'BugSubscriptionFilterTag',
    ]

import httplib
from itertools import chain

from lazr.restful.declarations import error_status
import pytz
from storm.expr import (
    Exists,
    Not,
    Select,
    SQL,
    )
from storm.properties import (
    Bool,
    DateTime,
    Int,
    Unicode,
    )
from storm.references import Reference
from storm.store import Store
from zope.interface import implements

from lp.app.enums import InformationType
from lp.bugs.enums import BugNotificationLevel
from lp.bugs.interfaces.bugsubscriptionfilter import (
    IBugSubscriptionFilter,
    IBugSubscriptionFilterMute,
    )
from lp.bugs.interfaces.bugtask import (
    BugTaskImportance,
    BugTaskStatus,
    )
from lp.registry.interfaces.person import validate_person
from lp.services import searchbuilder
from lp.services.database.constants import UTC_NOW
from lp.services.database.enumcol import DBEnum
from lp.services.database.interfaces import IStore
from lp.services.database.sqlbase import convert_storm_clause_to_string
from lp.services.database.stormbase import StormBase


@error_status(httplib.BAD_REQUEST)
class MuteNotAllowed(Exception):
    """Raised when someone tries to mute a filter that can't be muted."""


class BugSubscriptionFilter(StormBase):
    """A filter to specialize a *structural* subscription."""

    implements(IBugSubscriptionFilter)

    __storm_table__ = "BugSubscriptionFilter"

    id = Int(primary=True)

    structural_subscription_id = Int(
        "structuralsubscription", allow_none=False)
    structural_subscription = Reference(
        structural_subscription_id, "StructuralSubscription.id")

    bug_notification_level = DBEnum(
        enum=BugNotificationLevel,
        default=BugNotificationLevel.COMMENTS,
        allow_none=False)
    find_all_tags = Bool(allow_none=False, default=False)
    include_any_tags = Bool(allow_none=False, default=False)
    exclude_any_tags = Bool(allow_none=False, default=False)

    other_parameters = Unicode()

    description = Unicode('description')

    def _get_collection(self, cls, attribute):
        kind = getattr(cls, attribute)
        return frozenset(
            IStore(cls).find(cls, cls.filter == self).values(kind))

    def _set_collection(self, cls, enum, attribute, current_set, desired_set):
        desired_set = frozenset(desired_set)
        if desired_set == frozenset(enum.items):
            # Setting all is the same as setting none, and setting none is
            # cheaper for reading and storage.
            desired_set = frozenset()
        # Add missing.
        store = IStore(cls)
        for kind in desired_set.difference(current_set):
            bsf = cls()
            bsf.filter = self
            setattr(bsf, attribute, kind)
            store.add(bsf)
        # Remove unused.
        kind = getattr(cls, attribute)
        store.find(
            cls, cls.filter == self, kind.is_in(
                current_set.difference(desired_set))).remove()

    def _get_statuses(self):
        return self._get_collection(BugSubscriptionFilterStatus, 'status')

    def _set_statuses(self, statuses):
        self._set_collection(
            BugSubscriptionFilterStatus, BugTaskStatus, 'status',
            self.statuses, statuses)

    statuses = property(
        _get_statuses, _set_statuses, doc=(
            "A frozenset of statuses filtered on."))

    def _get_importances(self):
        return self._get_collection(
            BugSubscriptionFilterImportance, 'importance')

    def _set_importances(self, importances):
        self._set_collection(
            BugSubscriptionFilterImportance, BugTaskImportance, 'importance',
            self.importances, importances)

    importances = property(
        _get_importances, _set_importances, doc=(
            "A frozenset of importances filtered on."))

    def _get_tags(self):
        """Return a frozenset of tags to filter on."""
        wildcards = []
        if self.include_any_tags:
            wildcards.append(u"*")
        if self.exclude_any_tags:
            wildcards.append(u"-*")
        tags = (
            tag_filter.qualified_tag
            for tag_filter in IStore(BugSubscriptionFilterTag).find(
                BugSubscriptionFilterTag,
                BugSubscriptionFilterTag.filter == self))
        return frozenset(chain(wildcards, tags))

    def _set_tags(self, tags):
        """Update the tags to filter on.

        The tags can be qualified with a leading hyphen, and can be bundled in
        any iterable.

        If they are passed within a `searchbuilder.any` or `searchbuilder.all`
        object, the `find_all_tags` attribute will be updated to match.

        Wildcard tags - `*` and `-*` - can be given too, and will update
        `include_any_tags` and `exclude_any_tags`.
        """
        # Deal with searchbuilder terms.
        if isinstance(tags, searchbuilder.all):
            self.find_all_tags = True
            tags = frozenset(tags.query_values)
        elif isinstance(tags, searchbuilder.any):
            self.find_all_tags = False
            tags = frozenset(tags.query_values)
        else:
            # Leave find_all_tags unchanged.
            tags = frozenset(tags)
        wildcards = frozenset((u"*", u"-*")).intersection(tags)
        # Set wildcards.
        self.include_any_tags = "*" in wildcards
        self.exclude_any_tags = "-*" in wildcards
        # Deal with other tags.
        tags = tags - wildcards
        store = IStore(BugSubscriptionFilterTag)
        current_tag_filters = dict(
            (tag_filter.qualified_tag, tag_filter)
            for tag_filter in store.find(
                BugSubscriptionFilterTag,
                BugSubscriptionFilterTag.filter == self))
        # Remove unused tags.
        for tag in set(current_tag_filters).difference(tags):
            tag_filter = current_tag_filters.pop(tag)
            store.remove(tag_filter)
        # Add additional tags.
        for tag in tags.difference(current_tag_filters):
            tag_filter = BugSubscriptionFilterTag()
            tag_filter.filter = self
            tag_filter.include = not tag.startswith("-")
            tag_filter.tag = tag.lstrip("-")
            store.add(tag_filter)

    tags = property(
        _get_tags, _set_tags, doc=(
            "A frozenset of tags filtered on."))

    def _get_information_types(self):
        return self._get_collection(
            BugSubscriptionFilterInformationType, 'information_type')

    def _set_information_types(self, information_types):
        self._set_collection(
            BugSubscriptionFilterInformationType, InformationType,
            'information_type', self.information_types, information_types)

    information_types = property(
        _get_information_types, _set_information_types, doc=(
            "A frozenset of information_types filtered on."))

    def delete(self):
        """See `IBugSubscriptionFilter`."""
        BugSubscriptionFilter.deleteMultiple([self.id])
        Store.of(self).remove(self)

    @classmethod
    def deleteMultiple(cls, ids):
        from lp.bugs.model.structuralsubscription import StructuralSubscription
        store = IStore(BugSubscriptionFilter)
        structsub_ids = list(
            store.find(
                BugSubscriptionFilter.structural_subscription_id,
                BugSubscriptionFilter.id.is_in(ids)))
        kinds = [
            BugSubscriptionFilterImportance, BugSubscriptionFilterStatus,
            BugSubscriptionFilterTag, BugSubscriptionFilterInformationType]
        for kind in kinds:
            store.find(kind, kind.filter_id.is_in(ids)).remove()
        store.find(
            BugSubscriptionFilter,
            BugSubscriptionFilter.id.is_in(ids)).remove()
        # Now delete any structural subscriptions that have no filters.
        # Take out a SHARE lock on the filters that we use as evidence
        # for keeping structsubs, to ensure that they haven't been
        # deleted under us.
        filter_expr = Select(
            1, tables=[BugSubscriptionFilter],
            where=(
                BugSubscriptionFilter.structural_subscription_id
                    == StructuralSubscription.id))
        locked_filter_expr = SQL(
            convert_storm_clause_to_string(filter_expr) + ' FOR SHARE')
        store.find(
            StructuralSubscription,
            StructuralSubscription.id.is_in(structsub_ids),
            Not(Exists(locked_filter_expr))).remove()

    def isMuteAllowed(self, person):
        """See `IBugSubscriptionFilter`."""
        subscriber = self.structural_subscription.subscriber
        # The person can mute the Subscription if the subscription is via a
        # team of which they are a member and the team doesn't have a contact
        # address (because if the team does, then the mute would be
        # ineffectual).
        return (
            subscriber.is_team and
            person.inTeam(subscriber) and
            subscriber.preferredemail is None)

    def muted(self, person):
        store = Store.of(self)
        existing_mutes = store.find(
            BugSubscriptionFilterMute,
            BugSubscriptionFilterMute.filter_id == self.id,
            BugSubscriptionFilterMute.person_id == person.id)
        if not existing_mutes.is_empty():
            return existing_mutes.one().date_created

    def mute(self, person):
        """See `IBugSubscriptionFilter`."""
        subscriber = self.structural_subscription.subscriber
        if subscriber.is_team and subscriber.preferredemail:
            raise MuteNotAllowed(
                "This subscription cannot be muted because team %s has a "
                "contact address." % subscriber.name)
        if not self.isMuteAllowed(person):
            raise MuteNotAllowed(
                "This subscription cannot be muted for %s" % person.name)

        store = Store.of(self)
        existing_mutes = store.find(
            BugSubscriptionFilterMute,
            BugSubscriptionFilterMute.filter_id == self.id,
            BugSubscriptionFilterMute.person_id == person.id)
        if existing_mutes.is_empty():
            mute = BugSubscriptionFilterMute()
            mute.person = person
            mute.filter = self.id
            store.add(mute)

    def unmute(self, person):
        """See `IBugSubscriptionFilter`."""
        store = Store.of(self)
        existing_mutes = store.find(
            BugSubscriptionFilterMute,
            BugSubscriptionFilterMute.filter_id == self.id,
            BugSubscriptionFilterMute.person_id == person.id)
        existing_mutes.remove()


class BugSubscriptionFilterMute(StormBase):
    """Bug subscription filters a person has decided to block emails from."""

    implements(IBugSubscriptionFilterMute)

    __storm_table__ = "BugSubscriptionFilterMute"

    def __init__(self, person=None, filter=None):
        if person is not None:
            self.person = person
        if filter is not None:
            self.filter = filter.id

    person_id = Int("person", allow_none=False, validator=validate_person)
    person = Reference(person_id, "Person.id")

    filter_id = Int("filter", allow_none=False)
    filter = Reference(filter_id, "BugSubscriptionFilter.id")

    __storm_primary__ = 'person_id', 'filter_id'

    date_created = DateTime(
        "date_created", allow_none=False, default=UTC_NOW,
        tzinfo=pytz.UTC)


class BugSubscriptionFilterStatus(StormBase):
    """Statuses to filter."""

    __storm_table__ = "BugSubscriptionFilterStatus"
    __storm_primary__ = ('filter_id', 'status')

    filter_id = Int("filter", allow_none=False)
    filter = Reference(filter_id, "BugSubscriptionFilter.id")

    status = DBEnum(enum=BugTaskStatus, allow_none=False)


class BugSubscriptionFilterImportance(StormBase):
    """Importances to filter."""

    __storm_table__ = "BugSubscriptionFilterImportance"
    __storm_primary__ = ('filter_id', 'importance')

    filter_id = Int("filter", allow_none=False)
    filter = Reference(filter_id, "BugSubscriptionFilter.id")

    importance = DBEnum(enum=BugTaskImportance, allow_none=False)


class BugSubscriptionFilterTag(StormBase):
    """Tags to filter."""

    __storm_table__ = "BugSubscriptionFilterTag"

    id = Int(primary=True)

    filter_id = Int("filter", allow_none=False)
    filter = Reference(filter_id, "BugSubscriptionFilter.id")

    include = Bool(allow_none=False)
    tag = Unicode(allow_none=False)

    @property
    def qualified_tag(self):
        """The tag qualified with a hyphen if it is to be omitted."""
        if self.include:
            return self.tag
        else:
            return u"-" + self.tag


class BugSubscriptionFilterInformationType(StormBase):
    """Information types to filter."""

    __storm_table__ = "BugSubscriptionFilterInformationType"
    __storm_primary__ = ('filter_id', 'information_type')

    filter_id = Int("filter", allow_none=False)
    filter = Reference(filter_id, "BugSubscriptionFilter.id")

    information_type = DBEnum(enum=InformationType, allow_none=False)
