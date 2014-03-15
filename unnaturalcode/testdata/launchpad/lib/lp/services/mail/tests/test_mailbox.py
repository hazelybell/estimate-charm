# Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for mail boxes."""

__metaclass__ = type

import os
from shutil import rmtree
import tempfile

from lp.services.mail.mailbox import (
    DirectoryMailBox,
    IMailBox,
    )
from lp.testing import (
    TestCase,
    verifyObject,
    )


class TestDirectoryMailBox(TestCase):

    def setUp(self):
        super(TestDirectoryMailBox, self).setUp()
        # Create a temp directory.
        self.email_dir = tempfile.mkdtemp()
        self.addCleanup(rmtree, self.email_dir)

    def test_verify_interface(self):
        # Make sure that the object actually implements the interface.
        box = DirectoryMailBox(self.email_dir)
        verifyObject(IMailBox, box)

    def test_initially_empty(self):
        # Since the new directory has no files, the box is empty.
        box = DirectoryMailBox(self.email_dir)
        self.assertEqual(0, len(list(box.items())))

    def _add_mailfile(self, filename, contents=None):
        # Create a file in the email_dir with the specified contents.
        f = open(os.path.join(self.email_dir, filename), 'w')
        if contents:
            f.write(contents)
        f.close()

    def test_items(self):
        # The items generator provides  the filename and content.
        self._add_mailfile('foo', 'This is the content')
        box = DirectoryMailBox(self.email_dir)
        [mail] = list(box.items())
        self.assertEqual('foo', os.path.basename(mail[0]))
        self.assertEqual('This is the content', mail[1])

    def test_delete(self):
        # Deleting the item removes the file from the mail dir.
        self._add_mailfile('foo', 'This is the content')
        self._add_mailfile('bar', 'More content')
        box = DirectoryMailBox(self.email_dir)
        box.delete(os.path.join(self.email_dir, 'foo'))
        items = list(box.items())
        self.assertEqual(1, len(items))

    def test_deleting_while_iterating(self):
        # Deleting while iterating through should be fine.
        self._add_mailfile('foo', 'This is the content')
        self._add_mailfile('bar', 'More content')
        self._add_mailfile('baz', 'More content')
        box = DirectoryMailBox(self.email_dir)
        for id, content in box.items():
            box.delete(id)
        self.assertEqual(0, len(list(box.items())))
