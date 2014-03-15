# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Testing rosetta-branches cronscript.

This would normally be done in a doctest but TestCaseWithFactory has all the
provisions to handle Bazaar branches.
"""

__metaclass__ = type

from bzrlib.revision import NULL_REVISION
import transaction
from zope.component import getUtility

from lp.code.model.branchjob import RosettaUploadJob
from lp.services.osutils import override_environ
from lp.services.scripts.tests import run_script
from lp.testing import TestCaseWithFactory
from lp.testing.layers import ZopelessAppServerLayer
from lp.translations.enums import RosettaImportStatus
from lp.translations.interfaces.translationimportqueue import (
    ITranslationImportQueue,
    )
from lp.translations.interfaces.translations import (
    TranslationsBranchImportMode,
    )


class TestRosettaBranchesScript(TestCaseWithFactory):
    """Testing the rosetta-bazaar cronscript."""

    layer = ZopelessAppServerLayer

    def _clear_import_queue(self):
        # The testdata has entries in the queue.
        queue = getUtility(ITranslationImportQueue)
        entries = list(queue)
        for entry in entries:
            queue.remove(entry)

    def _setup_series_branch(self, pot_path):
        self.useBzrBranches()
        pot_content = self.factory.getUniqueString()
        branch, tree = self.create_branch_and_tree()
        tree.bzrdir.root_transport.put_bytes(pot_path, pot_content)
        tree.add(pot_path)
        # XXX: AaronBentley 2010-08-06 bug=614404: a bzr username is
        # required to generate the revision-id.
        with override_environ(BZR_EMAIL='me@example.com'):
            revision_id = tree.commit("first commit")
        branch.last_scanned_id = revision_id
        branch.last_mirrored_id = revision_id
        series = self.factory.makeProductSeries()
        series.branch = branch
        series.translations_autoimport_mode = (
            TranslationsBranchImportMode.IMPORT_TEMPLATES)
        return branch

    def test_rosetta_branches_script(self):
        # If a job exists it will be executed and the template file will
        # be put into the import queue with status "Approved".
        self._clear_import_queue()
        pot_path = self.factory.getUniqueString() + ".pot"
        branch = self._setup_series_branch(pot_path)
        RosettaUploadJob.create(branch, NULL_REVISION)
        transaction.commit()

        return_code, stdout, stderr = run_script(
            'cronscripts/process-job-source.py', ['IRosettaUploadJobSource'])
        self.assertEqual(0, return_code)

        queue = getUtility(ITranslationImportQueue)
        self.assertEqual(1, queue.countEntries())
        entry = list(queue)[0]
        self.assertEqual(RosettaImportStatus.APPROVED, entry.status)
        self.assertEqual(pot_path, entry.path)
