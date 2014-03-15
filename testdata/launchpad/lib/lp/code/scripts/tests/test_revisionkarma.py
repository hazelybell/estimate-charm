# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for the cron script that updates revision karma."""

__metaclass__ = type

from storm.store import Store
import transaction

from lp.code.scripts.revisionkarma import RevisionKarmaAllocator
from lp.registry.model.karma import Karma
from lp.services.config import config
from lp.testing import TestCaseWithFactory
from lp.testing.dbuser import switch_dbuser
from lp.testing.layers import LaunchpadZopelessLayer


class TestRevisionKarma(TestCaseWithFactory):
    """Test the `getBranch` method of the revision."""

    layer = LaunchpadZopelessLayer

    def runScript(self):
        transaction.commit()
        switch_dbuser(config.revisionkarma.dbuser)
        script = RevisionKarmaAllocator(
            'test', config.revisionkarma.dbuser, ['-q'])
        script.main()

    def assertKarmaEvent(self, person, product, count):
        # Make sure the count of karma events matches the script iteration
        # over revision.allocateKarma()
        instance = person or product
        result = Store.of(instance).find(
            Karma,
            Karma.person == person,
            Karma.product == product)
        self.assertEqual(count, result.count())

    def test_branch_allocated_karma(self):
        # Revision authors that are Lp users are awarded karma for non-junk
        # branches.
        author = self.factory.makePerson()
        rev = self.factory.makeRevision(author=author.preferredemail.email)
        branch = self.factory.makeBranch()
        branch.createBranchRevision(1, rev)
        self.assertTrue(rev.karma_allocated)
        self.assertKarmaEvent(author, branch.product, 1)

    def test_junk_branch_not_allocated_karma(self):
        # Revision authors do not get karma for junk branches.
        author = self.factory.makePerson()
        rev = self.factory.makeRevision(author=author.preferredemail.email)
        branch = self.factory.makePersonalBranch()
        branch.createBranchRevision(1, rev)
        self.assertTrue(rev.karma_allocated)
        self.assertKarmaEvent(author, branch.product, 0)

    def test_unknown_revision_author_not_allocated_karma(self):
        # Karma is not allocated when the revision author is not an Lp user.
        email = self.factory.getUniqueEmailAddress()
        rev = self.factory.makeRevision(author=email)
        branch = self.factory.makeAnyBranch()
        branch.createBranchRevision(1, rev)
        self.assertTrue(rev.karma_allocated)
        self.assertKarmaEvent(rev.revision_author.person, branch.product, 0)
