# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test that no files in the tree has spurious conflicts marker."""

__metaclass__ = type

import os
import subprocess
import unittest


class NoSpuriousConlictsMarkerTest(unittest.TestCase):
    """Check each file in the working tree for spurious conflicts marker."""

    # We do not check for ======= because it might match some
    # old heading style in some doctests.
    CONFLICT_MARKER_RE = r'^\(<<<<<<< TREE\|>>>>>>> MERGE-SOURCE\)$'

    # We could use bzrlib.workingtree for that test, but this cause
    # problems when the system bzr (so the developers' branch) isn't at
    # the same level than the bzrlib included in our tree. Anyway, it's
    # probably faster to use grep anyway.
    def test_noSpuriousConflictsMarker(self):
        """Fail if any spurious conflicts marker are found."""
        root_dir = os.path.join(os.path.dirname(__file__), '../../..')
        shell_command = "cd '%s' && bzr ls --versioned | xargs grep '%s'" % (
                root_dir, self.CONFLICT_MARKER_RE)

        # We need to reset PYTHONPATH here otherwise the bzrlib in our
        # tree will be picked up.
        new_env = dict(os.environ)
        new_env['PYTHONPATH'] = ''
        process = subprocess.Popen(
            shell_command, shell=True, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=new_env)
        out, err = process.communicate()
        self.failIf(len(out), 'Found spurious conflicts marker:\n%s' % out)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(NoSpuriousConlictsMarkerTest))
    return suite


if __name__ == '__main__':
    unittest.main()