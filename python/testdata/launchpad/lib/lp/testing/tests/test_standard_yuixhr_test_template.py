# Copyright 2012 Canonical Ltd.  This software is licensed under the
# GNU Affero General Public License version 3 (see the file LICENSE).

"""{Describe your test suite here}.
"""

__metaclass__ = type
__all__ = []

from lp.testing import person_logged_in
from lp.testing.factory import LaunchpadObjectFactory
from lp.testing.yuixhr import (
    login_as_person,
    make_suite,
    setup,
    )

# This is one half of a YUI app test.  The other half is a .js test of
# exactly the same name as your Python file, just with different file
# extensions.

# This file holds fixtures that your Javascript tests call to prepare
# for tests.  It also holds two lines of boiler plate at the bottom of
# the file that let the test runner know how to run these tests.

# You can run these yui app tests interactively.  This can help with
# construction and debugging.  To do so, start Launchpad with "make
# run-testapp" and go to
# http://launchpad.dev:8085/+yuitest/PATH/TO/THIS/FILE/WITHOUT/EXTENSION
# . For example,
# http://launchpad.dev:8085/+yuitest/lp/testing/tests/test_yuixhr_fixture
# will run the tests in
# {launchpad}/lib/lp/testing/tests/test_yui_fixture[.py|.js].

# Put your Python test fixtures here, just like these examples below.


@setup
def example(request, data):
    # This is a test fixture.  You will want to write your own, and
    # delete this one.  See the parallel
    # standard_yuixhr_test_template.js to see how to call fixtures
    # from your Javascript tests.
    #
    # A test fixture prepares the application for your test.  You can
    # do whatever you need here, including creating objects with an
    # object factory and logging the browser in as a given user.
    # You'll see an example below.
    #
    # Test fixtures can also return information back to your test.
    # Simply stuff the information you want into the "data" dict.  It
    # will be converted into JSON and sent back to the Javascript
    # caller.  Even Launchpad objects are converted, using the
    # standard lazr.restful mechanism.  This can be useful in several
    # ways.  Here are three examples.
    #
    # First, you can communicate information about the objects you
    # have created in the setup so that the Javascript knows what URLs
    # to use.  The code in this function has an example of this,
    # below.
    #
    # Second, you can return information about verifying some aspect
    # of the database state, so your Javascript test can easily assert
    # some fact that is not usually easily exposed to it.
    #
    # Finally, you can stash information that your teardown might
    # need.  You shouldn't usually need to clean anything up, because
    # the database and librarian are reset after every test, but if
    # you do set something up that needs an explicit teardown, you can
    # stash JSON-serializable information in "data" that the teardown
    # can use to know what to clean up.
    #
    # You can compose these setups and teardowns as well, using .extend.
    # There is a small example of this as well, below.
    #
    # As a full example, we will create an administrator and another
    # person; we will have the administrator create an object; we will
    # log the browser in as the other person; and we will stash
    # information about the object and the two people in the data
    # object.
    #
    # Again, this is a semi-random example.  Rip this whole fixture
    # out, and write the ones that you need.
    factory = LaunchpadObjectFactory()
    data['admin'] = factory.makeAdministrator()
    data['user'] = factory.makePerson()
    with person_logged_in(data['admin']):
        data['product'] = factory.makeProduct(owner=data['admin'])
    # This logs the browser in as a given person.  You need to use
    # this function for that purpose--the standard lp.testing login
    # functions are insufficient.
    login_as_person(data['user'])
    # Now we've done everything we said we would.  Let's imagine that
    # we had to also write some file to disk that would need to be
    # cleaned up at the end of the test.  We might stash information
    # about that in "data" too.
    data['some random data we might need for cleaning up'] = 'rutebega'
    # Now we are done.  We don't need to return anything, because we
    # have been mutating the "data" dict that was passed in.  (This
    # will become slightly more important if you ever want to use
    # .extend.)
@example.add_cleanup
def example(request, data):
    # This is an example of a cleanup function, which will be called
    # at the end of the test.  You usually won't need one of these,
    # because the database and librarian are automatically reset after
    # every test.  If you don't need it, don't write it!
    #
    # A cleanup function gets the data from the setup, after it has
    # been converted into JSON and back again.  So, in this case, we
    # could look at the clean up data we stashed in our setup if we
    # wanted to, and do something with it.  We don't really need to do
    # anything with it, so we'll just show that the data is still
    # around, and then stop.
    assert (
        data['some random data we might need for cleaning up'] == 'rutebega')

# Sometimes you might have setup and teardown code that can be shared
# within your test suite as part of several larger jobs.  You can use
# "extend" for that if you like.


@example.extend
def extended_example(request, data):
    # We have declared a new fixture named "extended_example", but
    # instead of using "setup" we used the "extend" method of the
    # "example" fixture.  You can think of "example" wrapping
    # "extended_example".  During test setup, the "example" setup will
    # be called first.  Then this function, in "extended_example,"
    # will be called.  During test teardown, the "extended_example"
    # cleanups will be called first, followed by the "example"
    # cleanups.
    #
    # The "data" dict is the same one that was passed to the wrapping
    # fixture.  You can look at it, mutate it, or do what you need.
    # You are also responsible for not overwriting or mangling the
    # dict so that the wrapping fixtures data and/or teardown is
    # compromised.
    #
    # For this example, we will log in as the user and make something.
    factory = LaunchpadObjectFactory()
    with person_logged_in(data['user']):
        data['another_product'] = factory.makeProduct(owner=data['user'])

# That's the end of the example fixtures.

# IMPORTANT!!  These last two lines are boilerplate that let
# Launchpad's testrunner find the associated Javascript tests and run
# them.  You should not have to change them, but you do need to have
# them.  Feel free to delete these comments, though. :-)


def test_suite():
    return make_suite(__name__)
