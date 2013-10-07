# Copyright 2011 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""These are yui appserver fixtures for the yui appserver test code's tests.
"""

__metaclass__ = type
__all__ = []

from zope.security.proxy import removeSecurityProxy

from lp.testing import login_person
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.yuixhr import (
    login_as_person,
    make_suite,
    setup,
    )

# The following are the fixtures needed by the tests.

# We use this variable for test results.
_received = []


@setup
def baseline(request, data):
    data['hello'] = 'world'


@baseline.add_cleanup
def baseline(request, data):
    global _received
    _received.append(('baseline', request, data))


@setup
def second(request, data):
    data['second'] = 'here'
@second.add_cleanup
def second(request, data):
    global _received
    _received.append(('second', request, data))

test_value = None


@setup
def faux_database_thing(request, data):
    global test_value
    data['previous_value'] = test_value
    test_value = None
@faux_database_thing.add_cleanup
def faux_database_thing(request, data):
    global test_value
    test_value = 'teardown was called'


@setup
def show_teardown_value(request, data):
    data['setup_data'] = 'Hello world'
@show_teardown_value.add_cleanup
def show_teardown_value(request, data):
    global test_value
    test_value = data

factory = LaunchpadObjectFactory()


@setup
def make_product(request, data):
    data['product'] = factory.makeProduct()


@setup
def make_product_loggedin(request, data):
    data['person'] = factory.makeAdministrator()
    login_person(data['person'])
    data['product'] = factory.makeProduct(owner=data['person'])


@setup
def naughty_make_product(request, data):
    data['product'] = removeSecurityProxy(factory.makeProduct())


@setup
def teardown_will_fail(request, data):
    pass
@teardown_will_fail.add_cleanup
def teardown_will_fail(request, data):
    raise RuntimeError('rutebegas')


@setup
def login_as_admin(request, data):
    data['user'] = factory.makeAdministrator()
    login_as_person(data['user'])


def test_suite():
    return make_suite(__name__)
