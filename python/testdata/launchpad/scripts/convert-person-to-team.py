#!/usr/bin/python -S
#
# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Script to convert a person into a team.

Only people whose account_status is NOACCOUNT can be turned into teams.
"""


import _pythonpath

from zope.component import getUtility

from lp.registry.interfaces.person import IPersonSet
from lp.services.identity.interfaces.account import AccountStatus
from lp.services.scripts.base import (
    LaunchpadScript,
    LaunchpadScriptFailure,
    )


class ConvertPersonToTeamScript(LaunchpadScript):

    usage = '%prog <person-to-convert> <team-owner>'

    def main(self):
        if len(self.args) != 2:
            raise LaunchpadScriptFailure(
                "You must specify the name of the person to be converted "
                "and the person/team who should be its teamowner.")

        person_set = getUtility(IPersonSet)
        person_name, owner_name = self.args
        person = person_set.getByName(person_name)
        if person is None:
            raise LaunchpadScriptFailure(
                "There's no person named '%s'." % person_name)
        if person.account_status != AccountStatus.NOACCOUNT:
            raise LaunchpadScriptFailure(
                "Only people which have no account can be turned into teams.")
        owner = person_set.getByName(owner_name)
        if owner is None:
            raise LaunchpadScriptFailure(
                "There's no person named '%s'." % owner_name)

        person.convertToTeam(owner)
        self.txn.commit()


if __name__ == '__main__':
    script = ConvertPersonToTeamScript('convert-person-to-team')
    script.lock_and_run()
