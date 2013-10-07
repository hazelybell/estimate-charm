# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the generate_ppa_htaccess.py script. """

import crypt
from datetime import (
    datetime,
    timedelta,
    )
import os
import subprocess
import sys
import tempfile

import pytz
from testtools.matchers import (
    AllMatch,
    FileContains,
    FileExists,
    Not,
    )
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.archivepublisher.config import getPubConfig
from lp.archivepublisher.scripts.generate_ppa_htaccess import (
    HtaccessTokenGenerator,
    )
from lp.registry.interfaces.distribution import IDistributionSet
from lp.registry.interfaces.person import IPersonSet
from lp.registry.interfaces.teammembership import TeamMembershipStatus
from lp.services.config import config
from lp.services.log.logger import BufferLogger
from lp.services.mail import stub
from lp.services.osutils import (
    ensure_directory_exists,
    remove_if_exists,
    write_file,
    )
from lp.services.scripts.interfaces.scriptactivity import IScriptActivitySet
from lp.soyuz.enums import (
    ArchiveStatus,
    ArchiveSubscriberStatus,
    )
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import (
    lp_dbuser,
    switch_dbuser,
    )
from lp.testing.layers import LaunchpadZopelessLayer
from lp.testing.mail_helpers import pop_notifications


class TestPPAHtaccessTokenGeneration(TestCaseWithFactory):
    """Test the generate_ppa_htaccess.py script."""

    layer = LaunchpadZopelessLayer
    dbuser = config.generateppahtaccess.dbuser

    SCRIPT_NAME = 'test tokens'

    def setUp(self):
        super(TestPPAHtaccessTokenGeneration, self).setUp()
        self.owner = self.factory.makePerson(
            name="joe", displayname="Joe Smith")
        self.ppa = self.factory.makeArchive(
            owner=self.owner, name="myppa", private=True)

        # "Ubuntu" doesn't have a proper publisher config but Ubuntutest
        # does, so override the PPA's distro here.
        ubuntutest = getUtility(IDistributionSet)['ubuntutest']
        self.ppa.distribution = ubuntutest

    def getScript(self, test_args=None):
        """Return a HtaccessTokenGenerator instance."""
        if test_args is None:
            test_args = []
        script = HtaccessTokenGenerator(self.SCRIPT_NAME, test_args=test_args)
        script.logger = BufferLogger()
        script.txn = self.layer.txn
        switch_dbuser(self.dbuser)
        return script

    def runScript(self):
        """Run the expiry script.

        :return: a tuple of return code, stdout and stderr.
        """
        script = os.path.join(
            config.root, "cronscripts", "generate-ppa-htaccess.py")
        args = [sys.executable, script, "-v"]
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        return process.returncode, stdout, stderr

    def testEnsureHtaccess(self):
        """Ensure that the .htaccess file is generated correctly."""
        # The publisher Config object does not have an interface, so we
        # need to remove the security wrapper.
        pub_config = getPubConfig(self.ppa)

        filename = os.path.join(pub_config.htaccessroot, ".htaccess")
        remove_if_exists(filename)
        script = self.getScript()
        script.ensureHtaccess(self.ppa)
        self.addCleanup(remove_if_exists, filename)

        contents = [
            "",
            "AuthType           Basic",
            "AuthName           \"Token Required\"",
            "AuthUserFile       %s/.htpasswd" % pub_config.htaccessroot,
            "Require            valid-user",
            "",
            ]
        self.assertThat(filename, FileContains('\n'.join(contents)))

    def testGenerateHtpasswd(self):
        """Given some `ArchiveAuthToken`s, test generating htpasswd."""
        # Make some subscriptions and tokens.
        tokens = []
        for name in ['name12', 'name16']:
            person = getUtility(IPersonSet).getByName(name)
            self.ppa.newSubscription(person, self.ppa.owner)
            tokens.append(self.ppa.newAuthToken(person))
        token_usernames = [token.person.name for token in tokens]

        # Generate the passwd file.
        script = self.getScript()
        filename = script.generateHtpasswd(self.ppa)
        self.addCleanup(remove_if_exists, filename)

        # It should be a temp file in the same directory as the intended
        # target file when it's renamed, so that os.rename() won't
        # complain about renaming across file systems.
        pub_config = getPubConfig(self.ppa)
        self.assertEqual(
            pub_config.htaccessroot, os.path.dirname(filename))

        # Read it back in.
        file_contents = [
            line.strip().split(':', 1) for line in open(filename, 'r')]

        # First entry is buildd secret, rest are from tokens.
        usernames = list(zip(*file_contents)[0])
        self.assertEqual(['buildd'] + token_usernames, usernames)

        # We can re-encrypt the buildd_secret and it should match the
        # one in the .htpasswd file.
        password = file_contents[0][1]
        encrypted_secret = crypt.crypt(self.ppa.buildd_secret, password)
        self.assertEqual(encrypted_secret, password)

    def testReplaceUpdatedHtpasswd(self):
        """Test that the htpasswd file is only replaced if it changes."""
        FILE_CONTENT = "Kneel before Zod!"
        # The publisher Config object does not have an interface, so we
        # need to remove the security wrapper.
        pub_config = getPubConfig(self.ppa)
        filename = os.path.join(pub_config.htaccessroot, ".htpasswd")

        # Write out a dummy .htpasswd
        ensure_directory_exists(pub_config.htaccessroot)
        write_file(filename, FILE_CONTENT)

        # Write the same contents in a temp file.
        fd, temp_filename = tempfile.mkstemp(dir=pub_config.htaccessroot)
        file = os.fdopen(fd, "w")
        file.write(FILE_CONTENT)
        file.close()

        # Replacement should not happen.
        script = self.getScript()
        self.assertFalse(
            script.replaceUpdatedHtpasswd(self.ppa, temp_filename))

        # Writing a different .htpasswd should see it get replaced.
        write_file(filename, "Come to me, son of Jor-El!")

        self.assertTrue(
            script.replaceUpdatedHtpasswd(self.ppa, temp_filename))

        os.remove(filename)

    def assertDeactivated(self, token):
        """Helper function to test token deactivation state."""
        return self.assertNotEqual(token.date_deactivated, None)

    def assertNotDeactivated(self, token):
        """Helper function to test token deactivation state."""
        self.assertEqual(token.date_deactivated, None)

    def setupSubscriptionsAndTokens(self):
        """Set up a few subscriptions and test tokens and return them."""
        # Set up some teams.  We need to test a few scenarios:
        # - someone in one subscribed team and leaving that team loses
        #    their token.
        # - someone in two subscribed teams leaving one team does not
        #   lose their token.
        # - All members of a team lose their tokens when a team of a
        #   subscribed team leaves it.

        persons1 = []
        persons2 = []
        name12 = getUtility(IPersonSet).getByName("name12")
        team1 = self.factory.makeTeam(owner=name12)
        team2 = self.factory.makeTeam(owner=name12)
        for count in range(5):
            person = self.factory.makePerson()
            team1.addMember(person, name12)
            persons1.append(person)
            person = self.factory.makePerson()
            team2.addMember(person, name12)
            persons2.append(person)

        all_persons = persons1 + persons2

        parent_team = self.factory.makeTeam(owner=name12)
        # This needs to be forced or TeamParticipation is not updated.
        parent_team.addMember(team2, name12, force_team_add=True)

        promiscuous_person = self.factory.makePerson()
        team1.addMember(promiscuous_person, name12)
        team2.addMember(promiscuous_person, name12)
        all_persons.append(promiscuous_person)

        lonely_person = self.factory.makePerson()
        all_persons.append(lonely_person)

        # At this point we have team1, with 5 people in it, team2 with 5
        # people in it, team3 with only team2 in it, promiscuous_person
        # who is in team1 and team2, and lonely_person who is in no
        # teams.

        # Ok now do some subscriptions and ensure everyone has a token.
        self.ppa.newSubscription(team1, self.ppa.owner)
        self.ppa.newSubscription(parent_team, self.ppa.owner)
        self.ppa.newSubscription(lonely_person, self.ppa.owner)
        tokens = {}
        for person in all_persons:
            tokens[person] = self.ppa.newAuthToken(person)

        return (
            team1, team2, parent_team, lonely_person,
            promiscuous_person, all_persons, persons1, persons2, tokens)

    def testDeactivatingTokens(self):
        """Test that token deactivation happens properly."""
        data = self.setupSubscriptionsAndTokens()
        (team1, team2, parent_team, lonely_person, promiscuous_person,
            all_persons, persons1, persons2, tokens) = data
        team1_person = persons1[0]

        # Initially, nothing is eligible for deactivation.
        script = self.getScript()
        script.deactivateInvalidTokens()
        for person in tokens:
            self.assertNotDeactivated(tokens[person])

        # Now remove someone from team1, he will lose his token but
        # everyone else keeps theirs.
        with lp_dbuser():
            team1_person.leave(team1)
        # Clear out emails generated when leaving a team.
        pop_notifications()

        script.deactivateInvalidTokens(send_email=True)
        self.assertDeactivated(tokens[team1_person])
        del tokens[team1_person]
        for person in tokens:
            self.assertNotDeactivated(tokens[person])

        # Ensure that a cancellation email was sent.
        num_emails = len(stub.test_emails)
        self.assertEqual(
            num_emails, 1, "Expected 1 email, got %s" % num_emails)

        # Promiscuous_person now leaves team1, but does not lose his
        # token because he's also in team2. No other tokens are
        # affected.
        with lp_dbuser():
            promiscuous_person.leave(team1)
        # Clear out emails generated when leaving a team.
        pop_notifications()
        script.deactivateInvalidTokens(send_email=True)
        self.assertNotDeactivated(tokens[promiscuous_person])
        for person in tokens:
            self.assertNotDeactivated(tokens[person])

        # Ensure that a cancellation email was not sent.
        num_emails = len(stub.test_emails)
        self.assertEqual(
            num_emails, 0, "Expected no emails, got %s" % num_emails)

        # Team 2 now leaves parent_team, and all its members lose their
        # tokens.
        with lp_dbuser():
            name12 = getUtility(IPersonSet).getByName("name12")
            parent_team.setMembershipData(
                team2, TeamMembershipStatus.APPROVED, name12)
            parent_team.setMembershipData(
                team2, TeamMembershipStatus.DEACTIVATED, name12)
            self.assertFalse(team2.inTeam(parent_team))
        script.deactivateInvalidTokens()
        for person in persons2:
            self.assertDeactivated(tokens[person])

        # promiscuous_person also loses the token because he's not in
        # either team now.
        self.assertDeactivated(tokens[promiscuous_person])

        # lonely_person still has his token, he's not in any teams.
        self.assertNotDeactivated(tokens[lonely_person])

    def setupDummyTokens(self):
        """Helper function to set up some tokens."""
        name12 = getUtility(IPersonSet).getByName("name12")
        name16 = getUtility(IPersonSet).getByName("name16")
        sub1 = self.ppa.newSubscription(name12, self.ppa.owner)
        sub2 = self.ppa.newSubscription(name16, self.ppa.owner)
        token1 = self.ppa.newAuthToken(name12)
        token2 = self.ppa.newAuthToken(name16)
        self.layer.txn.commit()
        subs = [sub1]
        subs.append(sub2)
        tokens = [token1]
        tokens.append(token2)
        return subs, tokens

    def ensureNoFiles(self):
        """Ensure the .ht* files don't already exist."""
        pub_config = getPubConfig(self.ppa)
        htaccess = os.path.join(pub_config.htaccessroot, ".htaccess")
        htpasswd = os.path.join(pub_config.htaccessroot, ".htpasswd")
        remove_if_exists(htaccess)
        remove_if_exists(htpasswd)
        return htaccess, htpasswd

    def testSubscriptionExpiry(self):
        """Ensure subscriptions' statuses are set to EXPIRED properly."""
        subs, tokens = self.setupDummyTokens()
        now = datetime.now(pytz.UTC)

        # Expire the first subscription.
        subs[0].date_expires = now - timedelta(minutes=3)
        self.assertEqual(subs[0].status, ArchiveSubscriberStatus.CURRENT)

        # Set the expiry in the future for the second.
        subs[1].date_expires = now + timedelta(minutes=3)
        self.assertEqual(subs[0].status, ArchiveSubscriberStatus.CURRENT)

        # Run the script and make sure only the first was expired.
        script = self.getScript()
        script.main()
        self.assertEqual(subs[0].status, ArchiveSubscriberStatus.EXPIRED)
        self.assertEqual(subs[1].status, ArchiveSubscriberStatus.CURRENT)

    def testBasicOperation(self):
        """Invoke the actual script and make sure it generates some files."""
        self.setupDummyTokens()
        htaccess, htpasswd = self.ensureNoFiles()

        # Call the script and check that we have a .htaccess and a
        # .htpasswd.
        return_code, stdout, stderr = self.runScript()
        self.assertEqual(
            return_code, 0, "Got a bad return code of %s\nOutput:\n%s" %
                (return_code, stderr))
        self.assertThat([htaccess, htpasswd], AllMatch(FileExists()))
        os.remove(htaccess)
        os.remove(htpasswd)

    def _setupOptionsData(self):
        """Setup test data for option testing."""
        subs, tokens = self.setupDummyTokens()

        # Cancel the first subscription.
        subs[0].cancel(self.ppa.owner)
        self.assertNotDeactivated(tokens[0])
        return subs, tokens

    def testDryrunOption(self):
        """Test that the dryrun and no-deactivation option works."""
        subs, tokens = self._setupOptionsData()

        htaccess, htpasswd = self.ensureNoFiles()
        script = self.getScript(test_args=["--dry-run"])
        script.main()

        # Assert no files were written.
        self.assertThat([htaccess, htpasswd], AllMatch(Not(FileExists())))

        # Assert that the cancelled subscription did not cause the token
        # to get deactivated.
        self.assertNotDeactivated(tokens[0])

    def testNoDeactivationOption(self):
        """Test that the --no-deactivation option works."""
        subs, tokens = self._setupOptionsData()
        script = self.getScript(test_args=["--no-deactivation"])
        script.main()
        self.assertNotDeactivated(tokens[0])
        script = self.getScript()
        script.main()
        self.assertDeactivated(tokens[0])

    def testBlacklistingPPAs(self):
        """Test that the htaccess for blacklisted PPAs are not touched."""
        subs, tokens = self.setupDummyTokens()
        htaccess, htpasswd = self.ensureNoFiles()

        # Setup the first subscription so that it is due to be expired.
        now = datetime.now(pytz.UTC)
        subs[0].date_expires = now - timedelta(minutes=3)
        self.assertEqual(subs[0].status, ArchiveSubscriberStatus.CURRENT)

        script = self.getScript()
        script.blacklist = {'joe': ['my_other_ppa', 'myppa', 'and_another']}
        script.main()

        # The tokens will still be deactivated, and subscriptions expired.
        self.assertDeactivated(tokens[0])
        self.assertEqual(subs[0].status, ArchiveSubscriberStatus.EXPIRED)
        # But the htaccess is not touched.
        self.assertThat([htaccess, htpasswd], AllMatch(Not(FileExists())))

    def testSkippingOfDisabledPPAs(self):
        """Test that the htaccess for disabled PPAs are not touched."""
        subs, tokens = self.setupDummyTokens()
        htaccess, htpasswd = self.ensureNoFiles()

        # Setup subscription so that htaccess/htpasswd is pending generation.
        now = datetime.now(pytz.UTC)
        subs[0].date_expires = now + timedelta(minutes=3)
        self.assertEqual(subs[0].status, ArchiveSubscriberStatus.CURRENT)

        # Set the PPA as disabled.
        self.ppa.disable()
        self.assertFalse(self.ppa.enabled)

        script = self.getScript()
        script.main()

        # The htaccess and htpasswd files should not be generated.
        self.assertThat([htaccess, htpasswd], AllMatch(Not(FileExists())))

    def testSkippingOfDeletedPPAs(self):
        """Test that the htaccess for deleted PPAs are not touched."""
        subs, tokens = self.setupDummyTokens()
        htaccess, htpasswd = self.ensureNoFiles()

        # Setup subscription so that htaccess/htpasswd is pending generation.
        now = datetime.now(pytz.UTC)
        subs[0].date_expires = now + timedelta(minutes=3)
        self.assertEqual(subs[0].status, ArchiveSubscriberStatus.CURRENT)

        # Set the PPA as deleted.
        self.ppa.status = ArchiveStatus.DELETED

        script = self.getScript()
        script.main()

        # The htaccess and htpasswd files should not be generated.
        self.assertThat([htaccess, htpasswd], AllMatch(Not(FileExists())))

    def testSendingCancellationEmail(self):
        """Test that when a token is deactivated, its user gets an email.

        The email must contain the right headers and text.
        """
        subs, tokens = self.setupDummyTokens()
        script = self.getScript()

        # Clear out any existing email.
        pop_notifications()

        script.sendCancellationEmail(tokens[0])

        num_emails = len(stub.test_emails)
        self.assertEqual(
            num_emails, 1, "Expected 1 email, got %s" % num_emails)

        [email] = pop_notifications()
        self.assertEqual(
            email['Subject'],
            "PPA access cancelled for PPA named myppa for Joe Smith")
        self.assertEqual(email['To'], "test@canonical.com")
        self.assertEqual(
            email['From'],
            "PPA named myppa for Joe Smith <noreply@launchpad.net>")
        self.assertEqual(email['Sender'], "bounces@canonical.com")

        body = email.get_payload()
        self.assertEqual(
            body,
            "Hello Sample Person,\n\n"
            "Launchpad: cancellation of archive access\n"
            "-----------------------------------------\n\n"
            "Your access to the private software archive "
                "\"PPA named myppa for Joe\nSmith\", "
            "which is hosted by Launchpad, has been "
                "cancelled.\n\n"
            "You will now no longer be able to download software from this "
                "archive.\n"
            "If you think this cancellation is in error, you should contact "
                "the owner\n"
            "of the archive to verify it.\n\n"
            "You can contact the archive owner by visiting their Launchpad "
                "page here:\n\n"
            "<http://launchpad.dev/~joe>\n\n"
            "If you have any concerns you can contact the Launchpad team by "
                "emailing\n"
            "feedback@launchpad.net\n\n"
            "Regards,\n"
            "The Launchpad team")

    def testNoEmailOnCancellationForSuppressedArchive(self):
        """No email should be sent if the archive has
        suppress_subscription_notifications set."""
        subs, tokens = self.setupDummyTokens()
        token = tokens[0]
        token.archive.suppress_subscription_notifications = True
        script = self.getScript()

        # Clear out any existing email.
        pop_notifications()

        script.sendCancellationEmail(token)

        num_emails = len(stub.test_emails)
        self.assertEqual(
            num_emails, 0, "Expected 0 emails, got %s" % num_emails)

    def test_getTimeToSyncFrom(self):
        # Sync from 1s before previous start to catch anything made during the
        # last script run, and to handle NTP clock skew.
        now = datetime.now(pytz.UTC)
        script_start_time = now - timedelta(seconds=2)
        script_end_time = now

        getUtility(IScriptActivitySet).recordSuccess(
            self.SCRIPT_NAME, script_start_time, script_end_time)
        script = self.getScript()
        self.assertEqual(
            script_start_time - timedelta(seconds=1),
            script.getTimeToSyncFrom())

    def test_getNewPrivatePPAs_no_previous_run(self):
        # All private PPAs are returned if there was no previous run.
        # This happens even if they have no tokens.

        # Create a public PPA that should not be in the list.
        self.factory.makeArchive(private=False)

        script = self.getScript()
        self.assertContentEqual([self.ppa], script.getNewPrivatePPAs())

    def test_getNewPrivatePPAs_only_those_since_last_run(self):
        # Only private PPAs created since the last run are returned.
        # This happens even if they have no tokens.
        last_start = datetime.now(pytz.UTC) - timedelta(seconds=90)
        before_last_start = last_start - timedelta(seconds=30)
        removeSecurityProxy(self.ppa).date_created = before_last_start

        # Create a new PPA that should show up.
        new_ppa = self.factory.makeArchive(private=True)

        script = self.getScript()
        new_ppas = script.getNewPrivatePPAs(since=last_start)
        self.assertContentEqual([new_ppa], new_ppas)

    def test_getNewTokens_no_previous_run(self):
        """All valid tokens returned if there is no record of previous run."""
        tokens = self.setupDummyTokens()[1]

        # If there is no record of the script running previously, all
        # valid tokens are returned.
        script = self.getScript()
        self.assertContentEqual(tokens, script.getNewTokens())

    def test_getNewTokens_only_those_since_last_run(self):
        """Only tokens created since the last run are returned."""
        last_start = datetime.now(pytz.UTC) - timedelta(seconds=90)
        before_last_start = last_start - timedelta(seconds=30)

        tokens = self.setupDummyTokens()[1]
        # This token will not be included.
        removeSecurityProxy(tokens[0]).date_created = before_last_start

        script = self.getScript()
        new_tokens = script.getNewTokens(since=last_start)
        self.assertContentEqual(tokens[1:], new_tokens)

    def test_getNewTokens_only_active_tokens(self):
        """Only active tokens are returned."""
        tokens = self.setupDummyTokens()[1]
        tokens[0].deactivate()

        script = self.getScript()
        self.assertContentEqual(tokens[1:], script.getNewTokens())

    def test_processes_PPAs_without_subscription(self):
        # A .htaccess file is written for Private PPAs even if they don't have
        # any subscriptions.
        htaccess, htpasswd = self.ensureNoFiles()
        transaction.commit()

        # Call the script and check that we have a .htaccess and a
        # .htpasswd.
        return_code, stdout, stderr = self.runScript()
        self.assertEqual(
            return_code, 0, "Got a bad return code of %s\nOutput:\n%s" %
                (return_code, stderr))
        self.assertThat([htaccess, htpasswd], AllMatch(FileExists()))
        os.remove(htaccess)
        os.remove(htpasswd)
