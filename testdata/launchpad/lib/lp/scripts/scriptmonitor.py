# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Monitor whether scripts have run between specified time periods."""

__metaclass__ = type
__all__ = ['check_script']

from lp.services.database.sqlbase import sqlvalues


def check_script(con, log, hostname, scriptname,
                 completed_from, completed_to):
    """Check whether a script ran on a specific host within stated timeframe.

    Return nothing on success, or log an error message and return error
    message.
    """
    cur = con.cursor()
    cur.execute("""
        SELECT id
        FROM ScriptActivity
        WHERE hostname=%s AND name=%s
            AND date_completed BETWEEN %s AND %s
        LIMIT 1
        """ % sqlvalues(hostname, scriptname, completed_from, completed_to))
    try:
        cur.fetchone()[0]
        return None
    except TypeError:
        output = ("The script '%s' didn't run on '%s' between %s and %s"
                % (scriptname, hostname, completed_from, completed_to))
        cur.execute("""
            SELECT MAX(date_completed)
            FROM ScriptActivity
            WHERE hostname=%s AND name=%s
        """ % sqlvalues(hostname, scriptname))
        date_last_seen = cur.fetchone()[0]
        if date_last_seen is not None:
            output += " (last seen %s)" % (date_last_seen,)
        log.fatal(output)
        return output
