#!/usr/bin/python -S
#
# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

import _pythonpath

from lp.code.scripts.unscanbranch import UnscanBranchScript


if __name__ == '__main__':
    UnscanBranchScript("unscan-branch", dbuser='branchscanner').run()
