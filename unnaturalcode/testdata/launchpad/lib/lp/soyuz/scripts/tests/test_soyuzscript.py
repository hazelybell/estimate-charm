# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the SoyuzScript base class.

We check that the base source and binary lookup methods are working
properly.
"""

import unittest

from lp.services.log.logger import BufferLogger
from lp.soyuz.scripts.ftpmasterbase import SoyuzScript
from lp.testing.layers import LaunchpadZopelessLayer


class TestSoyuzScript(unittest.TestCase):
    """Test the SoyuzScript class."""

    layer = LaunchpadZopelessLayer

    def getSoyuz(self, version=None, component=None, arch=None,
                 suite=None, distribution_name='ubuntu',
                 ppa=None, partner=False, ppa_name='ppa'):
        """Return a SoyuzScript instance.

        Allow tests to use a set of default options and pass an
        inactive logger to SoyuzScript.
        """
        test_args = ['-d', distribution_name, '-y']

        if suite is not None:
            test_args.extend(['-s', suite])

        if version is not None:
            test_args.extend(['-e', version])

        if arch is not None:
            test_args.extend(['-a', arch])

        if component is not None:
            test_args.extend(['-c', component])

        if ppa is not None:
            test_args.extend(['-p', ppa])
            test_args.extend(['--ppa-name', ppa_name])

        if partner:
            test_args.append('-j')

        soyuz = SoyuzScript(name='soyuz-script', test_args=test_args)
        # Store output messages, for future checks.
        soyuz.logger = BufferLogger()
        soyuz.setupLocation()
        return soyuz

    def testFinishProcedure(self):
        """Make sure finishProcedure returns the correct boolean."""
        soyuz = self.getSoyuz()
        soyuz.txn = LaunchpadZopelessLayer.txn
        soyuz.options.confirm_all = True
        self.assertTrue(soyuz.finishProcedure())
        # XXX Julian 2007-11-29 bug=172869:
        # Setting confirm_all to False is pretty untestable because it
        # asks the user for confirmation via raw_input.
        soyuz.options.dryrun = True
        self.assertFalse(soyuz.finishProcedure())
