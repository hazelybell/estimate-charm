# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Acceptance test for the translations-export-to-branch script."""

import datetime
import re
from textwrap import dedent

from bzrlib.errors import NotBranchError
import pytz
from testtools.matchers import MatchesRegex
import transaction
from zope.component import getUtility
from zope.security.proxy import removeSecurityProxy

from lp.app.enums import ServiceUsage
from lp.registry.interfaces.teammembership import (
    ITeamMembershipSet,
    TeamMembershipStatus,
    )
from lp.registry.model.productseries import ProductSeries
from lp.services.config import config
from lp.services.database.interfaces import ISlaveStore
from lp.services.log.logger import BufferLogger
from lp.services.scripts.tests import run_script
from lp.testing import (
    map_branch_contents,
    TestCaseWithFactory,
    )
from lp.testing.fakemethod import FakeMethod
from lp.testing.layers import ZopelessAppServerLayer
from lp.translations.scripts.translations_to_branch import (
    ExportTranslationsToBranch,
    )


class GruesomeException(Exception):
    """CPU on fire.  Or some other kind of failure."""


class TestExportTranslationsToBranch(TestCaseWithFactory):

    layer = ZopelessAppServerLayer

    def _filterOutput(self, output):
        """Remove DEBUG lines from output."""
        return '\n'.join([
            line for line in output.splitlines()
            if not line.startswith('DEBUG')])

    def test_translations_export_to_branch(self):
        # End-to-end test of the script doing its work.

        # Set up a server for hosted branches.
        self.useBzrBranches(direct_database=False)

        # Set up a product and translatable series.
        product = self.factory.makeProduct(name='committobranch')
        product = removeSecurityProxy(product)
        series = product.getSeries('trunk')

        # Set up a translations_branch for the series.
        db_branch, tree = self.create_branch_and_tree(product=product)
        removeSecurityProxy(db_branch).last_scanned_id = 'null:'
        product.translations_usage = ServiceUsage.LAUNCHPAD
        series.translations_branch = db_branch

        # Set up a template & Dutch translation for the series.
        template = self.factory.makePOTemplate(
            productseries=series, owner=product.owner, name='foo',
            path='po/messages.pot')
        template = removeSecurityProxy(template)
        potmsgset = self.factory.makePOTMsgSet(
            template, singular='Hello World', sequence=1)
        pofile = self.factory.makePOFile(
            'nl', potemplate=template, owner=product.owner)
        self.factory.makeCurrentTranslationMessage(
            pofile=pofile, potmsgset=potmsgset,
            translator=product.owner, reviewer=product.owner,
            translations=['Hallo Wereld'])

        # Make all this visible to the script we're about to run.
        transaction.commit()

        # Run The Script.
        retcode, stdout, stderr = run_script(
            'cronscripts/translations-export-to-branch.py', ['-vvv'])

        self.assertEqual('', stdout)
        self.assertEqual(
            'INFO    '
            'Creating lockfile: '
            '/var/lock/launchpad-translations-export-to-branch.lock\n'
            'INFO    Exporting to translations branches.\n'
            'INFO    Exporting Committobranch trunk series.\n'
            'INFO    '
            'Processed 1 item(s); 0 failure(s), 0 unpushed branch(es).',
            self._filterOutput(stderr))
        self.assertIn('No previous translations commit found.', stderr)
        self.assertEqual(0, retcode)

        # The branch now contains a snapshot of the translation.  (Only
        # one file: the Dutch translation we set up earlier).
        branch_contents = map_branch_contents(db_branch.getBzrBranch())
        expected_contents = {
            'po/nl.po': """
                # Dutch translation for .*
                # Copyright .*
                (?:#.*$
                )*msgid ""
                msgstr ""
                (?:"[^"]*"
                )*
                msgid "Hello World"
                msgstr "Hallo Wereld"\n""",
        }

        branch_filenames = set(branch_contents.iterkeys())
        expected_filenames = set(expected_contents.iterkeys())

        unexpected_filenames = branch_filenames - expected_filenames
        self.assertEqual(set(), unexpected_filenames)

        missing_filenames = expected_filenames - branch_filenames
        self.assertEqual(set(), missing_filenames)

        for filename, expected in expected_contents.iteritems():
            contents = branch_contents[filename].lstrip('\n')
            pattern = dedent(expected.lstrip('\n'))
            if not re.match(pattern, contents, re.MULTILINE):
                self.assertEqual(pattern, contents)

        # If we run the script again at this point, it won't export
        # anything because it sees that the POFile has not been changed
        # since the last export.
        retcode, stdout, stderr = run_script(
            'cronscripts/translations-export-to-branch.py',
            ['-vvv', '--no-fudge'])
        self.assertEqual(0, retcode)
        self.assertIn('Last commit was at', stderr)
        self.assertIn(
            "Processed 1 item(s); 0 failure(s), 0 unpushed branch(es).",
            stderr)
        self.assertEqual(
            None, re.search("INFO\s+Committed [0-9]+ file", stderr))

    def test_exportToStaleBranch(self):
        # Attempting to export to a stale branch marks it for scanning.
        self.useBzrBranches(direct_database=False)
        exporter = ExportTranslationsToBranch(test_args=[])
        exporter.logger = BufferLogger()
        productseries = self.factory.makeProductSeries()
        db_branch, tree = self.create_branch_and_tree(
            product=productseries.product)
        removeSecurityProxy(productseries).translations_branch = db_branch
        db_branch.last_mirrored_id = 'stale-id'
        db_branch.last_scanned_id = db_branch.last_mirrored_id
        self.becomeDbUser('translationstobranch')
        self.assertFalse(db_branch.pending_writes)
        self.assertNotEqual(
            db_branch.last_mirrored_id, tree.branch.last_revision())
        # The export code works on a Branch from the slave store.  It
        # shouldn't stop the scan request.
        slave_series = ISlaveStore(productseries).get(
            ProductSeries, productseries.id)
        exporter._exportToBranch(slave_series)
        self.assertEqual(
            db_branch.last_mirrored_id, tree.branch.last_revision())
        self.assertTrue(db_branch.pending_writes)
        matches = MatchesRegex(
            "(.|\n)*WARNING Skipped .* due to stale DB info, and scheduled a "
            "new scan.")
        self.assertThat(exporter.logger.getLogBuffer(), matches)

    def test_exportToBranches_handles_nonascii_exceptions(self):
        # There's an exception handler in _exportToBranches that must
        # cope well with non-ASCII exception strings.
        productseries = self.factory.makeProductSeries()
        exporter = ExportTranslationsToBranch(test_args=[])
        exporter.logger = BufferLogger()
        boom = u'\u2639'
        exporter._exportToBranch = FakeMethod(failure=GruesomeException(boom))

        self.becomeDbUser('translationstobranch')

        exporter._exportToBranches([productseries])

        self.assertEqual(1, exporter._exportToBranch.call_count)

        message = exporter.logger.getLogBuffer()
        self.assertTrue(message.startswith("ERROR"))
        self.assertTrue("GruesomeException" in message)

    def test_exportToBranches_handles_unpushed_branches(self):
        # bzrlib raises NotBranchError when accessing a nonexistent
        # branch.  The exporter deals with that by calling
        # _handleUnpushedBranch.
        exporter = ExportTranslationsToBranch(test_args=[])
        exporter.logger = BufferLogger()
        productseries = self.factory.makeProductSeries()
        productseries.translations_branch = self.factory.makeBranch()

        self.becomeDbUser('translationstobranch')

        # _handleUnpushedBranch is called if _exportToBranch raises
        # NotBranchError.
        exporter._handleUnpushedBranch = FakeMethod()
        exporter._exportToBranch = FakeMethod(failure=NotBranchError("No!"))
        exporter._exportToBranches([productseries])
        self.assertEqual(1, exporter._handleUnpushedBranch.call_count)

        # This does not happen if the export succeeds.
        exporter._handleUnpushedBranch = FakeMethod()
        exporter._exportToBranch = FakeMethod()
        exporter._exportToBranches([productseries])
        self.assertEqual(0, exporter._handleUnpushedBranch.call_count)

        # Nor does it happen if the export fails in some other way.
        exporter._handleUnpushedBranch = FakeMethod()
        exporter._exportToBranch = FakeMethod(failure=IndexError("Ayyeee!"))
        exporter._exportToBranches([productseries])
        self.assertEqual(0, exporter._handleUnpushedBranch.call_count)

    def test_handleUnpushedBranch_mails_branch_owner(self):
        exporter = ExportTranslationsToBranch(test_args=[])
        exporter.logger = BufferLogger()
        productseries = self.factory.makeProductSeries()
        email = self.factory.getUniqueEmailAddress()
        branch_owner = self.factory.makePerson(email=email)
        productseries.translations_branch = self.factory.makeBranch(
            owner=branch_owner)
        exporter._exportToBranch = FakeMethod(failure=NotBranchError("Ow"))
        exporter._sendMail = FakeMethod()

        self.becomeDbUser('translationstobranch')

        exporter._exportToBranches([productseries])

        self.assertEqual(1, exporter._sendMail.call_count)
        (sender, recipients, subject, text), kwargs = (
            exporter._sendMail.calls[-1])
        self.assertIn(config.canonical.noreply_from_address, sender)
        self.assertIn(email, recipients)
        self.assertEqual(
            "Launchpad: translations branch has not been set up.", subject)

        self.assertIn(
            "problem with translations branch synchronization", text)
        self.assertIn(productseries.title, text)
        self.assertIn(productseries.translations_branch.bzr_identity, text)
        self.assertIn('bzr push lp://', text)

    def test_handleUnpushedBranch_has_required_privileges(self):
        # Dealing with an unpushed branch is a special code path that
        # was not exercised by the full-script test.  Ensure that it has
        # the database privileges that it requires.
        exporter = ExportTranslationsToBranch(test_args=[])
        exporter.logger = BufferLogger()
        productseries = self.factory.makeProductSeries()
        email = self.factory.getUniqueEmailAddress()
        branch_owner = self.factory.makePerson(email=email)
        productseries.translations_branch = self.factory.makeBranch(
            owner=branch_owner)
        exporter._exportToBranch = FakeMethod(failure=NotBranchError("Ow"))

        self.becomeDbUser('translationstobranch')

        exporter._handleUnpushedBranch(productseries)

        # _handleUnpushedBranch completes successfully.  There are no
        # database changes still pending in the ORM that are going to
        # fail either.
        transaction.commit()

    def test_handleUnpushedBranch_is_privileged_to_contact_team(self):
        # Notifying a branch owner that is a team can require other
        # database privileges.  The script also has these privileges.
        exporter = ExportTranslationsToBranch(test_args=[])
        exporter.logger = BufferLogger()
        productseries = self.factory.makeProductSeries()
        email = self.factory.getUniqueEmailAddress()
        team_member = self.factory.makePerson(email=email)
        branch_owner = self.factory.makeTeam()
        getUtility(ITeamMembershipSet).new(
            team_member, branch_owner, TeamMembershipStatus.APPROVED,
            branch_owner.teamowner)
        productseries.translations_branch = self.factory.makeBranch(
            owner=branch_owner)
        exporter._exportToBranch = FakeMethod(failure=NotBranchError("Ow"))

        self.becomeDbUser('translationstobranch')

        exporter._handleUnpushedBranch(productseries)

        # _handleUnpushedBranch completes successfully.  There are no
        # database changes still pending in the ORM that are going to
        # fail either.
        transaction.commit()

    def test_sets_bzr_id(self):
        # The script commits to the branch under a user id that mentions
        # the automatic translations exports as well as the Launchpad
        # name of the branch owner.
        self.useBzrBranches(direct_database=False)
        exporter = ExportTranslationsToBranch(test_args=[])
        branch, tree = self.create_branch_and_tree()
        committer = exporter._makeDirectBranchCommit(branch)
        committer.unlock()
        self.assertEqual(
            "Launchpad Translations on behalf of %s" % branch.owner.name,
            committer.getBzrCommitterID())

    def test_findChangedPOFiles(self):
        # Returns all POFiles changed in a productseries after a certain
        # date.
        date_in_the_past = (
            datetime.datetime.now(pytz.UTC) - datetime.timedelta(1))
        pofile = self.factory.makePOFile()

        exporter = ExportTranslationsToBranch(test_args=[])
        self.assertEquals(
            [pofile],
            list(exporter._findChangedPOFiles(
                pofile.potemplate.productseries,
                changed_since=date_in_the_past)))

    def test_findChangedPOFiles_all(self):
        # If changed_since date is passed in as None, all POFiles are
        # returned.
        pofile = self.factory.makePOFile()
        exporter = ExportTranslationsToBranch(test_args=[])
        self.assertEquals(
            [pofile],
            list(exporter._findChangedPOFiles(
                pofile.potemplate.productseries, changed_since=None)))

    def test_findChangedPOFiles_unchanged(self):
        # If a POFile has been changed before changed_since date,
        # it is not returned.
        pofile = self.factory.makePOFile()
        date_in_the_future = (
            datetime.datetime.now(pytz.UTC) + datetime.timedelta(1))

        exporter = ExportTranslationsToBranch(test_args=[])
        self.assertEquals(
            [],
            list(exporter._findChangedPOFiles(
                pofile.potemplate.productseries,
                date_in_the_future)))

    def test_findChangedPOFiles_unchanged_template_changed(self):
        # If a POFile has been changed before changed_since date,
        # and template has been updated after it, POFile is still
        # considered changed and thus returned.
        pofile = self.factory.makePOFile()
        date_in_the_future = (
            datetime.datetime.now(pytz.UTC) + datetime.timedelta(1))
        date_in_the_far_future = (
            datetime.datetime.now(pytz.UTC) + datetime.timedelta(2))
        pofile.potemplate.date_last_updated = date_in_the_far_future

        exporter = ExportTranslationsToBranch(test_args=[])
        self.assertEquals(
            [pofile],
            list(exporter._findChangedPOFiles(
                pofile.potemplate.productseries,
                date_in_the_future)))
