/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.blueprints.addspec.test', function (Y) {

    var tests = Y.namespace('lp.blueprints.addspec.test');
    var addspec = Y.namespace('lp.blueprints.addspec');

    tests.suite = new Y.Test.Suite('lp.blueprints.addspec Tests');
    tests.suite.add(new Y.Test.Case({
        // Test the setup method.
        name: 'setup',

        setUp: function() {
            LP = {
            cache: {
                information_type_data: {
                        PUBLIC: {
                            name: 'Public', value: 'PUBLIC',
                            is_private: false,
                            order: 1,
                            description: 'Public bug'
                        },
                        PRIVATESECURITY: {
                            name: 'Private Security',
                            value: 'PRIVATESECURITY',
                            order: 2,
                            is_private: true,
                            description: 'private security bug'
                        },
                        USERDATA: {
                            name: 'Private', value: 'USERDATA',
                            is_private: true,
                            order: 3,
                            description: 'Private bug'
                        }
                    }
                }
            };
        },

        tearDown: function() {
        },

        // The information_type choice popup is rendered.
        test_set_up: function () {
            addspec.set_up();
            var information_type_node =
                Y.one('.information_type-content .value');
            Y.Assert.areEqual('Public', information_type_node.get('text'));
            var information_type_node_edit_node =
                Y.one('.information_type-content a.sprite.edit');
            Y.Assert.isTrue(Y.Lang.isValue(information_type_node_edit_node));
            var legacy_field = Y.one('table.radio-button-widget');
            Y.Assert.isTrue(legacy_field.hasClass('hidden'));
        }
    }));

}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console', 'lp.blueprints.addspec']
});
