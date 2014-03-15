# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Inline Help Support.

This package contains a base Help Folder implementation along a ZCML directive
for registering help folders.
"""

__metaclass__ = type
__all__ = [
    'HelpFolder',
    ]

from lp.app.browser.folder import ExportedFolder


class HelpFolder(ExportedFolder):
    """An exported directory containing inline help documentation."""

    export_subdirectories = True
