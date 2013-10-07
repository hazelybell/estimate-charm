YUI.add('lp.testing.tests.test_yuixhr_fixture', function (Y) {
var module = Y.lp.testing.serverfixture;

/**
 * Test setup and teardown of yuixhr fixtures, and the asociated JS module.
 */
var tests = Y.namespace('lp.testing.tests.test_yuixhr_fixture');
tests.suite = new Y.Test.Suite('lp.testing.yuixhr Tests');
tests.suite.add(new Y.Test.Case({

    name: 'Fixture setup and teardown tests',

    tearDown: function() {
        delete this._lp_fixture_setups;
        delete this._lp_fixture_data;
    },

    _should: {
        error: {
            test_bad_http_call_raises_error: true,
            test_bad_http_teardown_raises_error: true
        }
    },

    test_simple_setup: function() {
        var data = module.setup(this, 'baseline');
        Y.ArrayAssert.itemsAreEqual(['baseline'], this._lp_fixture_setups);
        Y.ObjectAssert.areEqual({'hello': 'world'}, data);
        Y.ObjectAssert.areEqual({'hello': 'world'}, this._lp_fixture_data);
        module.teardown(this); // Just for cleanliness, not for testing.
    },

    test_setup_with_multiple_fixtures: function() {
        var data = module.setup(this, 'baseline', 'second');
        Y.ArrayAssert.itemsAreEqual(
            ['baseline', 'second'], this._lp_fixture_setups);
        Y.ObjectAssert.areEqual({'hello': 'world', 'second': 'here'}, data);
        Y.ObjectAssert.areEqual(
            {'hello': 'world', 'second': 'here'}, this._lp_fixture_data);
        module.teardown(this); // Just for cleanliness, not for testing.
    },

    test_multiple_setup_calls: function() {
        var data = module.setup(this, 'baseline');
        var second_data = module.setup(this, 'second');
        Y.ArrayAssert.itemsAreEqual(
            ['baseline', 'second'], this._lp_fixture_setups);
        Y.ObjectAssert.areEqual({'hello': 'world'}, data);
        Y.ObjectAssert.areEqual({'second': 'here'}, second_data);
        Y.ObjectAssert.areEqual(
            {'hello': 'world', 'second': 'here'}, this._lp_fixture_data);
        module.teardown(this); // Just for cleanliness, not for testing.
    },

    test_teardown_clears_attributes: function() {
        var data = module.setup(this, 'baseline');
        module.teardown(this);
        Y.Assert.isUndefined(this._lp_fixture_setups);
        Y.Assert.isUndefined(this._lp_fixture_data);
    },

    test_bad_http_call_raises_error: function() {
        module.setup(this, 'does not exist');
    },

    test_bad_http_call_shows_traceback: function() {
        try {module.setup(this, 'does not exist');}
        catch (err) {
            Y.Assert.areEqual('Traceback (most recent call last)',
                              err.message.substring(0, 33));
        }
    },

    test_bad_http_teardown_raises_error: function() {
        module.setup(this, 'teardown_will_fail');
        module.teardown(this);
    },

    test_bad_http_teardown_shows_traceback: function() {
        module.setup(this, 'teardown_will_fail');
        try {module.teardown(this);}
        catch (err) {
            Y.Assert.areEqual('Traceback (most recent call last)',
                              err.message.substring(0, 33));
        }
    },

    test_setup_called_twice_with_same_fixture: function() {
        // This is arguably not desirable, but it is the way it works now.
        var data = module.setup(this, 'baseline');
        var second_data = module.setup(this, 'baseline');
        Y.ArrayAssert.itemsAreEqual(
            ['baseline', 'baseline'], this._lp_fixture_setups);
        Y.ObjectAssert.areEqual({'hello': 'world'}, data);
        Y.ObjectAssert.areEqual({'hello': 'world'}, second_data);
        Y.ObjectAssert.areEqual(
            {'hello': 'world'}, this._lp_fixture_data);
        module.teardown(this); // Just for cleanliness, not for testing.
    },

    test_teardown: function() {
        module.setup(this, 'faux_database_thing');
        module.teardown(this);
        var data = module.setup(this, 'faux_database_thing');
        Y.ObjectAssert.areEqual(
            {'previous_value': 'teardown was called'}, data);
    },

    test_teardown_receives_data_from_setup: function() {
        module.setup(this, 'show_teardown_value');
        module.teardown(this);
        var data = module.setup(this, 'faux_database_thing');
        Y.ObjectAssert.areEqual(
            {'setup_data': 'Hello world'}, data.previous_value);
    },

    test_teardown_resets_database: function() {
        var data = module.setup(this, 'make_product');
        var response = Y.io(
            data.product.self_link,
            {sync: true}
            );
        Y.Assert.areEqual(200, response.status);
        module.teardown(this);
        response = Y.io(
            data.product.self_link,
            {sync: true}
            );
        Y.Assert.areEqual(404, response.status);
    },

    test_login_works: function() {
        // Make sure the session cookie is cleared out at start of test.
        Y.Cookie.remove('launchpad_tests');
        // Make a product
        var data = module.setup(this, 'make_product');
        // We can't see this because only Launchpad and Registry admins can.
        Y.Assert.areEqual(
            'tag:launchpad.net:2008:redacted', data.product.project_reviewed);
        // Login as a Launchpad admin.
        module.setup(this, 'login_as_admin');
        // The cookie is HttpOnly so we can't check it, but we can now
        // see things that only a Launchpad admin can see.
        var response = Y.io(
            data.product.self_link,
            {sync: true, headers: {Accept: 'application/json'}}
            );
        var result = Y.JSON.parse(response.responseText);
        Y.Assert.areEqual(false, result.project_reviewed);
        module.teardown(this);
    },

    test_no_setup_can_still_teardown: function() {
        module.teardown(this);
    }
}));

}, '0.1', {
    requires: ['test', 'json', 'cookie', 'lp.testing.serverfixture']
});
