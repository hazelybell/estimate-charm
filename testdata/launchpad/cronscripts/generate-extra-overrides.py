#!/usr/bin/python -S
#
# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Generate extra overrides using Germinate."""

import _pythonpath

from lp.archivepublisher.scripts.generate_extra_overrides import (
    GenerateExtraOverrides,
    )


if __name__ == '__main__':
    script = GenerateExtraOverrides(
        "generate-extra-overrides", dbuser='generate_extra_overrides')
    script.lock_and_run()
