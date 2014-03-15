/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.registry.sharing.sharingdetailsview.test', function (Y) {

    var tests = Y.namespace('lp.registry.sharing.sharingdetailsview.test');
    tests.suite = new Y.Test.Suite(
        'lp.registry.sharing.sharingdetailsview Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.registry.sharing.sharingdetailsview_tests',

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
                            bug_summary:'Everything is broken.'
                        }
                    ],
                    branches: [
                        {
                            self_link: 'api/devel/~someone/+junk/somebranch',
                            web_link:'/~someone/+junk/somebranch',
                            branch_id: '2',
                            branch_name:'lp:~someone/+junk/somebranch'
                        }
                    ],
                    specifications: [
                        {
                            id: 2,
                            information_type: "Proprietary",
                            name: "big-project",
                            self_link: "api/devel/obsolete-junk/+spec/big-project",
                            web_link: "/obsolete-junk/+spec/big-project"
                        }
                    ],
                    grantee: {
                        displayname: 'Fred Bloggs',
                        self_link: '~fred'
                    },
                    pillar: {
                        self_link: '/pillar'
                    }
                }
            };
            this.fixture = Y.one('#fixture');
            var grantee_table = Y.Node.create(
                    Y.one('#sharing-table-template').getContent());
            this.fixture.appendChild(grantee_table);
        },

        tearDown: function () {
            Y.one('#fixture').empty(true);
            delete window.LP;
        },

        _create_Widget: function(cfg) {
            var ns = Y.lp.registry.sharing.sharingdetailsview;
            return new ns.SharingDetailsView(cfg);
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.registry.sharing.sharingdetailsview,
                "Could not locate the " +
                "lp.registry.sharing.sharingdetailsview module");
        },

        test_widget_can_be_instantiated: function() {
            this.view = this._create_Widget();
            Y.Assert.isInstanceOf(
                Y.lp.registry.sharing.sharingdetailsview.SharingDetailsView,
                this.view,
                "Sharing details view failed to be instantiated");
        },

        // The view is correctly rendered.
        test_render: function() {
            this.view = this._create_Widget();
            this.view.render();
            // The sharing details table - we'll just check one row
            Y.Assert.isNotNull(
                Y.one('#sharing-table-body tr[id=shared-bug-2]'));
        },

        // Clicking a bug remove link calls the confirm_grant_removal
        // method with the correct parameters.
        test_remove_bug_grant_click: function() {
            this.view = this._create_Widget();
            this.view.render();
            var confirmRemove_called = false;
            this.view.confirm_grant_removal = function(
                    delete_link, artifact_uri, artifact_name, artifact_type) {
                Y.Assert.areEqual('api/devel/bugs/2', artifact_uri);
                Y.Assert.areEqual('Bug 2', artifact_name);
                Y.Assert.areEqual('bug', artifact_type);
                Y.Assert.areEqual(delete_link_to_click, delete_link);
                confirmRemove_called = true;

            };
            var delete_link_to_click =
                Y.one('#sharing-table-body span[id=remove-bug-2] a');
            delete_link_to_click.simulate('click');
            Y.Assert.isTrue(confirmRemove_called);
        },

        // Clicking a bug remove link calls the confirm_grant_removal
        // method with the correct parameters.
        test_remove_branch_grant_click: function() {
            this.view = this._create_Widget();
            this.view.render();
            var confirmRemove_called = false;
            this.view.confirm_grant_removal = function(
                    delete_link, artifact_uri, artifact_name, artifact_type) {
                Y.Assert.areEqual(
                    'api/devel/~someone/+junk/somebranch', artifact_uri);
                Y.Assert.areEqual(
                    'lp:~someone/+junk/somebranch', artifact_name);
                Y.Assert.areEqual('branch', artifact_type);
                Y.Assert.areEqual(delete_link_to_click, delete_link);
                confirmRemove_called = true;

            };
            var delete_link_to_click =
                Y.one('#sharing-table-body span[id=remove-branch-2] a');
            delete_link_to_click.simulate('click');
            Y.Assert.isTrue(confirmRemove_called);
        },

        // Clicking a spec remove link calls the confirm_grant_removal
        // method with the correct parameters.
        test_remove_spec_grant_click: function() {
            this.view = this._create_Widget();
            this.view.render();
            var confirmRemove_called = false;
            this.view.confirm_grant_removal = function(
                    delete_link, artifact_uri, artifact_name, artifact_type) {
                Y.Assert.areEqual(
                    'api/devel/obsolete-junk/+spec/big-project',
                    artifact_uri);
                Y.Assert.areEqual('big-project', artifact_name);
                Y.Assert.areEqual('spec', artifact_type);
                Y.Assert.areEqual(delete_link_to_click, delete_link);
                confirmRemove_called = true;
            };
            var delete_link_to_click =
                Y.one('#sharing-table-body span[id=remove-spec-2] a');
            delete_link_to_click.simulate('click');
            Y.Assert.isTrue(confirmRemove_called);
        },

        //Test the behaviour of the removal confirmation dialog.
        _test_confirm_grant_removal: function(click_ok) {
            this.view = this._create_Widget();
            this.view.render();
            var performRemove_called = false;
            this.view.perform_remove_grant = function(
                delete_link, artifact_uri, artifact_type) {
                Y.Assert.areEqual('api/devel/bugs/2', artifact_uri);
                Y.Assert.areEqual('bug', artifact_type);
                Y.Assert.areEqual(artifact_delete_link, delete_link);
                performRemove_called = true;

            };
            var artifact_delete_link =
                Y.one('#sharing-table-body td[id=remove-bug-2] a');
            this.view.confirm_grant_removal(
                artifact_delete_link, 'api/devel/bugs/2', 'Bug 2', 'bug');
            var co = Y.one('.yui3-overlay.yui3-lp-app-confirmationoverlay');
            var actions = co.one('.yui3-lazr-formoverlay-actions');
            var btn_style;
            if (click_ok) {
                btn_style = '.ok-btn';
            } else {
                btn_style = '.cancel-btn';
            }
            var button = actions.one(btn_style);
            button.simulate('click');
            Y.Assert.areEqual(click_ok, performRemove_called);
            Y.Assert.isTrue(
                    co.hasClass('yui3-lp-app-confirmationoverlay-hidden'));
        },

        //Test the remove confirmation dialog when the user clicks Ok.
        test_confirm_grantee_removal_ok: function() {
            this._test_confirm_grant_removal(true);
        },

        //Test the remove confirmation dialog when the user clicks Cancel.
        test_confirm_grantee_removal_cancel: function() {
            this._test_confirm_grant_removal(false);
        },

        // The perform_remove_grant method makes the expected XHR calls when a
        // bug grant remove link is clicked.
        test_perform_remove_bug_grant: function() {
            var mockio = new Y.lp.testing.mockio.MockIo();
            var lp_client = new Y.lp.client.Launchpad({
                io_provider: mockio
            });
            this.view = this._create_Widget({
                lp_client: lp_client
            });
            this.view.render();
            var remove_grant_success_called = false;
            var self = this;
            this.view.remove_grant_success = function(artifact_uri) {
                Y.Assert.areEqual('api/devel/bugs/2', artifact_uri);
                remove_grant_success_called = true;
            };
            var delete_link =
                Y.one('#sharing-table-body span[id=remove-bug-2] a');
            this.view.perform_remove_grant(
                delete_link, 'api/devel/bugs/2', 'bug');
            Y.Assert.areEqual(
                '/api/devel/+services/sharing',
                mockio.last_request.url);
            var expected_qs = '';
            expected_qs = Y.lp.client.append_qs(
                expected_qs, 'ws.op', 'revokeAccessGrants');
            expected_qs = Y.lp.client.append_qs(
                expected_qs, 'pillar', '/pillar');
            expected_qs = Y.lp.client.append_qs(
                expected_qs, 'grantee', '~fred');
            expected_qs = Y.lp.client.append_qs(
                expected_qs, 'bugs', 'api/devel/bugs/2');
            Y.Assert.areEqual(expected_qs, mockio.last_request.config.data);
            mockio.last_request.successJSON({});
            Y.Assert.isTrue(remove_grant_success_called);
        },

        // The perform_remove_grant method makes the expected XHR calls when a
        // branch grant remove link is clicked.
        test_perform_remove_branch_grant: function() {
            var mockio = new Y.lp.testing.mockio.MockIo();
            var lp_client = new Y.lp.client.Launchpad({
                io_provider: mockio
            });
            this.view = this._create_Widget({
                lp_client: lp_client
            });
            this.view.render();
            var remove_grant_success_called = false;
            var self = this;
            this.view.remove_grant_success = function(artifact_uri) {
                Y.Assert.areEqual(
                    'api/devel/~someone/+junk/somebranch', artifact_uri);
                remove_grant_success_called = true;
            };
            var delete_link =
                Y.one('#sharing-table-body span[id=remove-branch-2] a');
            this.view.perform_remove_grant(
                delete_link, 'api/devel/~someone/+junk/somebranch', 'branch');
            Y.Assert.areEqual(
                '/api/devel/+services/sharing',
                mockio.last_request.url);
            var expected_qs = '';
            expected_qs = Y.lp.client.append_qs(
                expected_qs, 'ws.op', 'revokeAccessGrants');
            expected_qs = Y.lp.client.append_qs(
                expected_qs, 'pillar', '/pillar');
            expected_qs = Y.lp.client.append_qs(
                expected_qs, 'grantee', '~fred');
            expected_qs = Y.lp.client.append_qs(
                expected_qs, 'branches', 'api/devel/~someone/+junk/somebranch');
            Y.Assert.areEqual(expected_qs, mockio.last_request.config.data);
            mockio.last_request.successJSON({});
            Y.Assert.isTrue(remove_grant_success_called);
        },

        // The remove bug grant callback updates the model and syncs the UI.
        test_remove_bug_grant_success: function() {
            this.view = this._create_Widget({anim_duration: 0});
            this.view.render();
            var syncUI_called = false;
            this.view.syncUI = function() {
                syncUI_called = true;
            };
            this.view.remove_grant_success('api/devel/bugs/2');
            Y.Assert.isTrue(syncUI_called);
            Y.Array.each(window.LP.cache.bugs,
                function(bug) {
                    Y.Assert.areNotEqual(2, bug.bug_id);
            });
        },

        // The remove branch grant callback updates the model and syncs the UI.
        test_remove_branch_grant_success: function() {
            this.view = this._create_Widget({anim_duration: 0});
            this.view.render();
            var syncUI_called = false;
            this.view.syncUI = function() {
                syncUI_called = true;
            };
            this.view.remove_grant_success(
                'api/devel/~someone/+junk/somebranch');
            Y.Assert.isTrue(syncUI_called);
            Y.Array.each(window.LP.cache.branches,
                function(branch) {
                    Y.Assert.areNotEqual(2, branch.branch_id);
            });
        },

        // The remove specification grant callback updates the model and syncs
        // the UI.
        test_remove_spec_grant_success: function() {
            this.view = this._create_Widget({anim_duration: 0});
            this.view.render();
            var syncUI_called = false;
            this.view.syncUI = function() {
                syncUI_called = true;
            };
            this.view.remove_grant_success(
                'api/devel/obsolete-junk/+spec/big-project');
            Y.Assert.isTrue(syncUI_called);

            // Make sure the are no more specs in the cache.
            Y.Assert.areEqual(0, LP.cache.specifications.length,
                'All specs are removed from the cache.');
        },

        // XHR calls display errors correctly.
        _assert_error_displayed_on_failure: function(
                bug_or_branch, invoke_operation) {
            var mockio = new Y.lp.testing.mockio.MockIo();
            var lp_client = new Y.lp.client.Launchpad({
                io_provider: mockio
            });
            this.view = this._create_Widget({
                lp_client: lp_client
            });
            this.view.render();
            var display_error_called = false;
            var grantee_table = this.view.get('sharing_details_table');
            grantee_table.display_error = function(
                    artifact_id, artifact_type, error_msg) {
                Y.Assert.areEqual(2, artifact_id);
                Y.Assert.areEqual(bug_or_branch, artifact_type);
                Y.Assert.areEqual(
                    'Server error, please contact an administrator.',
                    error_msg);
                display_error_called = true;
            };
            invoke_operation(this.view);
            mockio.last_request.respond({
                status: 500,
                statusText: 'An error occurred'
            });
            Y.Assert.isTrue(display_error_called);
        },

        // The perform_remove_grant method handles errors correctly with bugs.
        test_perform_remove_bug_error: function() {
            var invoke_remove = function(view) {
            var delete_link =
                Y.one('#sharing-table-body span[id=remove-bug-2] a');
                view.perform_remove_grant(
                    delete_link, 'api/devel/bugs/2', 'bug');
            };
            this._assert_error_displayed_on_failure('bug', invoke_remove);
        },

        // The perform_remove_grant method handles errors correctly with
        // branches.
        test_perform_remove_branch_error: function() {
            var invoke_remove = function(view) {
            var delete_link =
                Y.one('#sharing-table-body span[id=remove-branch-2] a');
                view.perform_remove_grant(
                    delete_link, 'api/devel/~someone/+junk/somebranch',
                    'branch');
            };
            this._assert_error_displayed_on_failure('branch', invoke_remove);
        },

        // The perform_remove_grant method handles errors correctly with
        // specifications.
        test_perform_remove_spec_error: function() {
            var invoke_remove = function(view) {
                var delete_link =
                    Y.one('#sharing-table-body span[id=remove-spec-2] a');
                    view.perform_remove_grant(
                        delete_link,
                        'api/devel/obsolete-junk/+spec/big-project',
                        'spec');
            };
            this._assert_error_displayed_on_failure('spec', invoke_remove);
        },
        // Test that syncUI works as expected.
        test_syncUI: function() {
            this.view = this._create_Widget();
            this.view.render();
            var grantee_table = this.view.get('sharing_details_table');
            var table_syncUI_called = false;
            grantee_table.syncUI = function() {
                table_syncUI_called = true;
            };
            this.view.syncUI();
            Y.Assert.isTrue(table_syncUI_called);
        }
    }));

}, '0.1', {'requires': ['test', 'test-console', 'event', 'node-event-simulate',
        'lp.testing.mockio',
        'lp.registry.sharing.sharingdetails',
        'lp.registry.sharing.sharingdetailsview']});
