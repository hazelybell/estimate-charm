#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Remove personal details of a user from the database, leaving a stub."""

__metaclass__ = type
__all__ = []

import _pythonpath

from optparse import OptionParser
import sys

from lp.answers.enums import QuestionStatus
from lp.registry.interfaces.person import PersonCreationRationale
from lp.services.database.sqlbase import (
    connect,
    sqlvalues,
    )
from lp.services.scripts import (
    db_options,
    logger,
    logger_options,
    )


def close_account(con, log, username):
    """Close a person's account.

    Return True on success, or log an error message and return False
    """
    cur = con.cursor()
    cur.execute("""
        SELECT Person.id, Person.account, name, teamowner
        FROM Person
        LEFT OUTER JOIN EmailAddress ON Person.id = EmailAddress.person
        WHERE name = %(username)s OR lower(email) = lower(%(username)s)
        """, vars())
    try:
        person_id, account_id, username, teamowner = cur.fetchone()
    except TypeError:
        log.fatal("User %s does not exist" % username)
        return False

    # We don't do teams
    if teamowner is not None:
        log.fatal("%s is a team" % username)
        return False

    log.info("Closing %s's account" % username)

    def table_notification(table):
        log.debug("Handling the %s table" % table)

    # All names starting with 'removed' are blacklisted, so this will always
    # succeed.
    new_name = 'removed%d' % person_id

    # Remove the EmailAddress. This is the most important step, as
    # people requesting account removal seem to primarily be interested
    # in ensuring we no longer store this information.
    table_notification('EmailAddress')
    cur.execute("""
        DELETE FROM EmailAddress WHERE person = %s
        """ % sqlvalues(person_id))

    # Clean out personal details from the Person table
    table_notification('Person')
    unknown_rationale = PersonCreationRationale.UNKNOWN.value
    cur.execute("""
        UPDATE Person
        SET
            displayname = 'Removed by request',
            name=%(new_name)s,
            language = NULL,
            account = NULL,
            homepage_content = NULL,
            icon = NULL,
            mugshot = NULL,
            hide_email_addresses = TRUE,
            registrant = NULL,
            logo = NULL,
            creation_rationale = %(unknown_rationale)s,
            creation_comment = NULL
        WHERE id = %(person_id)s
        """, vars())

    # Remove the Account. We don't set the status to deactivated,
    # as this script is used to satisfy people who insist on us removing
    # all their personal details from our systems. This includes any
    # identification tokens like email addresses or openid identifiers.
    # So the Account record would be unusable, and contain no useful
    # information.
    table_notification('Account')
    if account_id is not None:
        cur.execute("""
            DELETE FROM Account WHERE id = %s
            """ % sqlvalues(account_id))

    # Reassign their bugs
    table_notification('BugTask')
    cur.execute("""
        UPDATE BugTask SET assignee = NULL WHERE assignee = %(person_id)s
        """, vars())

    # Reassign questions assigned to the user, and close all their questions
    # since nobody else can
    table_notification('Question')
    cur.execute("""
        UPDATE Question SET assignee=NULL WHERE assignee=%(person_id)s
        """, vars())
    closed_question_status = QuestionStatus.SOLVED.value
    cur.execute("""
        UPDATE Question
        SET status=%(closed_question_status)s, whiteboard=
            'Closed by Launchpad due to owner requesting account removal'
        WHERE owner=%(person_id)s
        """, vars())

    # Remove rows from tables in simple cases in the given order
    removals = [
        # Trash their email addresses. Unsociable privacy nut jobs who request
        # account removal would be pissed if they reregistered with their old
        # email address and this resurrected their deleted account, as the
        # email address is probably the piece of data we store that they where
        # most concerned with being removed from our systems.
        ('EmailAddress', 'person'),

        # Trash their codes of conduct and GPG keys
        ('SignedCodeOfConduct', 'owner'),
        ('GpgKey', 'owner'),

        # Subscriptions
        ('BranchSubscription', 'person'),
        ('BugSubscription', 'person'),
        ('QuestionSubscription', 'person'),
        ('SpecificationSubscription', 'person'),

        # Personal stuff, freeing up the namespace for others who want to play
        # or just to remove any fingerprints identifying the user.
        ('IrcId', 'person'),
        ('JabberId', 'person'),
        ('WikiName', 'person'),
        ('PersonLanguage', 'person'),
        ('PersonLocation', 'person'),
        ('SshKey', 'person'),

        # Karma
        ('Karma', 'person'),
        ('KarmaCache', 'person'),
        ('KarmaTotalCache', 'person'),

        # Team memberships
        ('TeamMembership', 'person'),
        ('TeamParticipation', 'person'),

        # Contacts
        ('AnswerContact', 'person'),

        # Pending items in queues
        ('POExportRequest', 'person'),
        ]
    for table, person_id_column in removals:
        table_notification(table)
        cur.execute("""
                DELETE FROM %(table)s WHERE %(person_id_column)s=%(person_id)d
                """ % vars())

    # Trash Sprint Attendance records in the future.
    table_notification('SprintAttendance')
    cur.execute("""
        DELETE FROM SprintAttendance
        USING Sprint
        WHERE Sprint.id = SprintAttendance.sprint
            AND attendee=%(person_id)s
            AND Sprint.time_starts > CURRENT_TIMESTAMP AT TIME ZONE 'UTC'
        """, vars())

    return True


def main():
    parser = OptionParser(
            '%prog [options] (username|email) [...]'
            )
    db_options(parser)
    logger_options(parser)

    (options, args) = parser.parse_args()

    if len(args) == 0:
        parser.error("Must specify username (Person.name)")

    log = logger(options)

    con = None
    try:
        log.debug("Connecting to database")
        con = connect()
        for username in args:
            if not close_account(con, log, username):
                log.debug("Rolling back")
                con.rollback()
                return 1
        log.debug("Committing changes")
        con.commit()
        return 0
    except:
        log.exception("Unhandled exception")
        log.debug("Rolling back")
        if con is not None:
            con.rollback()
        return 1


if __name__ == '__main__':
    sys.exit(main())
