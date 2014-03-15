# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

from zope.security.management import endInteraction
from zope.security.proxy import removeSecurityProxy

from lp.testing import (
    admin_logged_in,
    launchpadlib_for,
    login,
    logout,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.pages import LaunchpadWebServiceCaller


class TestPersonEmailSecurity(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonEmailSecurity, self).setUp()
        self.target = self.factory.makePerson(name='target')
        self.email_one = self.factory.makeEmail(
                'test1@example.com', self.target)
        self.email_two = self.factory.makeEmail(
                'test2@example.com', self.target)

    def test_logged_in_can_access(self):
        # A logged in launchpadlib connection can see confirmed email
        # addresses.
        accessor = self.factory.makePerson()
        lp = launchpadlib_for("test", accessor.name)
        person = lp.people['target']
        emails = sorted(list(person.confirmed_email_addresses))
        self.assertNotEqual(
                sorted([self.email_one, self.email_two]),
                len(emails))

    def test_anonymous_cannot_access(self):
        # An anonymous launchpadlib connection cannot see email addresses.

        # Need to endInteraction() because launchpadlib_for() will
        # setup a new one.
        endInteraction()
        lp = launchpadlib_for('test', person=None, version='devel')
        person = lp.people['target']
        emails = list(person.confirmed_email_addresses)
        self.assertEqual([], emails)


class TestPersonRepresentation(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        login('guilherme.salgado@canonical.com ')
        self.person = self.factory.makePerson(
            name='test-person', displayname='Test Person')
        self.webservice = LaunchpadWebServiceCaller(
            'launchpad-library', 'salgado-change-anything')

    def test_GET_xhtml_representation(self):
        # Remove the security proxy because IPerson.name is protected.
        person_name = removeSecurityProxy(self.person).name
        response = self.webservice.get(
            '/~%s' % person_name, 'application/xhtml+xml')

        self.assertEqual(response.status, 200)

        rendered_comment = response.body
        self.assertEquals(
            rendered_comment,
            '<a href="/~test-person" class="sprite person">Test Person</a>')


class PersonSetWebServiceTests(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(PersonSetWebServiceTests, self).setUp()
        self.webservice = LaunchpadWebServiceCaller('test', None)
        logout()

    def assertReturnsPeople(self, expected_names, path):
        self.assertEqual(
            expected_names,
            [person['name'] for person in
             self.webservice.get(path).jsonBody()['entries']])

    def test_default_content(self):
        # /people lists the 50 people with the most karma, excluding
        # those with no karma at all.
        self.assertEqual(
            4, len(self.webservice.get('/people').jsonBody()['entries']))

    def test_find(self):
        # It's possible to find people by name.
        with admin_logged_in():
            person_name = self.factory.makePerson().name
        self.assertReturnsPeople(
            [person_name], '/people?ws.op=find&text=%s' % person_name)

    def test_findTeam(self):
        # The search can be restricted to teams.
        with admin_logged_in():
            person_name = self.factory.makePerson().name
            team_name = self.factory.makeTeam(
                name='%s-team' % person_name).name
        self.assertReturnsPeople(
            [team_name], '/people?ws.op=findTeam&text=%s' % person_name)

    def test_findPerson(self):
        # The search can be restricted to people.
        with admin_logged_in():
            person_name = self.factory.makePerson().name
            self.factory.makeTeam(name='%s-team' % person_name)
        self.assertReturnsPeople(
            [person_name], '/people?ws.op=findPerson&text=%s' % person_name)

    def test_find_by_date(self):
        # Creation date filtering is supported.
        self.assertReturnsPeople(
            [u'bac'],
            '/people?ws.op=findPerson&text='
            '&created_after=2008-06-27&created_before=2008-07-01')

    def test_getByEmail(self):
        # You can get a person by their email address.
        with admin_logged_in():
            person = self.factory.makePerson()
            person_name = person.name
            person_email = person.preferredemail.email
        self.assertEqual(
            person_name,
            self.webservice.get(
                '/people?ws.op=getByEmail&email=%s' % person_email
                ).jsonBody()['name'])

    def test_getByEmail_checks_format(self):
        # A malformed email address is rejected.
        e = self.assertRaises(
            ValueError,
            self.webservice.get(
                '/people?ws.op=getByEmail&email=foo@').jsonBody)
        # XXX wgrant bug=1088358: This escaping shouldn't be here; it's
        # not HTML.
        self.assertEqual("email: Invalid email &#x27;foo@&#x27;.", e[0])

    def test_getByOpenIDIdentifier(self):
        # You can get a person by their OpenID identifier URL.
        with admin_logged_in():
            person = self.factory.makePerson()
            person_name = person.name
            person_openid = person.account.openid_identifiers.one().identifier
        self.assertEqual(
            person_name,
            self.webservice.get(
                '/people?ws.op=getByOpenIDIdentifier&'
                'identifier=http://openid.launchpad.dev/%%2Bid/%s'
                % person_openid,
                api_version='devel').jsonBody()['name'])
