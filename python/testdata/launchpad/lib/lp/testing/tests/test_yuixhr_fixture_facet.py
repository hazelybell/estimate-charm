# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""Test the ability to specify a facet for the yuixhr tests.
"""

__metaclass__ = type
__all__ = []

from lp.testing.yuixhr import make_suite


def test_suite():
    # You can specify a facet, as found in the vhost.* names in
    # [root]/configs/testrunner-appserver/launchpad-lazr.conf .  This
    # can be convenient for code that must be run within a given subdomain.
    return make_suite(__name__, 'bugs')
