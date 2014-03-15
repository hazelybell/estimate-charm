YUI.add('lp.testing.tests.test_yuixhr_fixture_facet', function (Y) {
var serverfixture = Y.lp.testing.serverfixture;

/**
 * Test how the yuixhr server fixture handles specified facets.
 */
var tests = Y.namespace('lp.testing.tests.test_yuixhr_fixture_facet');
tests.suite = new Y.Test.Suite('lp.testing.yuixhr facet Tests');
tests.suite.add(new Y.Test.Case({
  name: 'Serverfixture facet tests',

  tearDown: function() {
    serverfixture.teardown(this);
  },

  test_facet_was_honored: function() {
    Y.Assert.areEqual('bugs.launchpad.dev', Y.config.doc.location.hostname);
  }
}));

}, '0.1', {
    requires: ['test', 'lp.testing.serverfixture']
});
