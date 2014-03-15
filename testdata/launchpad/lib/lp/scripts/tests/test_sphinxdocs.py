# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for our Sphinx documentation."""

__metaclass__ = type

import os

import sphinx
from testtools.content import text_content

from lp.services.config import config
from lp.services.utils import run_capturing_output
from lp.testing import TestCase


class TestSphinxDocumentation(TestCase):
    """Is our Sphinx documentation building correctly?"""

    def test_docs_build_without_error(self):
        # The Sphinx documentation must build without errors or warnings.
        #
        # Note that the documents are built on devpad.canonical.com in a
        # cronscript that runs 'make -C doc html' in the Launchpad tree.  This
        # test assumes that make command devolves into 'sphinx-build ...',
        # because running make commands from tests seems distasteful.
        output_dir = self.makeTemporaryDirectory()
        doc_dir = os.path.join(config.root, 'doc')
        returncode, stdout, stderr = run_capturing_output(
            sphinx.main,
            ['sphinx-build', '-d', '%s/doctrees' % output_dir,
             '-aNqW', doc_dir, '%s/html' % output_dir])
        self.addDetail('stdout', text_content(stdout))
        self.addDetail('stderr', text_content(stderr))
        self.assertEqual(0, returncode)
