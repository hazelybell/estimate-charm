/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.registry.sharing.granteetable.test', function (Y) {

    var tests = Y.namespace('lp.registry.sharing.granteetable.test');
    tests.suite = new Y.Test.Suite(
        'lp.registry.sharing.granteetable Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.registry.sharing.granteetable_tests',

        setUp: function () {
            window.LP = {
                links: {},
                cache: {
                    context: {self_link: "~pillar" },
                    grantee_data: [
                    {'name': 'fred', 'display_name': 'Fred Bloggs',
                     'role': '(Maintainer)', web_link: '~fred',
                     'self_link': '~fred',
                     'icon_url': null, 'sprite_css': 'sprite person',
                     'permissions': {'P1': 's1', 'P2': 's2'}},
                    {'name': 'john.smith', 'display_name': 'John Smith',
                     'role': '', web_link: '~smith', 'self_link': '~smith',
                     'icon_url': 'smurf.png', 'sprite_css': 'sprite person',
                     'shared_items_exist': true,
                    'permissions': {'P1': 's1', 'P3': 's3'}}
                    ]
                }
            };
            this.sharing_permissions = {
                s1: 'S1',
                s2: 'S2'
            };
            this.information_types = {
                P1: 'Policy 1',
                P2: 'Policy 2',
                P3: 'Policy 3'
            };
            this.fixture = Y.one('#fixture');
            var grantee_table = Y.Node.create(
                    Y.one('#grantee-table-template').getContent());
            this.fixture.appendChild(grantee_table);
        },

        tearDown: function () {
            if (this.fixture !== null) {
                this.fixture.empty(true);
            }
            delete this.fixture;
            delete window.LP;
        },

        _create_Widget: function(overrides) {
            if (!Y.Lang.isValue(overrides)) {
                overrides = {};
            }
            var config = Y.merge({
                pillar_name: 'My Project',
                grantee_table: Y.one('#grantee-table'),
                anim_duration: 0,
                grantees: window.LP.cache.grantee_data,
                sharing_permissions: this.sharing_permissions,
                information_types: this.information_types,
                write_enabled: true
            }, overrides);
            window.LP.cache.grantee_data = config.grantees;
            var ns = Y.lp.registry.sharing.granteetable;
            return new ns.GranteeTableWidget(config);
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.registry.sharing.granteetable,
                "Could not locate the " +
                "lp.registry.sharing.granteetable module");
        },

        test_widget_can_be_instantiated: function() {
            this.grantee_table = this._create_Widget();
            Y.Assert.isInstanceOf(
                Y.lp.registry.sharing.granteetable.GranteeTableWidget,
                this.grantee_table,
                "Grantee table failed to be instantiated");
        },

        // Write mode unhides the edit icons.
        test_writable: function() {
            window.LP.cache.has_edit_permission = true;
            this.grantee_table = this._create_Widget({
                write_enabled: true
            });
            this.grantee_table.render();
            Y.all('#grantee-table ' +
                  '.sprite.add, .sprite.edit, .sprite.remove a')
                .each(function(link) {
                    Y.Assert.isFalse(link.hasClass('hidden'));
            });
        },

        // Read only mode disables the correct things.
        test_readonly: function() {
            window.LP.cache.has_edit_permission = true;
            this.grantee_table = this._create_Widget({
                write_enabled: false
            });
            this.grantee_table.render();
            Y.all('#grantee-table ' +
                  '.sprite.add, .sprite.edit, .sprite.remove a')
                .each(function(link) {
                    Y.Assert.isTrue(link.hasClass('hidden'));
            });
        },

        // When there are no grantees, the table contains an informative
        // message.
        test_no_grantee_message: function() {
            this.grantee_table = this._create_Widget({
                grantees: []
            });
            this.grantee_table.render();
            Y.Assert.areEqual(
                "My Project's private information is not shared " +
                "with anyone.",
                Y.one('#grantee-table tr td').get('text'));
        },

        // When the first grantee is added, the "No grantees" row is removed.
        test_first_grantee_added: function() {
            this.grantee_table = this._create_Widget({
                grantees: []
            });
            this.grantee_table.render();
            Y.Assert.isNotNull(Y.one('tr#grantee-table-not-shared'));
            var new_grantee = {
                'name': 'joe', 'display_name': 'Joe Smith',
                'role': '(Maintainer)', web_link: '~joe',
                'self_link': '~joe',
                'icon_url': 'smurf.png', 'sprite_css': 'sprite person',
                'permissions': {'P1': 's2'}};
            this.grantee_table.update_grantees([new_grantee]);
            Y.Assert.isNull(Y.one('tr#grantee-table-not-shared'));
        },

        // The given grantee is correctly rendered.
        _test_grantee_rendered: function(grantee) {
            // The grantee row
            var grantee_row = Y.one('#grantee-table tr[id="permission-'
                + grantee.name + '"]');
            Y.Assert.isNotNull(grantee_row);
            // The sprite or branding icon.
            if (Y.Lang.isValue(grantee.icon_url)) {
                Y.Assert.isNotNull(grantee_row.one('img[src="smurf.png"]'));
                Y.Assert.isNull(grantee_row.one('.sprite.person'));
            } else {
                Y.Assert.isNotNull(grantee_row.one('.sprite.person'));
            }
            // The update link
            Y.Assert.isNotNull(
                Y.one('#grantee-table span[id="update-'
                      + grantee.name + '"] a'));
            // The delete link
            Y.Assert.isNotNull(
                Y.one('#grantee-table span[id="remove-'
                      + grantee.name + '"] a'));
            // The sharing permissions
            var self = this;
            Y.each(grantee.permissions, function(permission, info_type) {
                var permission_node =
                    Y.one('#grantee-table td[id="td-permission-'
                          + grantee.name + '"] ul li '
                          + 'span[id="' + info_type + '-permission-'
                          + grantee.name + '"] span.value');
                Y.Assert.isNotNull(permission_node);
                var expected_content =
                    self.information_types[info_type] + ': ' +
                    self.sharing_permissions[permission];
                Y.Assert.areEqual(
                    expected_content, permission_node.get('text'));
            });
            // The shared items link.
            var shared_items_cell = grantee_row.one('td+td+td+td+td');
            if (grantee.shared_items_exist) {
                Y.Assert.isNotNull(
                    shared_items_cell.one(
                        'a[href="+sharing/' + grantee.name + '"]'));
            } else {
                Y.Assert.areEqual(
                    'No items shared through subscriptions.',
                    Y.Lang.trim(shared_items_cell.get('text')));
            }
        },

        // The grantee table is correctly rendered.
        test_render: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var self = this;
            Y.Array.each(this.grantee_data, function(grantee) {
                self._test_grantee_rendered(grantee);
            });
        },

        // When the update link is clicked, the correct event is published.
        test_grantee_update_click: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var event_fired = false;
            var ns = Y.lp.registry.sharing.granteetable;
            this.grantee_table.subscribe(
                ns.GranteeTableWidget.UPDATE_GRANTEE, function(e) {
                    var update_link = e.details[0];
                    var grantee_uri = e.details[1];
                    var person_name = e.details[2];
                    Y.Assert.areEqual('~fred', grantee_uri);
                    Y.Assert.areEqual('Fred Bloggs', person_name);
                    Y.Assert.areEqual(update_link_to_click, update_link);
                    event_fired = true;
                }
            );
            var update_link_to_click =
                Y.one('#grantee-table span[id="update-fred"] a');
            update_link_to_click.simulate('click');
            Y.Assert.isTrue(event_fired);
        },

        // The update_grantees call adds new grantees to the table.
        test_grantee_add: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var new_grantee = {
                'name': 'joe', 'display_name': 'Joe Smith',
                'role': '(Maintainer)', web_link: '~joe',
                'self_link': '~joe',
                'icon_url': 'smurf.png', 'sprite_css': 'sprite person',
                'permissions': {'P1': 's2'}};
            this.grantee_table.update_grantees([new_grantee]);
            this._test_grantee_rendered(new_grantee);
        },

        // The update_grantees call updates existing grantees in the table.
        test_grantee_update: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var updated_grantee = {
                'name': 'fred', 'display_name': 'Fred Bloggs',
                'role': '(Maintainer)', web_link: '~fred',
                'self_link': '~fred',
                'icon_url': null, 'sprite_css': 'sprite person',
                'permissions': {'P1': 's2', 'P2': 's1'}};
            this.grantee_table.update_grantees([updated_grantee]);
            this._test_grantee_rendered(updated_grantee);
        },

        // When the delete link is clicked, the correct event is published.
        test_grantee_delete_click: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var event_fired = false;
            var ns = Y.lp.registry.sharing.granteetable;
            this.grantee_table.subscribe(
                ns.GranteeTableWidget.REMOVE_GRANTEE, function(e) {
                    var delete_link = e.details[0];
                    var grantee_uri = e.details[1];
                    var person_name = e.details[2];
                    Y.Assert.areEqual('~fred', grantee_uri);
                    Y.Assert.areEqual('Fred Bloggs', person_name);
                    Y.Assert.areEqual(delete_link_to_click, delete_link);
                    event_fired = true;
                }
            );
            var delete_link_to_click =
                Y.one('#grantee-table span[id="remove-fred"] a');
            delete_link_to_click.simulate('click');
            Y.Assert.isTrue(event_fired);
        },

        // The delete_grantees call removes the grantees from the table.
        test_grantee_delete: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var row_selector = '#grantee-table tr[id=permission-fred]';
            Y.Assert.isNotNull(Y.one(row_selector));
            this.grantee_table.delete_grantees(
                [window.LP.cache.grantee_data[0]]);
            Y.Assert.isNull(Y.one(row_selector));
        },

        // When the permission popup is clicked, the correct event is published.
        test_permission_update_click: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var event_fired = false;
            var ns = Y.lp.registry.sharing.granteetable;
            this.grantee_table.subscribe(
                ns.GranteeTableWidget.UPDATE_PERMISSION, function(e) {
                    var grantee_uri = e.details[0];
                    var policy = e.details[1];
                    var permission = e.details[2];
                    Y.Assert.areEqual('~fred', grantee_uri);
                    Y.Assert.areEqual('P1', policy);
                    Y.Assert.areEqual(permission, 's2');
                    event_fired = true;
                }
            );
            var permission_popup =
                Y.one('#grantee-table span[id="P1-permission-fred"] a');
            permission_popup.simulate('click');
            var permission_choice = Y.one(
                '.yui3-ichoicelist-content a[href="#s2"]');
            permission_choice.simulate('click');
            Y.Assert.isTrue(event_fired);
        },

        // Model changes are rendered correctly when syncUI() is called.
        test_syncUI: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            // We manipulate the cached model data - delete, add and update
            var grantee_data = window.LP.cache.grantee_data;
            // Delete the first record.
            grantee_data.splice(0, 1);
            // Insert a new record.
            var new_grantee = {
                'name': 'joe', 'display_name': 'Joe Smith',
                'role': '(Maintainer)', web_link: '~joe',
                'self_link': '~joe',
                'icon_url': 'smurf.png', 'sprite_css': 'sprite person',
                'permissions': {'P1': 's2'}};
            grantee_data.splice(0, 0, new_grantee);
            // Update a record.
            grantee_data[1].permissions = {'P1': 's2', 'P2': 's1'};
            this.grantee_table.syncUI();
            // Check the results.
            var self = this;
            Y.Array.each(grantee_data, function(grantee) {
                self._test_grantee_rendered(grantee);
            });
            var deleted_row = '#grantee-table tr[id=permission-fred]';
            Y.Assert.isNull(Y.one(deleted_row));
        },

        // The navigator model total attribute is updated when the currently
        // displayed grantee data changes.
        test_navigation_totals_updated: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            // We manipulate the cached model data - delete, add and update
            var grantee_data = window.LP.cache.grantee_data;
            // Insert a new record.
            var new_grantee = {
                'name': 'joe', 'display_name': 'Joe Smith',
                'role': '(Maintainer)', web_link: '~joe',
                'self_link': '~joe',
                'icon_url': 'smurf.png', 'sprite_css': 'sprite person',
                'permissions': {'P1': 's2'}};
            grantee_data.splice(0, 0, new_grantee);
            this.grantee_table.syncUI();
            // Check the results.
            Y.Assert.areEqual(
                3, this.grantee_table.navigator.get('model').get('total'));
        },

        // When all rows are deleted, the table contains an informative message.
        test_delete_all: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            // We manipulate the cached model data.
            var grantee_data = window.LP.cache.grantee_data;
            // Delete all the records.
            grantee_data.splice(0, 2);
            this.grantee_table.syncUI();
            // Check the results.
            Y.Assert.areEqual(
                "My Project's private information is not shared " +
                "with anyone.",
                Y.one('#grantee-table tr#grantee-table-not-shared td')
                    .get('text'));
        },

        // A batch update is correctly rendered.
        test_navigator_content_update: function() {
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var new_grantee = {
                'name': 'joe', 'display_name': 'Joe Smith',
                'role': '(Maintainer)', web_link: '~joe',
                'self_link': '~joe',
                'icon_url': 'smurf.png', 'sprite_css': 'sprite person',
                'permissions': {'P1': 's2'}};
            this.grantee_table.navigator.fire('updateContent', [new_grantee]);
            this._test_grantee_rendered(new_grantee);
        },

        test_display_error_named_grantee: function() {
            // A named grantee operation error is displayed correctly.
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var row_fred = Y.one('#grantee-table tr[id="permission-fred"]');
            var success = false;
            Y.lp.app.errors.display_error = function(flash_node, msg) {
                Y.Assert.areEqual(row_fred, flash_node);
                Y.Assert.areEqual('An error occurred', msg);
                success = true;
            };
            this.grantee_table.display_error('fred', 'An error occurred');
            Y.Assert.isTrue(success);
        },

        test_display_error_no_grantee: function() {
            // An peration error is displayed correctly.
            this.grantee_table = this._create_Widget();
            this.grantee_table.render();
            var success = false;
            Y.lp.app.errors.display_error = function(flash_node, msg) {
                Y.Assert.isNull(flash_node);
                Y.Assert.areEqual('An error occurred', msg);
                success = true;
            };
            this.grantee_table.display_error(null, 'An error occurred');
            Y.Assert.isTrue(success);
        }
    }));

}, '0.1', {'requires': ['test', 'test-console', 'event', 'node-event-simulate',
        'lp.registry.sharing.granteetable',
        'lp.registry.sharing.granteepicker']});
