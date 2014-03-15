# Copyright 2010 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""An example cronscript. If it runs, it returns 42 as its return code."""

__metaclass__ = type
__all__ = []

import sys

from lp.services.scripts.base import (
    LaunchpadCronScript,
    SilentLaunchpadScriptFailure,
    )


class Script(LaunchpadCronScript):
    def main(self):
        if self.name == 'example-cronscript-enabled':
            raise SilentLaunchpadScriptFailure(42)
        else:
            # Raise a non-standard error code, as if the
            # script was invoked as disabled the main()
            # method should never be invoked.
            raise SilentLaunchpadScriptFailure(999)

if __name__ == '__main__':
    if sys.argv[-1] == 'enabled':
        name = 'example-cronscript-enabled'
    else:
        name = 'example-cronscript-disabled'
    script = Script(name)
    script.lock_and_run()
