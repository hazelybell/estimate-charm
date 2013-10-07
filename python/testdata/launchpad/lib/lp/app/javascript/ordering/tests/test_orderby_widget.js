/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.orderbybar.test', function(Y) {

    var tests = Y.namespace('lp.orderbybar.test');
    tests.suite = new Y.Test.Suite('OrderByBar Tests');

    var Assert = Y.Assert;
    var ArrayAssert = Y.ArrayAssert;

    tests.suite.add(new Y.Test.Case({
        name: 'orderbybar_widget_tests',
        orderby: null,

        _should: {
            error: {
                test_sort_order_validator:
                    new Error('sort_order must be either "asc" or "desc"'),
                test_active_sort_validator:
                    new Error('active attribute was not found in sort_keys')
            }
        },

        tearDown: function() {
            if (Y.Lang.isValue(this.orderby)) {
                this.orderby.destroy();
            }
        },

        /**
         * Unpack a list of key, name pairs into individual lists.
         *
         * [[Foo, 'Foo Item'], ['Bar', 'Bar item']] becomes
         * ['Foo', 'Bar'] and ['Foo Item', 'Bar Item'].
         */
        getIdsAndNames: function(keys) {
            var ids = [];
            var names = [];
            var len = keys.length;
            var i;
            for (i=0; i<len; i++) {
                ids.push(keys[i][0]);
                names.push(keys[i][1]);
            }
            return [ids, names];
        },

        /*
         * Helper function to create the srcNode on the page.  Widgets
         * will append to the body tag if srcNode is not supplied.
         */
        makeSrcNode: function(id) {
            // Calling the widget's destroy method, which teardown does,
            // will clean this up.
            var parent_node = Y.Node.create('<div></div>');
            parent_node.set('id', id);
            Y.one('body').appendChild(parent_node);
        },

        test_default_sort_keys: function() {
            // The default sort keys should exist in a newly created widget.
            this.orderby = new Y.lp.ordering.OrderByBar();
            var expected_sort_keys = [
                ['bugnumber', 'Number'],
                ['bugtitle', 'Title'],
                ['status', 'Status'],
                ['importance', 'Importance'],
                ['bug-heat-icons', 'Heat'],
                ['package', 'Package name'],
                ['milestone', 'Milestone'],
                ['assignee', 'Assignee'],
                ['bug-age', 'Age']
            ];
            var expected = this.getIdsAndNames(expected_sort_keys);
            var actual = this.getIdsAndNames(this.orderby.get('sort_keys'));
            ArrayAssert.itemsAreSame(expected[0], actual[0]);
            ArrayAssert.itemsAreSame(expected[1], actual[1]);
        },

        test_user_supplied_sort_keys: function() {
            // Call sites can supply their own sort keys to a widget.
            var user_supplied_sort_keys = [
                ['foo', 'Foo item', 'asc'],
                ['bar', 'Bar item', 'asc'],
                ['baz', 'Baz item', 'asc']
            ];
            this.orderby = new Y.lp.ordering.OrderByBar({
                sort_keys: user_supplied_sort_keys});
            var expected = this.getIdsAndNames(user_supplied_sort_keys);
            var actual = this.getIdsAndNames(this.orderby.get('sort_keys'));
            ArrayAssert.itemsAreSame(expected[0], actual[0]);
            ArrayAssert.itemsAreSame(expected[1], actual[1]);
        },

        test_rendered_items_html: function() {
            // We should be able to get a node from the DOM via an ID
            // created from sort keys, and the name should be used as
            // a button display name in HTML.
            var test_sort_keys = [
                ['foo', 'Foo item', 'asc'],
                ['bar', 'Bar item', 'asc']
            ];
            this.makeSrcNode('test-div');
            this.orderby = new Y.lp.ordering.OrderByBar({
                sort_keys: test_sort_keys,
                srcNode: Y.one('#test-div'),
                active: 'foo'
            });
            this.orderby.render();
            var foo_node = Y.one('#sort-foo');
            Assert.isNotNull(foo_node);
            Assert.areEqual(foo_node.get('firstChild').get('text'), 'Foo item');
            var bar_node = Y.one('#sort-bar');
            Assert.isNotNull(bar_node);
            Assert.areEqual(bar_node.get('firstChild').get('text'), 'Bar item');
        },

        test_render_active_sort_default: function() {
            // Confirm that there is a default active sort class applied.
            this.makeSrcNode('test-div');
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div')
            });
            this.orderby.render();
            var li_node = Y.one('#sort-importance');
            Assert.isTrue(li_node.hasClass('active-sort'));
        },

        test_render_active_sort_user_supplied: function() {
            // The active sort class is also set when "active"
            // is supplied via config.
            this.makeSrcNode('test-div');
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                active: 'status'
            });
            this.orderby.render();
            var li_node = Y.one('#sort-status');
            Assert.isTrue(li_node.hasClass('active-sort'));
        },

        test_active_sort_arrow_display_asc: function() {
            // Buttons using "asc" order get a down arrow added to the li.
            this.makeSrcNode('test-div');
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                sort_order: 'asc'
            });
            this.orderby.render();
            var arrow_span = Y.one('.active-sort span');
            var expected_text = '<span class="sprite order-ascending"></span>';
            Assert.areEqual(expected_text, arrow_span.get('innerHTML'));
        },

        test_active_sort_arrow_display_desc: function() {
            // Buttons using "desc" order get an up arrow added to the li.
            this.makeSrcNode('test-div');
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                sort_order: 'desc'
            });
            this.orderby.render();
            var arrow_span = Y.one('.active-sort span');
            var expected_text = '<span class="sprite order-descending"></span>';
            Assert.areEqual(expected_text, arrow_span.get('innerHTML'));
        },

        test_active_sort_click_class_change: function() {
            // Click a node should add the active_sort class
            // and remove that class from the previously active node.
            this.makeSrcNode('test-div');
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div')
            });
            this.orderby.render();
            var importance_node = Y.one('#sort-importance');
            Assert.isTrue(importance_node.hasClass('active-sort'));
            var status_node = Y.one('#sort-status');
            status_node.simulate('click');
            Assert.isTrue(status_node.hasClass('active-sort'));
        },

        test_active_sort_validator: function() {
            // This should fail because we do not allow
            // a "active" value not found in sort_keys.
            var test_sort_keys = [
                ['foo', 'Foo item', 'asc'],
                ['bar', 'Bar item', 'asc']
            ];
            this.orderby = new Y.lp.ordering.OrderByBar({
                sort_keys: test_sort_keys,
                active: 'foobarbazdonotexists'
            });
            this.orderby.render();
        },

        test_sort_order_validator: function() {
            // This should fail when using a sort order
            // other than "asc" or "desc".
            this.orderby = new Y.lp.ordering.OrderByBar({
                sort_order: 'foobar'
            });
            this.orderby.render();
        },

        test_click_current_sort_arrow_changes: function() {
            // Clicking the currently sorted on button should change
            // the arrow and widget state to show a sort change should
            // happen.
            this.makeSrcNode('test-div');
            var test_sort_keys = [
                ['foo', 'Foo item', 'asc'],
                ['bar', 'Bar item', 'asc']
            ];
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                sort_keys: test_sort_keys,
                active: 'foo',
                sort_order: 'asc'
            });
            this.orderby.render();
            var foo_node = Y.one('#sort-foo');
            var expected_starting_text =
                '<span class="sprite order-ascending"></span>';
            var expected_ending_text =
                '<span class="sprite order-descending"></span>';
            Assert.areEqual(
                expected_starting_text, foo_node.one('span').get('innerHTML'));
            Assert.isTrue(foo_node.one('span').hasClass('asc'));
            foo_node.simulate('click');
            Assert.areEqual(
                expected_ending_text, foo_node.one('span').get('innerHTML'));
            Assert.isTrue(foo_node.one('span').hasClass('desc'));
        },

        test_click_different_sort_arrows_change: function() {
            // Clicking a button other than the currently sorted on button
            // should change the arrow and widget state to show a sort
            // change should happen.
            this.makeSrcNode('test-div');
            var test_sort_keys = [
                ['foo', 'Foo item', 'asc'],
                ['bar', 'Bar item', 'asc']
            ];
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                sort_keys: test_sort_keys,
                active: 'foo',
                sort_order: 'asc'
            });
            this.orderby.render();
            var bar_node = Y.one('#sort-bar');
            bar_node.simulate('click');
            var expected_arrow = '<span class="sprite order-ascending"></span>';
            Assert.areEqual(
                expected_arrow, bar_node.one('span').get('innerHTML'));
            Assert.isTrue(bar_node.one('span').hasClass('asc'));
            // Ensure the original button doesn't have sort classes.
            Assert.isFalse(Y.one('#sort-foo').one('span').hasClass('asc'));
            Assert.isFalse(Y.one('#sort-foo').one('span').hasClass('desc'));
        },

        test_click_different_sort_arrows_change_default_order: function() {
            // A newly active sort button has the order as specified by
            // the constructor parameter sort_keys.
            this.makeSrcNode('test-div');
            var test_sort_keys = [
                ['foo', 'Foo item', 'asc'],
                ['bar', 'Bar item', 'desc'],
                ['baz', 'Baz item', 'asc']
            ];
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                sort_keys: test_sort_keys,
                active: 'foo',
                sort_order: 'asc'
            });
            this.orderby.render();
            var bar_node = Y.one('#sort-bar');
            bar_node.simulate('click');
            Assert.isTrue(bar_node.one('span').hasClass('desc'));
            Assert.areEqual('desc', this.orderby.get('sort_order'));
            var baz_node = Y.one('#sort-baz');
            baz_node.simulate('click');
            Assert.isTrue(baz_node.one('span').hasClass('asc'));
            Assert.areEqual('asc', this.orderby.get('sort_order'));
        },

        test_sort_clause_default: function() {
            // sort_clause defaults to "importance".
            this.orderby = new Y.lp.ordering.OrderByBar();
            this.orderby.render();
            Assert.areEqual('importance', this.orderby.get('sort_clause'));
        },

        test_sort_event_fires_with_data: function() {
            // A custom sort event fires from the widget to signal a
            // sort order change should happen in the page.  The
            // callback receives the objects sort_clause for use in
            // a URL.
            this.makeSrcNode('test-div');
            var test_sort_keys = [
                ['foo', 'Foo item', 'asc'],
                ['bar', 'Bar item', 'asc']
            ];
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                sort_keys: test_sort_keys,
                active: 'foo',
                sort_order: 'asc'
            });
            this.orderby.render();
            var foo_node = Y.one('#sort-foo');
            var event_fired = false;
            Y.on('orderbybar:sort', function(e) {
                event_fired = true;
                // Confirm that we get the sort statement we expect, too.
                Assert.areEqual('-foo', e);
            });
            foo_node.simulate('click');
            Assert.isTrue(event_fired);
        },

        test_add_settings_slot: function() {
            // The widget optionally can add a div for settings/config
            // widgets to hook onto.
            this.makeSrcNode('test-div');
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                config_slot: true
            });
            this.orderby.render();
            var config_slot = Y.one('#test-div').one('.config-widget');
            Assert.isNotNull(config_slot);
        },

        test_settings_slot_node_attribute: function() {
            // The widget keeps a reference to the settings slot
            // node if config_slot is true.
            this.makeSrcNode('test-div');
            this.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#test-div'),
                config_slot: true
            });
            this.orderby.render();
            var config_slot = Y.one('#test-div').one('.config-widget');
            Assert.areEqual(config_slot, this.orderby.get('config_node'));
        },

        test_hide_show_sort_buttons: function() {
            // By default, all sort buttons are shown.
            this.orderby = new Y.lp.ordering.OrderByBar();
            this.orderby.render();
            Y.each(this.orderby.get('li_nodes'), function(node) {
                Assert.isFalse(node._isHidden());
            });

            var visibility_rules = {
                'bugnumber': true,
                'bugtitle': true,
                'status': true,
                'importance': false,
                'bug-heat-icons': false,
                'package': false,
                'milestone': false,
                'assignee': false,
                'bug-age': false
            };
            this.orderby.updateVisibility(visibility_rules);
            Y.each(this.orderby.get('li_nodes'), function(node) {
                sort_name = node.get('id').replace('sort-', '');
                if (visibility_rules[sort_name] === true) {
                    Assert.isFalse(node._isHidden());
                } else {
                    Assert.isTrue(node._isHidden());
                }
            });
        }
    }));

}, '0.1', {'requires': ['test', 'node-event-simulate', 'lp.ordering']});
