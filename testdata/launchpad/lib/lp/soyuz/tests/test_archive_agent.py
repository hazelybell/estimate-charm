# Copyright 2010-2012 Canonical Ltd.  This software is licensed under the GNU
# Affero General Public License version 3 (see the file LICENSE).

"""Test Archive software center agent celebrity."""

from zope.component import getUtility

from lp.app.interfaces.launchpad import ILaunchpadCelebrities
from lp.testing import (
    celebrity_logged_in,
    person_logged_in,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestSoftwareCenterAgent(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def test_getArchiveSubscriptionURL(self):
        # The software center agent can get subscription URLs for any
        # archive that it's an owner of.
        owner = self.factory.makePerson()
        agent = getUtility(ILaunchpadCelebrities).software_center_agent
        ppa_owner = self.factory.makeTeam(members=[owner, agent])
        ppa = self.factory.makeArchive(owner=ppa_owner, private=True)
        person = self.factory.makePerson()
        with celebrity_logged_in('software_center_agent') as agent:
            sources = person.getArchiveSubscriptionURL(agent, ppa)
        with person_logged_in(ppa.owner):
            authtoken = ppa.getAuthToken(person).token
            url = ppa.archive_url.split('http://')[1]
        new_url = "http://%s:%s@%s" % (person.name, authtoken, url)
        self.assertEqual(sources, new_url)
