# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""looptuner.py tests.

These are the edge test cases that don't belong in the doctest.
"""

__metaclass__ = type

from cStringIO import StringIO

from zope.interface import implements

from lp.services.log.logger import FakeLogger
from lp.services.looptuner import (
    ITunableLoop,
    LoopTuner,
    )
from lp.testing import TestCase
from lp.testing.layers import BaseLayer


class MainException(Exception):
    """Exception raised from the main body of an ITunableLoop."""


class CleanupException(Exception):
    """Exception raised from the cleanup method of an ITunableLoop."""


class IsDoneException(Exception):
    """Exception raised from the isDone method of an ITunableLoop."""


class FailingLoop:
    implements(ITunableLoop)

    def __init__(
        self, fail_main=False, fail_cleanup=False):
        self.fail_main = fail_main
        self.fail_cleanup = fail_cleanup

    _done = False  # Set by __call__ to signal termination

    def isDone(self):
        return self._done

    def __call__(self, chunk_size):
        self._done = True
        if self.fail_main:
            raise MainException()

    def cleanUp(self):
        if self.fail_cleanup:
            raise CleanupException()


class TestSomething(TestCase):
    layer = BaseLayer

    def test_cleanup_exception_on_success(self):
        """Main task succeeded but cleanup failed.

        Exception from cleanup raised.
        """
        log_file = StringIO()
        loop = FailingLoop(fail_cleanup=True)
        tuner = LoopTuner(loop, 5, log=FakeLogger(log_file))
        self.assertRaises(CleanupException, tuner.run)
        self.assertEqual(log_file.getvalue(), "")

    def test_cleanup_exception_on_failure(self):
        """Main task failed and cleanup also failed.

        Exception from cleanup is logged.
        Original exception from main task is raised.
        """
        log_file = StringIO()
        loop = FailingLoop(fail_main=True, fail_cleanup=True)
        tuner = LoopTuner(loop, 5, log=FakeLogger(log_file))
        self.assertRaises(MainException, tuner.run)
        self.assertEqual(
            log_file.getvalue().strip(),
            "ERROR Unhandled exception in cleanUp")
