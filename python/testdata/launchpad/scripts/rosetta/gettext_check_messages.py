#!/usr/bin/python -S
#
# Copyright 2009 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Run gettext consistency checks on messages in the database.

Incoming translations are always run through gettext to check for
errors, mainly with conversion specifiers in format strings.  But under
certain circumstances (e.g. bug 317578) it's possible to have messages
in the database that would fail that check in their present form.  Or a
check may be added in later versions of gettext.

This script checks messages against gettext again.  Ones that fail are
disabled; if there is an imported alternative that does pass, it is
enabled instead.
"""

__metaclass__ = type

import _pythonpath

from lp.translations.scripts.gettext_check_messages import (
    GettextCheckMessages,
    )


if __name__ == '__main__':
    GettextCheckMessages('gettext-check-messages').lock_and_run()
