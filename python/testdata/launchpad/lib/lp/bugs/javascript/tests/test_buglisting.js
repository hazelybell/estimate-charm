YUI.add('lp.bugs.buglisting.test', function (Y) {
    var module = Y.lp.bugs.buglisting;

    var tests = Y.namespace('lp.bugs.buglisting.test');
    tests.suite = new Y.Test.Suite('Buglisting Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'bugs.buglisting_tests',

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.bugs.buglisting,
                "Could not locate the lp.bugs.buglisting module");
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'ListingNavigator',
        setUp: function() {
            this.target = Y.Node.create('<div></div>').set(
                'id', 'client-listing');
            Y.one('body').appendChild(this.target);
        },
        tearDown: function() {
            this.target.remove();
            delete this.target;
            Y.lp.testing.helpers.reset_history();
        },
        test_sets_search_params: function() {
            // search_parms includes all query values that don't control
            // batching
            var navigator = new module.BugListingNavigator({
                current_url: 'http://yahoo.com?foo=bar&start=1&memo=2&' +
                    'direction=3&orderby=4',
                cache: {next: null, prev: null},
                target: this.target
            });
            Y.lp.testing.assert.assert_equal_structure(
                {foo: 'bar'}, navigator.get('search_params'));
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'from_page tests',
        setUp: function() {
            window.LP = {
                cache: {
                    current_batch: {},
                    next: null,
                    prev: null,
                    related_features: {
                        'bugs.dynamic_bug_listings.pre_fetch': {value: 'on'}
                    }
                }
            };
        },
        getPreviousLink: function() {
            return Y.one('.previous').get('href');
        },
        test_from_page_with_client: function() {
            Y.one('#fixture').setContent(
                '<div id="bugs-table-listing">' +
                    '<a class="previous" href="http://example.org/">' +
                    'PreVious</a>' +
                    '<div id="client-listing"></div>' +
                '</div>');
            Y.Assert.areSame('http://example.org/', this.getPreviousLink());
            module.BugListingNavigator.from_page();
            Y.Assert.areNotSame('http://example.org/', this.getPreviousLink());
        },
        test_from_page_with_no_client: function() {
            Y.one('#fixture').setContent('');
            var navigator = module.BugListingNavigator.from_page();
            Y.Assert.isNull(navigator);
        },
        tearDown: function() {
            Y.one('#fixture').setContent("");
            delete window.LP;
        }
    }));


}, '0.1', {
    'requires': ['test', 'lp.testing.helpers', 'test-console',
        'lp.bugs.buglisting', 'lp.testing.mockio', 'lp.testing.assert',
        'lp.app.inlinehelp']
});
