#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Commit translations to translations_branch where requested.

This script needs to be run on the codehosting server, so that it can
access hosted branches.

Besides committing to branches, the script updates Branch records in the
database, to let the branch scanner know that the branches' contents
have been updated.  For the rest, the script talks to the slave store.
"""

__metaclass__ = type
__all__ = []

import _pythonpath

from lp.translations.scripts.translations_to_branch import (
    ExportTranslationsToBranch,
    )


if __name__ == '__main__':
    script = ExportTranslationsToBranch(
        'translations-export-to-branch', dbuser='translationstobranch')
    script.config_name = 'translations_export_to_branch'
    script.lock_and_run()
