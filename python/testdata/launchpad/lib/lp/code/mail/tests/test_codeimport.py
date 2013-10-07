# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for code import related mailings"""

from email import message_from_string

import transaction

from lp.code.enums import RevisionControlSystems
from lp.services.mail import stub
from lp.testing import (
    login_person,
    TestCaseWithFactory,
    )
from lp.testing.layers import DatabaseFunctionalLayer


class TestNewCodeImports(TestCaseWithFactory):
    """Test the emails sent out for new code imports."""

    layer = DatabaseFunctionalLayer

    def test_cvs_import(self):
        # Test the email for a new CVS import.
        eric = self.factory.makePerson(name='eric')
        fooix = self.factory.makeProduct(name='fooix')
        # Eric needs to be logged in for the mail to be sent.
        login_person(eric)
        code_import = self.factory.makeProductCodeImport(
            cvs_root=':pserver:anonymouse@cvs.example.com:/cvsroot',
            cvs_module='a_module', branch_name='import',
            product=fooix, registrant=eric)
        transaction.commit()
        msg = message_from_string(stub.test_emails[0][2])
        self.assertEqual('code-import', msg['X-Launchpad-Notification-Type'])
        self.assertEqual('~eric/fooix/import', msg['X-Launchpad-Branch'])
        self.assertEqual(
            'A new CVS code import has been requested by Eric:\n'
            '    http://code.launchpad.dev/~eric/fooix/import\n'
            'from\n'
            '    :pserver:anonymouse@cvs.example.com:/cvsroot, a_module\n'
            '\n'
            '-- \nYou are getting this email because you are a member of the '
            'vcs-imports team.\n', msg.get_payload(decode=True))

    def test_svn_import(self):
        # Test the email for a new subversion import.
        eric = self.factory.makePerson(name='eric')
        fooix = self.factory.makeProduct(name='fooix')
        # Eric needs to be logged in for the mail to be sent.
        login_person(eric)
        code_import = self.factory.makeProductCodeImport(
            svn_branch_url='svn://svn.example.com/fooix/trunk',
            branch_name='trunk', product=fooix, registrant=eric,
            rcs_type=RevisionControlSystems.BZR_SVN)
        transaction.commit()
        msg = message_from_string(stub.test_emails[0][2])
        self.assertEqual('code-import', msg['X-Launchpad-Notification-Type'])
        self.assertEqual('~eric/fooix/trunk', msg['X-Launchpad-Branch'])
        self.assertEqual(
            'A new subversion code import has been requested by Eric:\n'
            '    http://code.launchpad.dev/~eric/fooix/trunk\n'
            'from\n'
            '    svn://svn.example.com/fooix/trunk\n'
            '\n'
            '-- \nYou are getting this email because you are a member of the '
            'vcs-imports team.\n', msg.get_payload(decode=True))

    def test_git_import(self):
        # Test the email for a new git import.
        eric = self.factory.makePerson(name='eric')
        fooix = self.factory.makeProduct(name='fooix')
        # Eric needs to be logged in for the mail to be sent.
        login_person(eric)
        code_import = self.factory.makeProductCodeImport(
            git_repo_url='git://git.example.com/fooix.git',
            branch_name='master', product=fooix, registrant=eric)
        transaction.commit()
        msg = message_from_string(stub.test_emails[0][2])
        self.assertEqual('code-import', msg['X-Launchpad-Notification-Type'])
        self.assertEqual('~eric/fooix/master', msg['X-Launchpad-Branch'])
        self.assertEqual(
            'A new git code import has been requested '
            'by Eric:\n'
            '    http://code.launchpad.dev/~eric/fooix/master\n'
            'from\n'
            '    git://git.example.com/fooix.git\n'
            '\n'
            '-- \nYou are getting this email because you are a member of the '
            'vcs-imports team.\n', msg.get_payload(decode=True))

    def test_new_source_package_import(self):
        # Test the email for a new sourcepackage import.
        eric = self.factory.makePerson(name='eric')
        distro = self.factory.makeDistribution(name='foobuntu')
        series = self.factory.makeDistroSeries(
            name='manic', distribution=distro)
        fooix = self.factory.makeSourcePackage(
            sourcepackagename='fooix', distroseries=series)
        # Eric needs to be logged in for the mail to be sent.
        login_person(eric)
        code_import = self.factory.makePackageCodeImport(
            git_repo_url='git://git.example.com/fooix.git',
            branch_name='master', sourcepackage=fooix, registrant=eric)
        transaction.commit()
        msg = message_from_string(stub.test_emails[0][2])
        self.assertEqual('code-import', msg['X-Launchpad-Notification-Type'])
        self.assertEqual(
            '~eric/foobuntu/manic/fooix/master', msg['X-Launchpad-Branch'])
        self.assertEqual(
            'A new git code import has been requested '
            'by Eric:\n'
            '    http://code.launchpad.dev/~eric/foobuntu/manic/fooix/master\n'
            'from\n'
            '    git://git.example.com/fooix.git\n'
            '\n'
            '-- \nYou are getting this email because you are a member of the '
            'vcs-imports team.\n', msg.get_payload(decode=True))
