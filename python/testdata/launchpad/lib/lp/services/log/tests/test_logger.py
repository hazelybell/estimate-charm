# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for `lp.services.log.logger`."""

__metaclass__ = type

from lp.services.log.logger import BufferLogger
from lp.testing import TestCase


class TestBufferLogger(TestCase):
    """Tests for `BufferLogger`."""

    def test_content(self):
        # The content property returns a `testtools.content.Content` object
        # representing the contents of the logger's buffer.
        logger = BufferLogger()
        logger.info("Hello")
        logger.warn("World")
        self.assertEqual(
            "INFO Hello\nWARNING World\n",
            "".join(logger.content.iter_text()))
