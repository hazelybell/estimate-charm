# Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for PersonSet."""

__metaclass__ = type


from testtools.matchers import LessThan
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.code.tests.helpers import remove_all_sample_data_branches
from lp.registry.errors import (
    InvalidName,
    NameAlreadyTaken,
    )
from lp.registry.interfaces.nameblacklist import INameBlacklistSet
from lp.registry.interfaces.person import (
    IPerson,
    IPersonSet,
    PersonCreationRationale,
    TeamEmailAddressError,
    )
from lp.registry.model.codeofconduct import SignedCodeOfConduct
from lp.registry.model.person import Person
from lp.services.database.interfaces import (
    IMasterStore,
    IStore,
    )
from lp.services.database.sqlbase import (
    cursor,
    flush_database_caches,
    )
from lp.services.identity.interfaces.account import (
    AccountCreationRationale,
    AccountStatus,
    AccountSuspendedError,
    )
from lp.services.identity.interfaces.emailaddress import (
    EmailAddressAlreadyTaken,
    EmailAddressStatus,
    InvalidEmailAddress,
    )
from lp.services.identity.model.account import Account
from lp.services.identity.model.emailaddress import EmailAddress
from lp.services.openid.model.openididentifier import OpenIdIdentifier
from lp.testing import (
    ANONYMOUS,
    login,
    logout,
    person_logged_in,
    StormStatementRecorder,
    TestCase,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer
from lp.testing.matchers import HasQueryCount


class TestPersonSet(TestCaseWithFactory):
    """Test `IPersonSet`."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonSet, self).setUp()
        login(ANONYMOUS)
        self.addCleanup(logout)
        self.person_set = getUtility(IPersonSet)

    def test_isNameBlacklisted(self):
        cursor().execute(
            "INSERT INTO NameBlacklist(id, regexp) VALUES (-100, 'foo')")
        self.failUnless(self.person_set.isNameBlacklisted('foo'))
        self.failIf(self.person_set.isNameBlacklisted('bar'))

    def test_isNameBlacklisted_user_is_admin(self):
        team = self.factory.makeTeam()
        name_blacklist_set = getUtility(INameBlacklistSet)
        self.admin_exp = name_blacklist_set.create(u'fnord', admin=team)
        self.store = IStore(self.admin_exp)
        self.store.flush()
        user = team.teamowner
        self.assertFalse(self.person_set.isNameBlacklisted('fnord', user))

    def test_getByEmail_ignores_case_and_whitespace(self):
        person1_email = 'foo.bar@canonical.com'
        person1 = self.person_set.getByEmail(person1_email)
        self.failIf(
            person1 is None,
            "PersonSet.getByEmail() could not find %r" % person1_email)

        person2 = self.person_set.getByEmail('  foo.BAR@canonICAL.com  ')
        self.failIf(
            person2 is None,
            "PersonSet.getByEmail() should ignore case and whitespace.")
        self.assertEqual(person1, person2)

    def test_getByEmail_ignores_unvalidated_emails(self):
        person = self.factory.makePerson()
        self.factory.makeEmail(
            'fnord@example.com',
            person,
            email_status=EmailAddressStatus.NEW)
        found = self.person_set.getByEmail('fnord@example.com')
        self.assertTrue(found is None)

    def test_getPrecachedPersonsFromIDs(self):
        # The getPrecachedPersonsFromIDs() method should only make one
        # query to load all the extraneous data. Accessing the
        # attributes should then cause zero queries.
        person_ids = [self.factory.makePerson().id for i in range(3)]

        with StormStatementRecorder() as recorder:
            persons = list(self.person_set.getPrecachedPersonsFromIDs(
                person_ids, need_karma=True, need_ubuntu_coc=True,
                need_location=True, need_archive=True,
                need_preferred_email=True, need_validity=True))
        self.assertThat(recorder, HasQueryCount(LessThan(2)))

        with StormStatementRecorder() as recorder:
            for person in persons:
                person.is_valid_person
                person.karma
                person.is_ubuntu_coc_signer
                person.location,
                person.archive
                person.preferredemail
        self.assertThat(recorder, HasQueryCount(LessThan(1)))

    def test_getPrecachedPersonsFromIDs_is_ubuntu_coc_signer(self):
        # getPrecachedPersonsFromIDs() sets is_ubuntu_coc_signer
        # correctly.
        person_ids = [self.factory.makePerson().id for i in range(3)]
        SignedCodeOfConduct(owner=person_ids[0], active=True)
        flush_database_caches()

        persons = list(
            self.person_set.getPrecachedPersonsFromIDs(
                person_ids, need_ubuntu_coc=True))
        self.assertContentEqual(
            zip(person_ids, [True, False, False]),
            [(p.id, p.is_ubuntu_coc_signer) for p in persons])

    def test_getByOpenIDIdentifier_returns_person(self):
        # getByOpenIDIdentifier takes a full OpenID identifier and
        # returns the corresponding person.
        person = self.factory.makePerson()
        with person_logged_in(person):
            identifier = person.account.openid_identifiers.one().identifier
        self.assertEqual(
            person,
            self.person_set.getByOpenIDIdentifier(
                u'http://openid.launchpad.dev/+id/%s' % identifier))
        self.assertEqual(
            person,
            self.person_set.getByOpenIDIdentifier(
                u'http://ubuntu-openid.launchpad.dev/+id/%s' % identifier))

    def test_getByOpenIDIdentifier_for_nonexistent_identifier_is_none(self):
        # None is returned if there's no matching person.
        self.assertIs(
            None,
            self.person_set.getByOpenIDIdentifier(
                u'http://openid.launchpad.dev/+id/notanid'))

    def test_getByOpenIDIdentifier_for_bad_domain_is_none(self):
        # Even though the OpenIDIdentifier table doesn't store the
        # domain, we verify it against our known OpenID faux-vhosts.
        # If it doesn't match, we don't even try to check the identifier.
        person = self.factory.makePerson()
        with person_logged_in(person):
            identifier = person.account.openid_identifiers.one().identifier
        self.assertIs(
            None,
            self.person_set.getByOpenIDIdentifier(
                u'http://not.launchpad.dev/+id/%s' % identifier))

    def test_find__accepts_queries_with_or_operator(self):
        # PersonSet.find() allows to search for OR combined terms.
        person_one = self.factory.makePerson(name='baz')
        person_two = self.factory.makeTeam(name='blah')
        result = list(self.person_set.find('baz OR blah'))
        self.assertEqual([person_one, person_two], result)

    def test_findPerson__accepts_queries_with_or_operator(self):
        # PersonSet.findPerson() allows to search for OR combined terms.
        person_one = self.factory.makePerson(
            name='baz', email='one@example.org')
        person_two = self.factory.makePerson(
            name='blah', email='two@example.com')
        result = list(self.person_set.findPerson('baz OR blah'))
        self.assertEqual([person_one, person_two], result)
        # Note that these OR searches do not work for email addresses.
        result = list(self.person_set.findPerson(
            'one@example.org OR two@example.org'))
        self.assertEqual([], result)

    def test_findPerson__case_insensitive_email_address_search(self):
        # A search for email addresses is case insensitve.
        person_one = self.factory.makePerson(
            name='baz', email='ONE@example.org')
        person_two = self.factory.makePerson(
            name='blah', email='two@example.com')
        result = list(self.person_set.findPerson('one@example.org'))
        self.assertEqual([person_one], result)
        result = list(self.person_set.findPerson('TWO@example.com'))
        self.assertEqual([person_two], result)

    def test_findTeam__accepts_queries_with_or_operator(self):
        # PersonSet.findTeam() allows to search for OR combined terms.
        team_one = self.factory.makeTeam(name='baz', email='ONE@example.org')
        team_two = self.factory.makeTeam(name='blah', email='TWO@example.com')
        result = list(self.person_set.findTeam('baz OR blah'))
        self.assertEqual([team_one, team_two], result)
        # Note that these OR searches do not work for email addresses.
        result = list(self.person_set.findTeam(
            'one@example.org OR two@example.org'))
        self.assertEqual([], result)

    def test_findTeam__case_insensitive_email_address_search(self):
        # A search for email addresses is case insensitve.
        team_one = self.factory.makeTeam(name='baz', email='ONE@example.org')
        team_two = self.factory.makeTeam(name='blah', email='TWO@example.com')
        result = list(self.person_set.findTeam('one@example.org'))
        self.assertEqual([team_one], result)
        result = list(self.person_set.findTeam('TWO@example.com'))
        self.assertEqual([team_two], result)


class TestPersonSetCreateByOpenId(TestCaseWithFactory):
    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonSetCreateByOpenId, self).setUp()
        self.person_set = getUtility(IPersonSet)
        self.store = IMasterStore(Account)

        # Generate some valid test data.
        self.account = self.makeAccount()
        self.identifier = self.makeOpenIdIdentifier(self.account, u'whatever')
        self.person = self.makePerson(self.account)
        self.email = self.makeEmailAddress(
            email='whatever@example.com', person=self.person)

    def makeAccount(self):
        return self.store.add(Account(
            displayname='Displayname',
            creation_rationale=AccountCreationRationale.UNKNOWN,
            status=AccountStatus.ACTIVE))

    def makeOpenIdIdentifier(self, account, identifier):
        openid_identifier = OpenIdIdentifier()
        openid_identifier.identifier = identifier
        openid_identifier.account = account
        return self.store.add(openid_identifier)

    def makePerson(self, account):
        return self.store.add(Person(
            name='acc%d' % account.id, account=account,
            displayname='Displayname',
            creation_rationale=PersonCreationRationale.UNKNOWN))

    def makeEmailAddress(self, email, person):
            return self.store.add(EmailAddress(
                email=email,
                account=person.account,
                person=person,
                status=EmailAddressStatus.PREFERRED))

    def testAllValid(self):
        found, updated = self.person_set.getOrCreateByOpenIDIdentifier(
            self.identifier.identifier, self.email.email, 'Ignored Name',
            PersonCreationRationale.UNKNOWN, 'No Comment')
        found = removeSecurityProxy(found)

        self.assertIs(False, updated)
        self.assertIs(self.person, found)
        self.assertIs(self.account, found.account)
        self.assertIs(self.email, found.preferredemail)
        self.assertIs(self.email.account, self.account)
        self.assertIs(self.email.person, self.person)
        self.assertEqual(
            [self.identifier], list(self.account.openid_identifiers))

    def testEmailAddressCaseInsensitive(self):
        # As per testAllValid, but the email address used for the lookup
        # is all upper case.
        found, updated = self.person_set.getOrCreateByOpenIDIdentifier(
            self.identifier.identifier, self.email.email.upper(),
            'Ignored Name', PersonCreationRationale.UNKNOWN, 'No Comment')
        found = removeSecurityProxy(found)

        self.assertIs(False, updated)
        self.assertIs(self.person, found)
        self.assertIs(self.account, found.account)
        self.assertIs(self.email, found.preferredemail)
        self.assertIs(self.email.account, self.account)
        self.assertIs(self.email.person, self.person)
        self.assertEqual(
            [self.identifier], list(self.account.openid_identifiers))

    def testNewOpenId(self):
        # Account looked up by email and the new OpenId identifier
        # attached. We can do this because we trust our OpenId Provider.
        new_identifier = u'newident'
        found, updated = self.person_set.getOrCreateByOpenIDIdentifier(
            new_identifier, self.email.email, 'Ignored Name',
            PersonCreationRationale.UNKNOWN, 'No Comment')
        found = removeSecurityProxy(found)

        self.assertIs(True, updated)
        self.assertIs(self.person, found)
        self.assertIs(self.account, found.account)
        self.assertIs(self.email, found.preferredemail)
        self.assertIs(self.email.account, self.account)
        self.assertIs(self.email.person, self.person)

        # Old OpenId Identifier still attached.
        self.assertIn(self.identifier, list(self.account.openid_identifiers))

        # So is our new one.
        identifiers = [
            identifier.identifier for identifier
                in self.account.openid_identifiers]
        self.assertIn(new_identifier, identifiers)

    def testNewAccountAndIdentifier(self):
        # If neither the OpenId Identifier nor the email address are
        # found, we create everything.
        new_email = u'new_email@example.com'
        new_identifier = u'new_identifier'
        found, updated = self.person_set.getOrCreateByOpenIDIdentifier(
            new_identifier, new_email, 'New Name',
            PersonCreationRationale.UNKNOWN, 'No Comment')
        found = removeSecurityProxy(found)

        # We have a new Person
        self.assertIs(True, updated)
        self.assertIsNot(None, found)

        # It is correctly linked to an account, emailaddress and
        # identifier.
        self.assertIs(found, found.preferredemail.person)
        self.assertEqual(
            new_identifier, found.account.openid_identifiers.any().identifier)

    def testNoAccount(self):
        # EmailAddress is linked to a Person, but there is no Account.
        # Convert this stub into something valid.
        self.email.account = None
        self.email.status = EmailAddressStatus.NEW
        self.person.account = None
        new_identifier = u'new_identifier'
        found, updated = self.person_set.getOrCreateByOpenIDIdentifier(
            new_identifier, self.email.email, 'Ignored',
            PersonCreationRationale.UNKNOWN, 'No Comment')
        found = removeSecurityProxy(found)

        self.assertTrue(updated)

        self.assertIsNot(None, found.account)
        self.assertEqual(
            new_identifier, found.account.openid_identifiers.any().identifier)
        self.assertIs(self.email.person, found)
        self.assertEqual(EmailAddressStatus.PREFERRED, self.email.status)

    def testEmailAddressAccountAndOpenIDAccountAreDifferent(self):
        # The EmailAddress and OpenId Identifier are both in the database,
        # but they are not linked to the same account. In this case, the
        # OpenId Identifier trumps the EmailAddress's account.
        self.identifier.account = self.store.find(
            Account, displayname='Foo Bar').one()
        email_account = self.email.account

        found, updated = self.person_set.getOrCreateByOpenIDIdentifier(
            self.identifier.identifier, self.email.email, 'New Name',
            PersonCreationRationale.UNKNOWN, 'No Comment')
        found = removeSecurityProxy(found)

        self.assertFalse(updated)
        self.assertIs(IPerson(self.identifier.account), found)

        self.assertIs(found.account, self.identifier.account)
        self.assertIn(self.identifier, list(found.account.openid_identifiers))
        self.assertIs(email_account, self.email.account)

    def testEmptyOpenIDIdentifier(self):
        self.assertRaises(
            AssertionError,
            self.person_set.getOrCreateByOpenIDIdentifier, u'', 'foo@bar.com',
            'New Name', PersonCreationRationale.UNKNOWN, 'No Comment')

    def testTeamEmailAddress(self):
        # If the EmailAddress is linked to a team, login fails. There is
        # no way to automatically recover -- someone must manually fix
        # the email address of the team or the SSO account.
        self.factory.makeTeam(email="foo@bar.com")

        self.assertRaises(
            TeamEmailAddressError,
            self.person_set.getOrCreateByOpenIDIdentifier,
            u'other-openid-identifier', 'foo@bar.com', 'New Name',
            PersonCreationRationale.UNKNOWN, 'No Comment')

    def testDeactivatedAccount(self):
        # Logging into a deactivated account with a new email address
        # reactivates the account, adds that email address, and sets it
        # as preferred.
        addr = 'not@an.address'
        self.person.preDeactivate('I hate life.')
        self.assertEqual(AccountStatus.DEACTIVATED, self.person.account_status)
        self.assertIs(None, self.person.preferredemail)
        found, updated = self.person_set.getOrCreateByOpenIDIdentifier(
            self.identifier.identifier, addr, 'New Name',
            PersonCreationRationale.UNKNOWN, 'No Comment')
        self.assertEqual(AccountStatus.ACTIVE, self.person.account_status)
        self.assertEqual(addr, self.person.preferredemail.email)


class TestCreatePersonAndEmail(TestCase):
    """Test `IPersonSet`.createPersonAndEmail()."""
    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCase.setUp(self)
        login(ANONYMOUS)
        self.addCleanup(logout)
        self.person_set = getUtility(IPersonSet)

    def test_duplicated_name_not_accepted(self):
        self.person_set.createPersonAndEmail(
            'testing@example.com', PersonCreationRationale.UNKNOWN,
            name='zzzz')
        self.assertRaises(
            NameAlreadyTaken, self.person_set.createPersonAndEmail,
            'testing2@example.com', PersonCreationRationale.UNKNOWN,
            name='zzzz')

    def test_duplicated_email_not_accepted(self):
        self.person_set.createPersonAndEmail(
            'testing@example.com', PersonCreationRationale.UNKNOWN)
        self.assertRaises(
            EmailAddressAlreadyTaken, self.person_set.createPersonAndEmail,
            'testing@example.com', PersonCreationRationale.UNKNOWN)

    def test_invalid_email_not_accepted(self):
        self.assertRaises(
            InvalidEmailAddress, self.person_set.createPersonAndEmail,
            'testing@.com', PersonCreationRationale.UNKNOWN)

    def test_invalid_name_not_accepted(self):
        self.assertRaises(
            InvalidName, self.person_set.createPersonAndEmail,
            'testing@example.com', PersonCreationRationale.UNKNOWN,
            name='/john')


class TestPersonSetBranchCounts(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        remove_all_sample_data_branches()
        self.person_set = getUtility(IPersonSet)

    def test_no_branches(self):
        """Initially there should be no branches."""
        self.assertEqual(0, self.person_set.getPeopleWithBranches().count())

    def test_five_branches(self):
        branches = [self.factory.makeAnyBranch() for x in range(5)]
        # Each branch has a different product, so any individual product
        # will return one branch.
        self.assertEqual(5, self.person_set.getPeopleWithBranches().count())
        self.assertEqual(1, self.person_set.getPeopleWithBranches(
                branches[0].product).count())


class TestPersonSetEnsurePerson(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer
    email_address = 'testing.ensure.person@example.com'
    displayname = 'Testing ensurePerson'
    rationale = PersonCreationRationale.SOURCEPACKAGEUPLOAD

    def setUp(self):
        TestCaseWithFactory.setUp(self)
        self.person_set = getUtility(IPersonSet)

    def test_ensurePerson_returns_existing_person(self):
        # IPerson.ensurePerson returns existing person and does not
        # override its details.
        testing_displayname = 'will not be modified'
        testing_person = self.factory.makePerson(
            email=self.email_address, displayname=testing_displayname)

        ensured_person = self.person_set.ensurePerson(
            self.email_address, self.displayname, self.rationale)
        self.assertEquals(testing_person.id, ensured_person.id)
        self.assertIsNot(
            ensured_person.displayname, self.displayname,
            'Person.displayname should not be overridden.')
        self.assertIsNot(
            ensured_person.creation_rationale, self.rationale,
            'Person.creation_rationale should not be overridden.')

    def test_ensurePerson_hides_new_person_email(self):
        # IPersonSet.ensurePerson creates new person with
        # 'hide_email_addresses' set.
        ensured_person = self.person_set.ensurePerson(
            self.email_address, self.displayname, self.rationale)
        self.assertTrue(ensured_person.hide_email_addresses)


class TestPersonSetGetOrCreateByOpenIDIdentifier(TestCaseWithFactory):

    layer = DatabaseFunctionalLayer

    def setUp(self):
        super(TestPersonSetGetOrCreateByOpenIDIdentifier, self).setUp()
        self.person_set = getUtility(IPersonSet)

    def callGetOrCreate(self, identifier, email='a@b.com'):
        return self.person_set.getOrCreateByOpenIDIdentifier(
            identifier, email, "Joe Bloggs",
            PersonCreationRationale.SOFTWARE_CENTER_PURCHASE,
            "when purchasing an application via Software Center.")

    def test_existing_person(self):
        email = 'test-email@example.com'
        person = self.factory.makePerson(email=email)
        openid_ident = removeSecurityProxy(
            person.account).openid_identifiers.any().identifier

        result, db_updated = self.callGetOrCreate(openid_ident, email=email)

        self.assertEqual(person, result)
        self.assertFalse(db_updated)

    def test_existing_deactivated_account(self):
        # An existing deactivated account will be reactivated.
        person = self.factory.makePerson(
            account_status=AccountStatus.DEACTIVATED)
        openid_ident = removeSecurityProxy(
            person.account).openid_identifiers.any().identifier

        found_person, db_updated = self.callGetOrCreate(openid_ident)
        self.assertEqual(person, found_person)
        self.assertEqual(AccountStatus.ACTIVE, person.account.status)
        self.assertTrue(db_updated)
        self.assertEqual(
            "when purchasing an application via Software Center.",
            removeSecurityProxy(person.account).status_comment)

    def test_existing_suspended_account(self):
        # An existing suspended account will raise an exception.
        person = self.factory.makePerson(
            account_status=AccountStatus.SUSPENDED)
        openid_ident = removeSecurityProxy(
            person.account).openid_identifiers.any().identifier

        self.assertRaises(
            AccountSuspendedError, self.callGetOrCreate, openid_ident)

    def test_no_account_or_email(self):
        # An identifier can be used to create an account (it is assumed
        # to be already authenticated with SSO).
        person, db_updated = self.callGetOrCreate(u'openid-identifier')

        self.assertEqual(
            u"openid-identifier", removeSecurityProxy(
                person.account).openid_identifiers.any().identifier)
        self.assertTrue(db_updated)

    def test_no_matching_account_existing_email(self):
        # The openid_identity of the account matching the email will
        # updated.
        other_person = self.factory.makePerson('a@b.com')

        person, db_updated = self.callGetOrCreate(
            u'other-openid-identifier', 'a@b.com')

        self.assertEqual(other_person, person)
        self.assert_(
            u'other-openid-identifier' in [
                identifier.identifier for identifier in removeSecurityProxy(
                    person.account).openid_identifiers])
