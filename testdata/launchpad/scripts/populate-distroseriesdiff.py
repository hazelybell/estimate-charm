#!/usr/bin/python -S
#
# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

__metaclass__ = type

import _pythonpath

from lp.registry.scripts.populate_distroseriesdiff import (
    PopulateDistroSeriesDiff,
    )


if __name__ == '__main__':
    PopulateDistroSeriesDiff('populate-distroseriesdiff').run()
