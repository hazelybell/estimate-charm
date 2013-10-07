YUI.add('lp.testing.tests.test_standard_yuixhr_test_template', function (Y) {

// This is one-half of an example yuixhr test.  The other half of a
// test like this is a file of the same name but with a .py
// extension.  It holds the fixtures that this file uses for
// application setup and teardown.  It also helps the Launchpad
// testrunner know how to run these tests.  The actual tests are
// written here, in Javascript. The YUI namespace must match the Python
// module path.

// These tests are expensive to run.  Keep them to a minimum,
// preferring pure JS unit tests and pure Python unit tests.

var serverfixture = Y.lp.testing.serverfixture;

// TODO: change this explanation string.
/**
 * Test important things...
 */
var tests = Y.namespace('lp.testing.tests.test_standard_yuixhr_test_template');
// TODO: Change this string to match what you are doing.
tests.suite = new Y.Test.Suite('lp.testing.yuixhr Tests');
tests.suite.add(new Y.Test.Case({
    // TODO: change this name.
    name: 'Example tests',

    tearDown: function() {
        // Always do this.
        serverfixture.teardown(this);
    },

    // Your tests go here.
    test_example: function() {
        // In this example, we care about the return value of the setup.
        // Sometimes, you won't.
        var data = serverfixture.setup(this, 'example');
        // Now presumably you would test something, maybe like this.
        var response = Y.io(
            data.product.self_link,
            {sync: true}
            );
        Y.Assert.areEqual(200, response.status);
    }
}));

}, '0.1', {
    requires: ['test', 'lp.testing.serverfixture']
});
