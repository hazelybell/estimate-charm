/* Copyright 2009-2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.milestonetable.test', function (Y) {
    var tests = Y.namespace('lp.milestonetable.test');

    var milestonetable = Y.lp.registry.milestonetable;
    tests.suite = new Y.Test.Suite("milestonetable Tests");

    tests.suite.add(new Y.Test.Case({
        // Test the setup method.
        name: 'setup',

        _should: {
            error: {
                test_config_undefined: true,
                test_config_property_undefined: true,
                test_missing_tbody_is_an_error: true
                }
            },

        setUp: function() {
            this.tbody = Y.one('#milestone-rows');
            },

        tearDown: function() {
            delete this.tbody;
            milestonetable._milestone_row_uri_template = null;
            milestonetable._tbody = null;
            },

        test_good_config: function() {
            // Verify the config data is stored.
            var config = {
                milestone_row_uri_template: '/uri',
                milestone_rows_id:  '#milestone-rows'
                };
            milestonetable.setup(config);
            Y.Assert.areSame(
                config.milestone_row_uri_template,
                milestonetable._milestone_row_uri_template);
            Y.Assert.areSame(this.tbody, milestonetable._tbody);
            },

        test_config_undefined: function() {
            // Verify an error is thrown if there is no config.
            milestonetable.setup();
            },

        test_config_property_undefined: function() {
            // Verify an error is thrown when the config is incomplete.
            var config = {
                milestone_row_uri_template: '/uri'
                };
            milestonetable.setup(config);
            },

        test_missing_tbody_is_an_error: function() {
            // Verify an error is thrown when the id cannot be found.
            var config = {
                milestone_row_uri_template: '/uri',
                milestone_rows_id:  'does-not-exist'
                };
            milestonetable.setup(config);
            }
        }));

    tests.suite.add(new Y.Test.Case({
        // Test the _setup_milestone_event_data method.
        name: '_setup_milestone_event_data',

        setUp: function() {
            this.tbody = Y.one('#milestone-rows');
            },

        tearDown: function() {
            delete this.tbody;
            },

        test_data_state: function() {
            // Verify the milestone name, target container, and callbacks.
            var data = milestonetable._setup_milestone_event_data(
                {name: '0.1'}, this.tbody);
            Y.Assert.areEqual('0.1', data.name);
            Y.Assert.areSame(this.tbody, data.tbody);
            Y.Assert.areSame(
                milestonetable._on_add_success, data.success_handle.sub.fn);
            Y.Assert.areSame(
                milestonetable._on_add_failure, data.failure_handle.sub.fn);
            }
        }));

    tests.suite.add(new Y.Test.Case({
        // Test the _prepend_node method.
        name: '_prepend_node',

        setUp: function() {
            this.parent_node = null;
            this.child_node = Y.Node.create('<li>3</li>');
            },

        tearDown: function() {
            delete this.parent_node;
            delete this.child_node;
            },

        test_empty_container: function() {
            // Verify that the child is added to the parent node.
            this.parent_node = Y.Node.create('<ul></ul>');
            milestonetable._prepend_node(this.parent_node, this.child_node);
            Y.Assert.areSame(this.parent_node, this.child_node.ancestor());
            },

        test_non_empty_container: function() {
            // Verify that the child is the first child in the parent node.
            this.parent_node = Y.Node.create(
                '<ul><li>2</l1><li>1</l1></ul>');
            milestonetable._prepend_node(this.parent_node, this.child_node);
            Y.Assert.areSame(this.child_node.ancestor(), this.parent_node);
            var first_child = this.child_node.ancestor().get(
                'children').item(0);
            Y.Assert.areSame(this.child_node, first_child);
            }
        }));


    tests.suite.add(new Y.Test.Case({
        // Test the _ensure_table_is_seen method.
        name: '_ensure_table_is_seen',

        setUp: function() {
            this.table = null;
            this.tbody = null;
            },

        tearDown: function() {
            delete this.table;
            delete this.tbody;
            },

        test_hidden_container: function() {
            // Verify that the container's hidden class is removed.
            this.table = Y.Node.create(
                '<table class="listing hidden"><tbody></tbody></table>');
            this.tbody = this.table.get('children').item(0);
            milestonetable._ensure_table_is_seen(this.tbody);
            Y.Assert.areEqual('listing', this.table.get('className'));
            }
        }));

    tests.suite.add(new Y.Test.Case({
        // Test the _clear_add_handlers method.
        name: '_clear_add_handlers',

        setUp: function() {
            this.data =  milestonetable._setup_milestone_event_data(
                {name: '0.1'}, Y.one('#milestone-rows'));
            },

        tearDown: function() {
            delete this.data;
            },

        test_handlers_are_detached: function() {
            // Verify the callbacks are detached.
            // If this fails, multiple prepends will happen.
            Y.Assert.isUndefined(this.data.success_handle.sub.deleted);
            Y.Assert.isUndefined(this.data.failure_handle.sub.deleted);
            milestonetable._clear_add_handlers(this.data);
            Y.Assert.isTrue(this.data.success_handle.sub.deleted);
            Y.Assert.isTrue(this.data.failure_handle.sub.deleted);
            }
        }));

    tests.suite.add(new Y.Test.Case({
        // Test the _on_add_failure and _on_add_success callback methods.
        name: '_on_add_<failure|success>',

        setUp: function() {
            this.failure = 'Could not retrieve milestone 0.1';
            this.success = 'New milestone 0.1';
            this.response = {
                responseText: " <tr><td>" + this.success + "<td></tr> "};
            this.data =  milestonetable._setup_milestone_event_data(
                {name: '0.1'}, Y.one('#milestone-rows'));
            // Needed to reset the DOM.
            this.table = this.data.tbody.ancestor();
            this.tbody_markup = this.table.get('innerHTML');
            },

        tearDown: function() {
            this.table.set('innerHTML', this.tbody_markup);
            delete this.failure;
            delete this.success;
            delete this.response;
            delete this.data;
            delete this.table;
            delete this.tbody_markup;
            },

        test_failure_message_prepended: function() {
            // Verify the failure handler prepends the message.
            milestonetable._on_add_failure('id', this.response, this.data);
            var tr = this.data.tbody.get('children').item(0);
            Y.Assert.areEqual(this.failure, tr.get('text'));
            },

        test_success_milestone_prepended: function() {
            // Verify the success handler prepends the milestone.
            milestonetable._on_add_success('id', this.response, this.data);
            var tr = this.data.tbody.get('children').item(0);
            Y.Assert.areEqual(this.success, tr.get('text'));
            }
        }));

    tests.suite.add(new Y.Test.Case({
        // Test the get_milestone_row method.
        name: 'get_milestone_row',

        setUp: function() {
            milestonetable.setup({
                milestone_row_uri_template: '/path/{name}/+row',
                milestone_rows_id: '#milestone-rows'
                });
            // Monkey patch Y.io to verify it is called.
            this.original_io = Y.io;
            var record = {uri: null};
            this.record = record;
            Y.io = function(uri) {
                record.uri = uri;};
            },

        tearDown: function() {
            Y.io = this.original_io;
            delete milestonetable._milestone_row_uri_template;
            delete milestonetable._tbody;
            delete this.record;
            },

        test_get_milestone_row: function() {
            // Verify the callbacks milestoneoverlay callback executes.
            milestonetable.get_milestone_row({name: '0.1'});
            Y.Assert.areEqual('/path/0.1/+row', this.record.uri);
            }
        }));
}, '0.1', {
    requires: ['lp.testing.runner', 'test', 'test-console',
               'lp.registry.milestonetable']
});
