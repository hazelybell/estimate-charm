#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Import a mailing list (well, parts of it)."""

# XXX BarryWarsaw 2008-11-24
# Things this script does NOT currently do.
#
# - Import archives.

__metaclass__ = type
__all__ = [
    'MailingListImport',
    ]


import _pythonpath

import logging
import sys
import textwrap

from lp.registry.scripts.mlistimport import Importer
from lp.services.config import config
from lp.services.scripts.base import LaunchpadScript


class MailingListImport(LaunchpadScript):
    """
    %prog [options] team_name

    Import various mailing list artifacts into a Launchpad mailing
    list.  This script allows you to import e.g. the membership list
    from an external mailing list into a Launchpad hosted mailng list.
    """

    loglevel = logging.INFO
    description = 'Import data into a Launchpad mailing list.'

    def __init__(self, name, dbuser=None):
        self.usage = textwrap.dedent(self.__doc__)
        super(MailingListImport, self).__init__(name, dbuser)

    def add_my_options(self):
        """See `LaunchpadScript`."""
        self.parser.add_option('-f', '--filename', default='-', help=(
            'The file name containing the addresses to import, one '
            "per line.  If '-' is used or this option is not given, "
            'then addresses are read from standard input.'))
        self.parser.add_option('--notifications',
                               default=False, action='store_true',
                               help=(
            'Enable team-join notification sending to team admins.'))

    def main(self):
        """See `LaunchpadScript`."""
        team_name = None
        if len(self.args) == 0:
            self.parser.error('Missing team name')
        elif len(self.args) > 1:
            self.parser.error('Too many arguments')
        else:
            team_name = self.args[0]

        importer = Importer(team_name, self.logger)

        # Suppress sending emails based on the (absence) of the --notification
        # switch.  Notifications are disabled by default because they can
        # cause huge amounts to be sent to the team owner.
        send_email_config = """
            [immediate_mail]
            send_email: %s
            """ % self.options.notifications
        config.push('send_email_config', send_email_config)

        if self.options.filename == '-':
            # Read all the addresses from standard input, parse them
            # here, and use the direct interface to the importer.
            addresses = []
            while True:
                line = sys.stdin.readline()
                if line == '':
                    break
                addresses.append(line[:-1])
            importer.importAddresses(addresses)
        else:
            importer.importFromFile(self.options.filename)

        # All done; commit the database changes.
        self.txn.commit()
        return 0


if __name__ == '__main__':
    script = MailingListImport('scripts.mlist-import', 'mlist-import')
    status = script.lock_and_run()
    sys.exit(status)
