#!/usr/bin/python -S
#
# Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""It provides easy integration of other scripts without database access.

   It should provide an easy way to retrieve current information from
   Launchpad when using plain shell scripts, for example:

   * SUPPORTED distroseries names:
       `./lp-query-distro.py -d ubuntu supported`

   Standard Output will carry the successfully executed information and
   exit_code will be ZERO.
   In case of failure, exit_code will be different than ZERO and Standard
   Error will contain debug information.
   """

import _pythonpath

from lp.soyuz.scripts.querydistro import LpQueryDistro


if __name__ == '__main__':
    script = LpQueryDistro('lp-query-distro', dbuser='ro')
    script.run()
