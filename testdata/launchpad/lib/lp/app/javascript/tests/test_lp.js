YUI.add('lp.test', function (Y) {

    var tests = Y.namespace('lp.test');
    tests.suite = new Y.Test.Suite("lp helper tests");

    tests.suite.add(new Y.Test.Case({
        name: 'test_bugs_branches',

        test_get_url_path_with_pillar: function () {
            Y.Assert.areEqual(
                '/fnord', Y.lp.get_url_path('http://launchpad.dev/fnord'));
        },

        test_get_url_path_without_slash: function () {
            Y.Assert.areEqual(
                '/', Y.lp.get_url_path('http://launchpad.dev'));
        },

        test_get_url_path_with_double_slash: function () {
            Y.Assert.areEqual(
                '/fnord', Y.lp.get_url_path('http://launchpad.dev//fnord'));
        }
    }));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console', 'node', 'lp']
});
