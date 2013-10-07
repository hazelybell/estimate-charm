/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.registry.sharing.sharingdetails.test', function(Y) {

// Local aliases
    var Assert = Y.Assert;
    var sharing_details = Y.lp.registry.sharing.sharingdetails;

    var tests = Y.namespace('lp.registry.sharing.sharingdetails.test');
    tests.suite = new Y.Test.Suite(
        "lp.registry.sharing.sharingdetails Tests");

    tests.suite.add(new Y.Test.Case({
        name: 'Sharing Details',

        setUp: function () {
            window.LP = {
                links: {},
                cache: {
                    bugs: [
                        {
                            self_link: 'api/devel/bugs/2',
                            web_link:'/bugs/2',
                            bug_id: '2',
                            bug_importance: 'critical',
                            bug_summary:'Everything is broken.',
                            information_type: 'Private Security'
                        }
                    ],
                    branches: [
                        {
                            self_link: 'api/devel/~someone/+junk/somebranch',
                            web_link:'/~someone/+junk/somebranch',
                            branch_id: '2',
                            branch_name:'lp:~someone/+junk/somebranch',
                            information_type: 'Private'
                        }
                    ]
                }
            };
            this.fixture = Y.one('#fixture');
            var sharing_table = Y.Node.create(
                    Y.one('#sharing-table-template').getContent());
            this.fixture.appendChild(sharing_table);
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
                anim_duration: 0,
                person_name: 'Fred',
                bugs: window.LP.cache.bugs,
                branches: window.LP.cache.branches,
                write_enabled: true
            }, overrides);
            window.LP.cache.grantee_data = config.grantees;
            return new sharing_details.SharingDetailsTable(config);
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.registry.sharing.sharingdetails,
                "Could not locate the " +
                "lp.registry.sharing.sharingdetails module");
        },

        test_constants_is_set: function () {
            Y.Assert.areEqual(
                'sharingDetailsTable',
                sharing_details.SharingDetailsTable.NAME);
            Y.Assert.areEqual(
                'removeGrant',
                sharing_details.SharingDetailsTable.REMOVE_GRANT);
        },

        test_widget_can_be_instantiated: function() {
            this.details_widget = this._create_Widget();
            Y.Assert.isInstanceOf(
                Y.lp.registry.sharing.sharingdetails.SharingDetailsTable,
                this.details_widget,
                "Sharing details table failed to be instantiated");
        },

        // Read only mode disables the correct things.
        test_readonly: function() {
            this.details_widget = this._create_Widget({
                write_enabled: false
            });
            this.details_widget.render();
            Y.all('#sharing-table-body .sprite.remove a')
                .each(function(link) {
                    Y.Assert.isTrue(link.hasClass('hidden'));
            });
        },

        _strip: function(text) {
            return text.replace(/\s+/g, '');
        },

        // Test that branches are correctly rendered.
        test_render_branches: function () {
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            var row = Y.one(
                '#sharing-table-body tr#shared-branch-2');
            var web_link = row.one('a');
            var expected = "lp:~someone/+junk/somebranch";
            var actual_text = web_link.get('text');
            Assert.areEqual(expected, this._strip(actual_text));
            var info_type = row.one('.information_type');
            var info_text = info_type.get('text');
            Assert.areEqual('Private', this._strip(info_text));
            var sortkey = row.one('.sortkey').get('text');
            Assert.areEqual(
                "sorttable_branchsortkey", this._strip(sortkey));
        },

        // Test that bugs are correctly rendered.
        test_render_bugs: function () {
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            var row = Y.one(
                '#sharing-table-body tr#shared-bug-2');
            var web_link = row.one('a');
            var expected = "Everythingisbroken.";
            var actual_text = web_link.get('text');
            Assert.areEqual(expected, this._strip(actual_text));
            var info_type = row.one('.information_type');
            var info_text = info_type.get('text');
            Assert.areEqual('PrivateSecurity', this._strip(info_text));
            var sortkey = row.one('.sortkey').get('text');
            Assert.areEqual(2, this._strip(sortkey));
        },

        // When the bug revoke link is clicked, the correct event is published.
        test_bug_revoke_click: function() {
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            var event_fired = false;
            this.details_widget.subscribe(
                sharing_details.SharingDetailsTable.REMOVE_GRANT,
                function(e) {
                    var delete_link = e.details[0];
                    var artifact_uri = e.details[1];
                    var artifact_name = e.details[2];
                    var artifact_type = e.details[3];
                    Y.Assert.areEqual('api/devel/bugs/2', artifact_uri);
                    Y.Assert.areEqual('Bug 2', artifact_name);
                    Y.Assert.areEqual('bug', artifact_type);
                    Y.Assert.areEqual(delete_link_to_click, delete_link);
                    event_fired = true;
                }
            );
            var delete_link_to_click =
                Y.one('#sharing-table-body span[id=remove-bug-2] a');
            delete_link_to_click.simulate('click');
            Y.Assert.isTrue(event_fired);
        },

        // Model changes are rendered correctly when syncUI() is called.
        test_syncUI: function() {
            this.details_widget = this._create_Widget();
            this.details_widget.render();

            var sorttable_ns = Y.lp.app.sorttable;
            var orig_init = sorttable_ns.SortTable.init;
            var sorttable_init_called = false;
            sorttable_ns.SortTable.init = function(force_refresh) {
                sorttable_init_called = force_refresh;
            };

            // We manipulate the cached model data - delete a bug.
            var bugs = window.LP.cache.bugs;
            // Delete the first bug.
            bugs.splice(0, 1);
            this.details_widget.syncUI();
            // Check the results.
            var bug_row_selector = '#sharing-table-body tr[id=shared-bug-2]';
            Y.Assert.isNull(Y.one(bug_row_selector));
            var branch_row_selector =
                '#sharing-table-body tr[id=shared-branch-2]';
            Y.Assert.isNotNull(Y.one(branch_row_selector));
            // The sorting data is initialised.
            Y.Assert.isTrue(sorttable_init_called);
            sorttable_ns.SortTable.init = orig_init;
        },

        // When the branch revoke link is clicked, the correct event is
        // published.
        test_branch_revoke_click: function() {
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            var event_fired = false;
            this.details_widget.subscribe(
                sharing_details.SharingDetailsTable.REMOVE_GRANT,
                function(e) {
                    var delete_link = e.details[0];
                    var artifact_uri = e.details[1];
                    var artifact_name = e.details[2];
                    var artifact_type = e.details[3];
                    Y.Assert.areEqual(
                        'api/devel/~someone/+junk/somebranch',
                        artifact_uri);
                    Y.Assert.areEqual(
                        'lp:~someone/+junk/somebranch', artifact_name);
                    Y.Assert.areEqual('branch', artifact_type);
                    Y.Assert.areEqual(delete_link_to_click, delete_link);
                    event_fired = true;
                }
            );
            var delete_link_to_click =
                Y.one('#sharing-table-body span[id=remove-branch-2] a');
            delete_link_to_click.simulate('click');
            Y.Assert.isTrue(event_fired);
        },

        // The delete_artifacts call removes the specified bugs from the table.
        test_delete_bugs: function() {
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            var row_selector = '#sharing-table-body tr[id=shared-bug-2]';
            Y.Assert.isNotNull(Y.one(row_selector));
            this.details_widget.delete_artifacts(
                [window.LP.cache.bugs[0]], [], false);
            Y.Assert.isNull(Y.one(row_selector));
        },

        // The delete_artifacts call removes the specified branches from the
        // table.
        test_delete_branches: function() {
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            var row_selector = '#sharing-table-body tr[id=shared-branch-2]';
            Y.Assert.isNotNull(Y.one(row_selector));
            this.details_widget.delete_artifacts(
                [], [window.LP.cache.branches[0]], false);
            Y.Assert.isNull(Y.one(row_selector));
        },

        // When all artifacts are deleted, a suitable message is displayed.
        test_delete_all_artifacts: function() {
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            this.details_widget.delete_artifacts(
                [window.LP.cache.bugs[0]],
                [window.LP.cache.branches[0]], true);
            Y.Assert.areEqual(
                'There are no shared bugs, branches, or blueprints.',
                Y.one('#sharing-table-body tr').get('text'));
        },

        test_display_error_bug: function() {
            // A bug operation error is displayed correctly.
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            var row_bug = Y.one('#sharing-table-body tr[id=shared-bug-2]');
            var success = false;
            Y.lp.app.errors.display_error = function(flash_node, msg) {
                Y.Assert.areEqual(row_bug, flash_node);
                Y.Assert.areEqual('An error occurred', msg);
                success = true;
            };
            this.details_widget.display_error(2, 'bug', 'An error occurred');
            Y.Assert.isTrue(success);
        },

        test_display_error_branch: function() {
            // A branch operation error is displayed correctly.
            this.details_widget = this._create_Widget();
            this.details_widget.render();
            var row_branch= Y.one('#sharing-table-body tr[id=shared-branch-2]');
            var success = false;
            Y.lp.app.errors.display_error = function(flash_node, msg) {
                Y.Assert.areEqual(row_branch, flash_node);
                Y.Assert.areEqual('An error occurred', msg);
                success = true;
            };
            this.details_widget.display_error(2, 'branch', 'An error occurred');
            Y.Assert.isTrue(success);
        }
    }));


}, '0.1', { 'requires':
    [ 'test', 'test-console', 'event', 'node-event-simulate',
      'lp.registry.sharing.sharingdetails',
      'lp.app.sorttable'
    ]});
