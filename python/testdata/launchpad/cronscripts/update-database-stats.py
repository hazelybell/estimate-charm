#!/usr/bin/python -S
# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Populate the DatabaseTableStats and DatabaseCpuStats tables."""

__metaclass__ = type

import _pythonpath

from lp.registry.model.person import Person
from lp.services.database.interfaces import IMasterStore
from lp.services.scripts import db_options
from lp.services.scripts.base import LaunchpadCronScript


class UpdateDatabaseStats(LaunchpadCronScript):
    """Populate the DatabaseTableStats and DatabaseCpuStats tables."""

    def main(self):
        "Run UpdateDatabaseTableStats."""
        store = IMasterStore(Person)

        # The logic is in a stored procedure because we want to run
        # ps(1) on the database server rather than the host this script
        # is running on.
        self.logger.debug("Invoking update_database_stats()")
        store.execute("SELECT update_database_stats()", noresult=True)

        self.logger.debug("Committing")
        store.commit()

    def add_my_options(self):
        """Add standard database command line options."""
        db_options(self.parser)

if __name__ == '__main__':
    script = UpdateDatabaseStats(
        'update-database-stats', dbuser='database_stats_update')
    script.lock_and_run()
