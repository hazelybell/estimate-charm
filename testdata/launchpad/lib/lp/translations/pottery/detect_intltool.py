# Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Functions to detect if intltool can be used to generate a POT file for the
package in the current directory."""

from contextlib import contextmanager


__metaclass__ = type
__all__ = [
    'is_intltool_structure',
    ]


@contextmanager
def read_lock_tree(tree):
    """Context manager to claim a read lock on a bzr tree."""
    tree.lock_read()
    yield
    tree.unlock()


def is_intltool_structure(tree):
    """Does this source tree look like it's set up for intltool?

    Currently this just checks for the existence of POTFILES.in.

    :param tree: A bzrlib.Tree object to search for the intltool structure.
    :returns: True if signs of an intltool structure were found.
    """
    with read_lock_tree(tree):
        for thedir, files in tree.walkdirs():
            for afile in files:
                file_path, file_name, file_type = afile[:3]
                if file_type != 'file':
                    continue
                if file_name == "POTFILES.in":
                    return True
    return False
