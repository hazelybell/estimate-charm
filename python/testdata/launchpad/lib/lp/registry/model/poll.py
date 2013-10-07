# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type
__all__ = [
    'Poll',
    'PollOption',
    'PollOptionSet',
    'PollSet',
    'VoteCast',
    'Vote',
    'VoteSet',
    'VoteCastSet',
    ]

from datetime import datetime
import random

import pytz
from sqlobject import (
    AND,
    BoolCol,
    ForeignKey,
    IntCol,
    OR,
    SQLObjectNotFound,
    StringCol,
    )
from storm.store import Store
from zope.component import getUtility
from zope.interface import implements

from lp.registry.interfaces.person import validate_public_person
from lp.registry.interfaces.poll import (
    IPoll,
    IPollOption,
    IPollOptionSet,
    IPollSet,
    IVote,
    IVoteCast,
    IVoteCastSet,
    IVoteSet,
    OptionIsNotFromSimplePoll,
    PollAlgorithm,
    PollSecrecy,
    PollStatus,
    )
from lp.services.database.datetimecol import UtcDateTimeCol
from lp.services.database.enumcol import EnumCol
from lp.services.database.sqlbase import (
    SQLBase,
    sqlvalues,
    )


class Poll(SQLBase):
    """See IPoll."""

    implements(IPoll)
    _table = 'Poll'
    sortingColumns = ['title', 'id']
    _defaultOrder = sortingColumns

    team = ForeignKey(
        dbName='team', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    name = StringCol(dbName='name', notNull=True)

    title = StringCol(dbName='title', notNull=True, unique=True)

    dateopens = UtcDateTimeCol(dbName='dateopens', notNull=True)

    datecloses = UtcDateTimeCol(dbName='datecloses', notNull=True)

    proposition = StringCol(dbName='proposition',  notNull=True)

    type = EnumCol(dbName='type', enum=PollAlgorithm,
                   default=PollAlgorithm.SIMPLE)

    allowspoilt = BoolCol(dbName='allowspoilt', default=True, notNull=True)

    secrecy = EnumCol(dbName='secrecy', enum=PollSecrecy,
                      default=PollSecrecy.SECRET)

    def newOption(self, name, title, active=True):
        """See IPoll."""
        return getUtility(IPollOptionSet).new(self, name, title, active)

    def isOpen(self, when=None):
        """See IPoll."""
        if when is None:
            when = datetime.now(pytz.timezone('UTC'))
        return (self.datecloses >= when and self.dateopens <= when)

    @property
    def closesIn(self):
        """See IPoll."""
        return self.datecloses - datetime.now(pytz.timezone('UTC'))

    @property
    def opensIn(self):
        """See IPoll."""
        return self.dateopens - datetime.now(pytz.timezone('UTC'))

    def isClosed(self, when=None):
        """See IPoll."""
        if when is None:
            when = datetime.now(pytz.timezone('UTC'))
        return self.datecloses <= when

    def isNotYetOpened(self, when=None):
        """See IPoll."""
        if when is None:
            when = datetime.now(pytz.timezone('UTC'))
        return self.dateopens > when

    def getAllOptions(self):
        """See IPoll."""
        return getUtility(IPollOptionSet).selectByPoll(self)

    def getActiveOptions(self):
        """See IPoll."""
        return getUtility(IPollOptionSet).selectByPoll(self, only_active=True)

    def getVotesByPerson(self, person):
        """See IPoll."""
        return Vote.selectBy(person=person, poll=self)

    def personVoted(self, person):
        """See IPoll."""
        results = VoteCast.selectBy(person=person, poll=self)
        return bool(results.count())

    def removeOption(self, option, when=None):
        """See IPoll."""
        assert self.isNotYetOpened(when=when)
        if option.poll != self:
            raise ValueError(
                "Can't remove an option that doesn't belong to this poll")
        option.destroySelf()

    def getOptionByName(self, name):
        """See IPoll."""
        return PollOption.selectOneBy(poll=self, name=name)

    def _assertEverythingOkAndGetVoter(self, person, when=None):
        """Use assertions to Make sure all pre-conditions for a person to vote
        are met.

        Return the person if this is not a secret poll or None if it's a
        secret one.
        """
        assert self.isOpen(when=when), "This poll is not open"
        assert not self.personVoted(person), "Can't vote twice in the same poll"
        assert person.inTeam(self.team), (
            "Person %r is not a member of this poll's team." % person)

        # We only associate the option with the person if the poll is not a
        # SECRET one.
        if self.secrecy == PollSecrecy.SECRET:
            voter = None
        else:
            voter = person
        return voter

    def storeCondorcetVote(self, person, options, when=None):
        """See IPoll."""
        voter = self._assertEverythingOkAndGetVoter(person, when=when)
        assert self.type == PollAlgorithm.CONDORCET
        voteset = getUtility(IVoteSet)

        token = voteset.newToken()
        votes = []
        activeoptions = self.getActiveOptions()
        for option, preference in options.items():
            assert option.poll == self, (
                "The option %r doesn't belong to this poll" % option)
            assert option.active, "Option %r is not active" % option
            votes.append(voteset.new(self, option, preference, token, voter))

        # Store a vote with preference = None for each active option of this
        # poll that wasn't in the options argument.
        for option in activeoptions:
            if option not in options:
                votes.append(voteset.new(self, option, None, token, voter))

        getUtility(IVoteCastSet).new(self, person)
        return votes

    def storeSimpleVote(self, person, option, when=None):
        """See IPoll."""
        voter = self._assertEverythingOkAndGetVoter(person, when=when)
        assert self.type == PollAlgorithm.SIMPLE
        voteset = getUtility(IVoteSet)

        if option is None and not self.allowspoilt:
            raise ValueError("This poll doesn't allow spoilt votes.")
        elif option is not None:
            assert option.poll == self, (
                "The option %r doesn't belong to this poll" % option)
            assert option.active, "Option %r is not active" % option
        token = voteset.newToken()
        # This is a simple-style poll, so you can vote only on a single option
        # and this option's preference must be 1
        preference = 1
        vote = voteset.new(self, option, preference, token, voter)
        getUtility(IVoteCastSet).new(self, person)
        return vote

    def getTotalVotes(self):
        """See IPoll."""
        assert self.isClosed()
        return Vote.selectBy(poll=self).count()

    def getWinners(self):
        """See IPoll."""
        assert self.isClosed()
        # XXX: GuilhermeSalgado 2005-08-24:
        # For now, this method works only for SIMPLE-style polls. This is
        # not a problem as CONDORCET-style polls are disabled.
        assert self.type == PollAlgorithm.SIMPLE
        query = """
            SELECT option
            FROM Vote
            WHERE poll = %d AND option IS NOT NULL
            GROUP BY option
            HAVING COUNT(*) = (
                SELECT COUNT(*)
                FROM Vote
                WHERE poll = %d
                GROUP BY option
                ORDER BY COUNT(*) DESC LIMIT 1
                )
            """ % (self.id, self.id)
        results = Store.of(self).execute(query).get_all()
        if not results:
            return None
        return [PollOption.get(id) for (id,) in results]

    def getPairwiseMatrix(self):
        """See IPoll."""
        assert self.type == PollAlgorithm.CONDORCET
        options = list(self.getAllOptions())
        pairwise_matrix = []
        for option1 in options:
            pairwise_row = []
            for option2 in options:
                points_query = """
                    SELECT COUNT(*) FROM Vote as v1, Vote as v2 WHERE
                        v1.token = v2.token AND
                        v1.option = %s AND v2.option = %s AND
                        (
                         (
                          v1.preference IS NOT NULL AND
                          v2.preference IS NOT NULL AND
                          v1.preference < v2.preference
                         )
                          OR
                         (
                          v1.preference IS NOT NULL AND
                          v2.preference IS NULL
                         )
                        )
                    """ % sqlvalues(option1.id, option2.id)
                if option1 == option2:
                    pairwise_row.append(None)
                else:
                    points = Store.of(self).execute(points_query).get_one()[0]
                    pairwise_row.append(points)
            pairwise_matrix.append(pairwise_row)
        return pairwise_matrix


class PollSet:
    """See IPollSet."""

    implements(IPollSet)

    def new(self, team, name, title, proposition, dateopens, datecloses,
            secrecy, allowspoilt, poll_type=PollAlgorithm.SIMPLE):
        """See IPollSet."""
        return Poll(team=team, name=name, title=title,
                proposition=proposition, dateopens=dateopens,
                datecloses=datecloses, secrecy=secrecy,
                allowspoilt=allowspoilt, type=poll_type)

    def selectByTeam(self, team, status=PollStatus.ALL, orderBy=None, when=None):
        """See IPollSet."""
        if when is None:
            when = datetime.now(pytz.timezone('UTC'))

        if orderBy is None:
            orderBy = Poll.sortingColumns


        status = set(status)
        status_clauses = []
        if PollStatus.OPEN in status:
            status_clauses.append(AND(Poll.q.dateopens <= when,
                                    Poll.q.datecloses > when))
        if PollStatus.CLOSED in status:
            status_clauses.append(Poll.q.datecloses <= when)
        if PollStatus.NOT_YET_OPENED in status:
            status_clauses.append(Poll.q.dateopens > when)

        assert len(status_clauses) > 0, "No poll statuses were selected"

        results = Poll.select(AND(Poll.q.teamID == team.id,
                                  OR(*status_clauses)))

        return results.orderBy(orderBy)

    def getByTeamAndName(self, team, name, default=None):
        """See IPollSet."""
        query = AND(Poll.q.teamID == team.id, Poll.q.name == name)
        try:
            return Poll.selectOne(query)
        except SQLObjectNotFound:
            return default


class PollOption(SQLBase):
    """See IPollOption."""

    implements(IPollOption)
    _table = 'PollOption'
    _defaultOrder = ['title', 'id']

    poll = ForeignKey(dbName='poll', foreignKey='Poll', notNull=True)

    name = StringCol(notNull=True)

    title = StringCol(notNull=True)

    active = BoolCol(notNull=True, default=False)


class PollOptionSet:
    """See IPollOptionSet."""

    implements(IPollOptionSet)

    def new(self, poll, name, title, active=True):
        """See IPollOptionSet."""
        return PollOption(poll=poll, name=name, title=title, active=active)

    def selectByPoll(self, poll, only_active=False):
        """See IPollOptionSet."""
        query = PollOption.q.pollID == poll.id
        if only_active:
            query = AND(query, PollOption.q.active == True)
        return PollOption.select(query)

    def getByPollAndId(self, poll, option_id, default=None):
        """See IPollOptionSet."""
        query = AND(PollOption.q.pollID == poll.id,
                    PollOption.q.id == option_id)
        try:
            return PollOption.selectOne(query)
        except SQLObjectNotFound:
            return default


class VoteCast(SQLBase):
    """See IVoteCast."""

    implements(IVoteCast)
    _table = 'VoteCast'
    _defaultOrder = 'id'

    person = ForeignKey(
        dbName='person', foreignKey='Person',
        storm_validator=validate_public_person, notNull=True)

    poll = ForeignKey(dbName='poll', foreignKey='Poll', notNull=True)


class VoteCastSet:
    """See IVoteCastSet."""

    implements(IVoteCastSet)

    def new(self, poll, person):
        """See IVoteCastSet."""
        return VoteCast(poll=poll, person=person)


class Vote(SQLBase):
    """See IVote."""

    implements(IVote)
    _table = 'Vote'
    _defaultOrder = ['preference', 'id']

    person = ForeignKey(
        dbName='person', foreignKey='Person',
        storm_validator=validate_public_person)

    poll = ForeignKey(dbName='poll', foreignKey='Poll', notNull=True)

    option = ForeignKey(dbName='option', foreignKey='PollOption')

    preference = IntCol(dbName='preference')

    token = StringCol(dbName='token', notNull=True, unique=True)


class VoteSet:
    """See IVoteSet."""

    implements(IVoteSet)

    def newToken(self):
        """See IVoteSet."""
        chars = '23456789bcdfghjkmnpqrstvwxzBCDFGHJKLMNPQRSTVWXZ'
        length = 10
        token = ''.join([random.choice(chars) for c in range(length)])
        while self.getByToken(token):
            token = ''.join([random.choice(chars) for c in range(length)])
        return token

    def new(self, poll, option, preference, token, person):
        """See IVoteSet."""
        return Vote(poll=poll, option=option, preference=preference,
                    token=token, person=person)

    def getByToken(self, token):
        """See IVoteSet."""
        return Vote.selectBy(token=token)

    def getVotesByOption(self, option):
        """See IVoteSet."""
        if option.poll.type != PollAlgorithm.SIMPLE:
            raise OptionIsNotFromSimplePoll(
                '%r is not an option of a simple-style poll.' % option)
        return Vote.selectBy(option=option).count()

