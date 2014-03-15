# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test pgsession.py."""

__metaclass__ = type

from unittest import TestCase

from zope.publisher.browser import TestRequest
from zope.security.management import (
    endInteraction,
    newInteraction,
    )
from zope.session.interfaces import (
    ISessionData,
    ISessionDataContainer,
    )

from lp.services.webapp.pgsession import (
    PGSessionData,
    PGSessionDataContainer,
    )
from lp.testing.layers import (
    LaunchpadFunctionalLayer,
    LaunchpadLayer,
    )


class PicklingTest:
    '''This class is used to ensure we can store arbitrary pickles'''
    def __init__(self, value):
        self.value = value

    def __eq__(self, obj):
        return self.value == obj.value


class TestPgSession(TestCase):
    dbuser = 'session'
    layer = LaunchpadFunctionalLayer

    def setUp(self):
        self.sdc = PGSessionDataContainer()
        LaunchpadLayer.resetSessionDb()
        self.request = TestRequest()
        newInteraction(self.request)

    def tearDown(self):
        endInteraction()
        del self.request
        del self.sdc

    def test_sdc_basics(self):
        # Make sure we have the correct class and it provides the required
        # interface.
        self.failUnless(isinstance(self.sdc, PGSessionDataContainer))
        self.failUnless(ISessionDataContainer.providedBy(self.sdc))

        client_id = 'Client Id'

        # __getitem__ does not raise a keyerror for an unknown client id.
        # This is not correct, but needed to work around a design flaw in
        # the session machinery.
        self.assertNotEqual(None, self.sdc['Unknown client id'])

        # __setitem__ calls are ignored.
        self.sdc[client_id] = 'ignored'

        # Once __setitem__ is called, we can access the SessionData
        session_data = self.sdc[client_id]
        self.failUnless(isinstance(session_data, PGSessionData))
        self.failUnless(ISessionData.providedBy(session_data))

    def test_storage(self):
        client_id1 = 'Client Id #1'
        client_id2 = 'Client Id #2'
        product_id1 = 'Product Id #1'
        product_id2 = 'Product Id #2'

        # Create some SessionPkgData storages
        self.sdc[client_id1] = 'whatever'
        self.sdc[client_id2] = 'whatever'
        session1a = self.sdc[client_id1][product_id1]

        # Set some values in the session
        session1a['key1'] = 'value1'
        session1a['key2'] = PicklingTest('value2')
        self.failUnlessEqual(session1a['key1'], 'value1')
        self.failUnlessEqual(session1a['key2'].value, 'value2')

        # Make sure no leakage between sessions
        session1b = self.sdc[client_id1][product_id2]
        session2a = self.sdc[client_id2][product_id1]
        self.assertRaises(KeyError, session1b.__getitem__, 'key')
        self.assertRaises(KeyError, session2a.__getitem__, 'key')

        # Make sure data can be retrieved from the db
        session1a_dupe = self.sdc[client_id1][product_id1]

        # This new session should not be the same object
        self.failIf(session1a is session1a_dupe)

        # But it should contain copies of the same data, unpickled from the
        # database
        self.failUnlessEqual(session1a['key1'], session1a_dupe['key1'])
        self.failUnlessEqual(session1a['key2'], session1a_dupe['key2'])

        # They must be copies - not the same object
        self.failIf(session1a['key2'] is session1a_dupe['key2'])

        # Ensure the keys method works as it is suppsed to
        self.failUnlessEqual(sorted(session1a.keys()), ['key1', 'key2'])
        self.failUnlessEqual(session2a.keys(), [])

        # Ensure we can delete and alter things from the session
        del session1a['key1']
        session1a['key2'] = 'new value2'
        self.assertRaises(KeyError, session1a.__getitem__, 'key1')
        self.failUnlessEqual(session1a['key2'], 'new value2')
        self.failUnlessEqual(session1a.keys(), ['key2'])

        # Note that deleting will not raise a KeyError
        del session1a['key1']
        del session1a['key1']
        del session1a['whatever']

        # And ensure that these changes are persistent
        session1a_dupe = self.sdc[client_id1][product_id1]
        self.assertRaises(KeyError, session1a_dupe.__getitem__, 'key1')
        self.failUnlessEqual(session1a_dupe['key2'], 'new value2')
        self.failUnlessEqual(session1a_dupe.keys(), ['key2'])

    def test_session_only_stored_when_changed(self):
        # A record of the session is only stored in the database when
        # some data is stored against the session.
        client_id = 'Client Id #1'
        product_id = 'Product Id'

        session = self.sdc[client_id]
        pkgdata = session[product_id]
        self.assertRaises(KeyError, pkgdata.__getitem__, 'key')

        # Test results depend on the session being empty. This is
        # taken care of by setUp().
        store = self.sdc.store
        result = store.execute("SELECT COUNT(*) FROM SessionData")
        self.assertEqual(result.get_one()[0], 0)

        # The session cookie is also not yet set in the response.
        self.assertEqual(self.request.response.getCookie('launchpad_tests'),
                         None)

        # Now try storing some data in the session, which will result
        # in it being stored in the database.
        pkgdata['key'] = 'value'
        result = store.execute(
            "SELECT client_id FROM SessionData ORDER BY client_id")
        client_ids = [row[0] for row in result]
        self.assertEquals(client_ids, [client_id])

        # The session cookie also is now set, via the same "trigger".
        self.assertNotEqual(
            self.request.response.getCookie('launchpad_tests'), None)

        # also see the page test xx-no-anonymous-session-cookies for tests of
        # the cookie behavior.
