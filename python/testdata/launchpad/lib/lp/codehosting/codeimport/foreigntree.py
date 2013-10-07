# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Support for CVS and Subversion branches."""

__metaclass__ = type
__all__ = ['CVSWorkingTree', 'SubversionWorkingTree']

import os

import CVS
import subvertpy
import subvertpy.client
import subvertpy.ra


class CVSWorkingTree:
    """Represents a CVS working tree."""

    def __init__(self, cvs_root, cvs_module, local_path):
        """Construct a CVSWorkingTree.

        :param cvs_root: The root of the CVS repository.
        :param cvs_module: The module in the CVS repository.
        :param local_path: The local path to check the working tree out to.
        """
        self.root = cvs_root
        self.module = cvs_module
        self.local_path = os.path.abspath(local_path)

    def checkout(self):
        repository = CVS.Repository(self.root, None)
        repository.get(self.module, self.local_path)

    def commit(self):
        tree = CVS.tree(self.local_path)
        tree.commit(log='Log message')

    def update(self):
        tree = CVS.tree(self.local_path)
        tree.update()


class SubversionWorkingTree:
    """Represents a Subversion working tree."""

    def __init__(self, url, path):
        """Construct a `SubversionWorkingTree`.

        :param url: The URL of the branch for this tree.
        :param path: The path to the working tree.
        """
        self.remote_url = url
        self.local_path = path

    def _get_client(self):
        username_provider = subvertpy.ra.get_username_provider()
        auth = subvertpy.ra.Auth([username_provider])
        auth.set_parameter(subvertpy.AUTH_PARAM_DEFAULT_USERNAME, "lptest2")
        return subvertpy.client.Client(auth=auth)

    def checkout(self):
        client = self._get_client()
        client.checkout(
            self.remote_url, self.local_path, rev="HEAD",
            ignore_externals=True)

    def commit(self):
        client = self._get_client()
        client.log_msg_func = lambda c: 'Log message'
        client.commit([self.local_path], recurse=True)

    def update(self):
        client = self._get_client()
        client.update(self.local_path, "HEAD", True, True)
