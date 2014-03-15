# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Database constants."""

from storm.expr import SQL


UTC_NOW = SQL("CURRENT_TIMESTAMP AT TIME ZONE 'UTC'")

DEFAULT = SQL("DEFAULT")

# We can't use infinity, as psycopg doesn't know how to handle it. And
# neither does Python I guess.
#NEVER_EXPIRES = SQL("'infinity'::TIMESTAMP")

NEVER_EXPIRES = SQL("'3000-01-01'::TIMESTAMP WITHOUT TIME ZONE")

THIRTY_DAYS_AGO = SQL(
    "CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - interval '30 days'")

SEVEN_DAYS_AGO = SQL(
    "CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - interval '7 days'")

ONE_DAY_AGO = SQL(
    "CURRENT_TIMESTAMP AT TIME ZONE 'UTC' - interval '1 day'")
