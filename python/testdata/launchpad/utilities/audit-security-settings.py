#! /usr/bin/python -S

# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Check that everything is alright in security.cfg

Usage hint:

% utilities/audit-security.py
"""
__metatype__ = type

import _pythonpath

import os

from lp.scripts.utilities.settingsauditor import SettingsAuditor


BRANCH_ROOT = os.path.split(
    os.path.dirname(os.path.abspath(__file__)))[0]
SECURITY_PATH = os.path.join(
    BRANCH_ROOT, 'database', 'schema', 'security.cfg')


def main():
    data = file(SECURITY_PATH).read()
    auditor = SettingsAuditor(data)
    settings = auditor.audit()
    file(SECURITY_PATH, 'w').write(settings)
    print auditor.error_data

if __name__ == '__main__':
    main()
