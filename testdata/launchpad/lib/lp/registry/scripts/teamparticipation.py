# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Script code relating to team participations."""

__metaclass__ = type
__all__ = [
    "check_teamparticipation_circular",
    "check_teamparticipation_consistency",
    "fetch_team_participation_info",
    "fix_teamparticipation_consistency",
    ]

from collections import (
    defaultdict,
    namedtuple,
    )
from functools import partial
from itertools import (
    chain,
    count,
    imap,
    izip,
    )

import transaction

from lp.registry.interfaces.teammembership import ACTIVE_STATES
from lp.registry.model.teammembership import TeamParticipation
from lp.services.database.interfaces import (
    IMasterStore,
    ISlaveStore,
    )
from lp.services.database.sqlbase import (
    quote,
    sqlvalues,
    )
from lp.services.scripts.base import LaunchpadScriptFailure


def check_teamparticipation_circular(log):
    """Check circular references.

    There can be no mutual participation between teams.
    """
    query = """
        SELECT tp.team, tp2.team
          FROM TeamParticipation AS tp,
               TeamParticipation AS tp2
         WHERE tp.team = tp2.person
           AND tp.person = tp2.team
           AND tp.id != tp2.id;
        """
    circular_references = list(ISlaveStore(TeamParticipation).execute(query))
    if len(circular_references) > 0:
        raise LaunchpadScriptFailure(
            "Circular references found: %s" % circular_references)


ConsistencyError = namedtuple(
    "ConsistencyError", ("type", "team", "people"))


def report_progress(log, interval, results, what):
    """Iterate through `results`, reporting on progress.

    :param log: A logger.
    :param interval: How many results to report progress about.
    :param results: An iterable of things.
    :param what: A string descriping what the results are.
    """
    for num, result in izip(count(1), results):
        if num % interval == 0:
            log.debug("%d %s", num, what)
        yield result
    log.debug("%d %s", num, what)


def execute_long_query(store, log, interval, query):
    """Execute the given query, reporting as results are fetched.

    The query is logged, then every `interval` rows a message is logged with
    the total number of rows fetched thus far.
    """
    log.debug(query)
    results = store.execute(query)
    # Hackish; the default is 10 which seems fairly low.
    results._raw_cursor.arraysize = interval
    return report_progress(log, interval, results, "rows")


def fetch_team_participation_info(log):
    """Fetch people, teams, memberships and participations."""
    slurp = partial(
        execute_long_query, ISlaveStore(TeamParticipation), log, 10000)

    people = dict(
        slurp(
            "SELECT id, name FROM Person"
            " WHERE teamowner IS NULL"
            "   AND merged IS NULL"))
    teams = dict(
        slurp(
            "SELECT id, name FROM Person"
            " WHERE teamowner IS NOT NULL"
            "   AND merged IS NULL"))
    team_memberships = defaultdict(set)
    results = slurp(
        "SELECT team, person FROM TeamMembership"
        " WHERE status in %s" % quote(ACTIVE_STATES))
    for (team, person) in results:
        team_memberships[team].add(person)
    team_participations = defaultdict(set)
    results = slurp(
        "SELECT team, person FROM TeamParticipation")
    for (team, person) in results:
        team_participations[team].add(person)

    # Don't hold any locks.
    transaction.commit()

    return people, teams, team_memberships, team_participations


def check_teamparticipation_consistency(log, info):
    """Check for missing or spurious participations.

    For example, participations for people who are not members, or missing
    participations for people who are members.
    """
    people, teams, team_memberships, team_participations = info

    # set.intersection() with a dict is slow.
    people_set = frozenset(people)
    teams_set = frozenset(teams)

    def get_participants(team):
        """Recurse through membership records to get participants."""
        member_people = team_memberships[team].intersection(people_set)
        member_people.add(team)  # Teams always participate in themselves.
        member_teams = team_memberships[team].intersection(teams_set)
        return member_people.union(
            chain.from_iterable(imap(get_participants, member_teams)))

    def check_participants(person, expected, observed):
        spurious = observed - expected
        missing = expected - observed
        if len(spurious) > 0:
            yield ConsistencyError("spurious", person, sorted(spurious))
        if len(missing) > 0:
            yield ConsistencyError("missing", person, sorted(missing))

    errors = []

    log.debug("Checking consistency of %d people", len(people))
    for person in report_progress(log, 50000, people, "people"):
        participants_expected = set((person,))
        participants_observed = team_participations[person]
        errors.extend(
            check_participants(
                person, participants_expected, participants_observed))

    log.debug("Checking consistency of %d teams", len(teams))
    for team in report_progress(log, 1000, teams, "teams"):
        participants_expected = get_participants(team)
        participants_observed = team_participations[team]
        errors.extend(
            check_participants(
                team, participants_expected, participants_observed))

    def get_repr(id):
        if id in people:
            name = people[id]
        elif id in teams:
            name = teams[id]
        else:
            name = "<unknown>"
        return "%s (%d)" % (name, id)

    for error in errors:
        people_repr = ", ".join(imap(get_repr, error.people))
        log.warn(
            "%s: %s TeamParticipation entries for %s.",
            get_repr(error.team), error.type, people_repr)

    return errors


def fix_teamparticipation_consistency(log, errors):
    """Fix missing or spurious participations.

    This function does not consult `TeamMembership` at all, so it /may/
    introduce another participation inconsistency if the records that are the
    subject of the given errors have been modified since being checked.

    :param errors: An iterable of `ConsistencyError` tuples.
    """
    sql_missing = (
        """
        INSERT INTO TeamParticipation (team, person)
        SELECT %(team)s, %(person)s
        EXCEPT
        SELECT team, person
          FROM TeamParticipation
         WHERE team = %(team)s
           AND person = %(person)s
        """)
    sql_spurious = (
        """
        DELETE FROM TeamParticipation
         WHERE team = %(team)s
           AND person IN %(people)s
        """)
    store = IMasterStore(TeamParticipation)
    for error in errors:
        if error.type == "missing":
            for person in error.people:
                statement = sql_missing % sqlvalues(
                    team=error.team, person=person)
                log.debug(statement)
                store.execute(statement)
                transaction.commit()
        elif error.type == "spurious":
            statement = sql_spurious % sqlvalues(
                team=error.team, people=error.people)
            log.debug(statement)
            store.execute(statement)
            transaction.commit()
        else:
            log.warn("Unrecognized error: %r", error)
