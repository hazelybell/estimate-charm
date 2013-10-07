# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Tests for lp.services.osutils."""

__metaclass__ = type

import errno
import os
import socket
import tempfile

from testtools.matchers import FileContains

from lp.services.osutils import (
    ensure_directory_exists,
    open_for_writing,
    remove_tree,
    write_file,
    )
from lp.testing import TestCase


class TestRemoveTree(TestCase):
    """Tests for remove_tree."""

    def test_removes_directory(self):
        # remove_tree deletes the directory.
        directory = tempfile.mkdtemp()
        remove_tree(directory)
        self.assertFalse(os.path.isdir(directory))
        self.assertFalse(os.path.exists(directory))

    def test_on_nonexistent_path_passes_silently(self):
        # remove_tree simply does nothing when called on a non-existent path.
        directory = tempfile.mkdtemp()
        nonexistent_tree = os.path.join(directory, 'foo')
        remove_tree(nonexistent_tree)
        self.assertFalse(os.path.isdir(nonexistent_tree))
        self.assertFalse(os.path.exists(nonexistent_tree))

    def test_raises_on_file(self):
        # If remove_tree is pased a file, it raises an OSError.
        directory = tempfile.mkdtemp()
        filename = os.path.join(directory, 'foo')
        fd = open(filename, 'w')
        fd.write('data')
        fd.close()
        self.assertRaises(OSError, remove_tree, filename)


class TestEnsureDirectoryExists(TestCase):
    """Tests for 'ensure_directory_exists'."""

    def test_directory_exists(self):
        directory = self.makeTemporaryDirectory()
        self.assertFalse(ensure_directory_exists(directory))

    def test_directory_doesnt_exist(self):
        directory = os.path.join(self.makeTemporaryDirectory(), 'foo/bar/baz')
        self.assertTrue(ensure_directory_exists(directory))
        self.assertTrue(os.path.isdir(directory))


class TestOpenForWriting(TestCase):
    """Tests for 'open_for_writing'."""

    def test_opens_for_writing(self):
        # open_for_writing opens a file for, umm, writing.
        directory = self.makeTemporaryDirectory()
        filename = os.path.join(directory, 'foo')
        fp = open_for_writing(filename, 'w')
        fp.write("Hello world!\n")
        fp.close()
        self.assertEqual("Hello world!\n", open(filename).read())

    def test_opens_for_writing_append(self):
        # open_for_writing can also open to append.
        directory = self.makeTemporaryDirectory()
        filename = os.path.join(directory, 'foo')
        fp = open_for_writing(filename, 'w')
        fp.write("Hello world!\n")
        fp.close()
        fp = open_for_writing(filename, 'a')
        fp.write("Next line\n")
        fp.close()
        self.assertEqual("Hello world!\nNext line\n", open(filename).read())

    def test_even_if_directory_doesnt_exist(self):
        # open_for_writing will open a file for writing even if the directory
        # doesn't exist.
        directory = self.makeTemporaryDirectory()
        filename = os.path.join(directory, 'foo', 'bar', 'baz', 'filename')
        fp = open_for_writing(filename, 'w')
        fp.write("Hello world!\n")
        fp.close()
        self.assertEqual("Hello world!\n", open(filename).read())


class TestWriteFile(TestCase):

    def test_write_file(self):
        directory = self.makeTemporaryDirectory()
        filename = os.path.join(directory, 'filename')
        content = self.getUniqueString()
        write_file(filename, content)
        self.assertThat(filename, FileContains(content))
