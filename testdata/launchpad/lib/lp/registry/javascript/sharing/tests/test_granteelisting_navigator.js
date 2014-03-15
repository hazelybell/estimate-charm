/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.registry.sharing.granteelisting_navigator.test',
    function (Y) {

    var tests = Y.namespace(
        'lp.registry.sharing.granteelisting_navigator.test');
    tests.suite = new Y.Test.Suite(
        'lp.registry.sharing.granteelisting_navigator Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.registry.sharing.granteelisting_navigator',

        setUp: function () {
            this.fixture = Y.one('#fixture');
            var grantee_table = Y.Node.create(
                    Y.one('#grantee-table-template').getContent());
            this.fixture.appendChild(grantee_table);

        },

        tearDown: function () {
            if (this.fixture !== null) {
                this.fixture.empty();
            }
            delete this.fixture;
        },

        _create_Widget: function() {
            var ns = Y.lp.registry.sharing.granteelisting_navigator;
            return new ns.GranteeListingNavigator({
                cache: {},
                target: Y.one('#grantee-table')
            });
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.registry.sharing.granteelisting_navigator,
                "Could not locate the " +
                "lp.registry.sharing.granteelisting_navigator module");
        },

        test_widget_can_be_instantiated: function() {
            this.navigator = this._create_Widget();
            var ns = Y.lp.registry.sharing.granteelisting_navigator;
            Y.Assert.isInstanceOf(
                ns.GranteeListingNavigator,
                this.navigator,
                "Grantee listing navigator failed to be instantiated");
        }
    }));

}, '0.1', {'requires': ['test', 'test-console',
        'lp.registry.sharing.granteelisting_navigator'
    ]});
