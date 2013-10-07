/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.registry.sharing.pillarsharingview.test', function (Y) {

    var tests = Y.namespace('lp.registry.sharing.pillarsharingview.test');
    tests.suite = new Y.Test.Suite(
        'lp.registry.sharing.sharing Tests');

    var common_test_methods = {
            setUp: function () {
            Y.one('#fixture').appendChild(
                Y.Node.create(Y.one('#test-fixture').getContent()));
            window.LP = {
                links: {},
                cache: {
                    context: {
                        self_link: '~pillar', display_name: 'Pillar',
                        bug_sharing_policy: 'Bug Policy 1',
                        branch_sharing_policy: null,
                        specification_sharing_policy: null},
                    grantee_data: [
                    {'name': 'fred', 'display_name': 'Fred Bloggs',
                     'role': '(Maintainer)', web_link: '~fred',
                     'self_link': '~fred',
                     'permissions': {'P1': 'ALL', 'P2': 'SOME'},
                     'shared_artifact_types': []},
                    {'name': 'john', 'display_name': 'John Smith',
                     'role': '', web_link: '~john',
                     'self_link': 'file:///api/devel/~john',
                     'permissions': {'P1': 'ALL', 'P3': 'SOME'},
                     'shared_artifact_types': ['P3']}
                    ],
                    sharing_permissions: [
                        {'value': 'ALL', 'title': 'All',
                         'description': 'Everything'},
                        {'value': 'NOTHING', 'title': 'Nothing',
                         'description': 'Nothing'},
                        {'value': 'SOME', 'title': 'Some',
                         'description': 'Some'}
                    ],
                    information_types: [
                        {index: '0', value: 'P1', title: 'Policy 1',
                         description: 'Policy 1 description'},
                        {index: '1', value: 'P2', title: 'Policy 2',
                         description: 'Policy 2 description'},
                        {index: '2', value: 'P3', title: 'Policy 3',
                         description: 'Policy 3 description'}
                    ],
                    bug_sharing_policies: [
                        {index: '0', value: 'BSP1', title: 'Bug Policy 1',
                         description: 'Bug Policy 1 description'},
                        {index: '1', value: 'BSP2', title: 'Bug Policy 2',
                         description: 'Bug Policy 2 description'}
                    ],
                    branch_sharing_policies: [
                        {index: '0', value: 'BRSP1',
                         title: 'Branch Policy 1',
                         description: 'Branch Policy 1 description'}
                    ],
                    specification_sharing_policies: [
                        {index: '0', value: 'SPSP1',
                         title: 'Specification Policy 1',
                         description: 'Specification Policy 1 description'}
                    ]
                }
            };
            this.mockio = new Y.lp.testing.mockio.MockIo();
        },

        tearDown: function () {
            Y.one('#fixture').empty(true);
            delete window.LP;
            delete this.mockio;
        },

        _create_Widget: function(cfg) {
            var lp_client = new Y.lp.client.Launchpad({
                io_provider: this.mockio
            });
            var config = Y.merge(cfg, {
                lp_client: lp_client,
                anim_duration: 0,
                header: "Grant access",
                steptitle: "Select user",
                vocabulary: "SharingVocab",
                legacy_sharing_policy_description: "Legacy"
            });
            var ns = Y.lp.registry.sharing.pillarsharingview;
            return new ns.PillarSharingView(config);
        }
    };

    tests.suite.add(new Y.Test.Case(Y.merge(common_test_methods, {
        name: 'lp.registry.sharing.sharing_tests',

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.registry.sharing.pillarsharingview,
                "Could not locate the " +
                "lp.registry.sharing.pillarsharingview module");
        },

        test_widget_can_be_instantiated: function() {
            this.view = this._create_Widget();
            Y.Assert.isInstanceOf(
                Y.lp.registry.sharing.pillarsharingview.PillarSharingView,
                this.view,
                "Pillar sharing view failed to be instantiated");
            // Check the picker config.
            var grantee_picker = this.view.get('grantee_picker');
            Y.Assert.areEqual(
                grantee_picker.get('headerContent')
                    .get('text'), 'Grant access');
            Y.Assert.areEqual(grantee_picker.get('steptitle'), 'Select user');
        },

        // The view is correctly rendered.
        test_render: function() {
            this.view = this._create_Widget();
            this.view.render();
            // Check the grantee table config.
            Y.Assert.areEqual(
                this.view.get('grantee_table').get('pillar_name'),
                'Pillar');
            // The grantee table - we'll just check one row
            Y.Assert.isNotNull(
                Y.one('#grantee-table tr[id=permission-fred]'));
            // The sharing picker
            Y.Assert.isNotNull(Y.one('.yui3-grantee_picker'));
        },

        // Clicking a update grantee grantee link calls
        // the update_grantee_interaction method with the correct parameters.
        test_update_grantee_click: function() {
            this.view = this._create_Widget();
            this.view.render();
            var update_grantee_called = false;
            this.view.update_grantee_interaction = function(
                    update_link, person_uri, person_name) {
                Y.Assert.areEqual('~fred', person_uri);
                Y.Assert.areEqual('Fred Bloggs', person_name);
                Y.Assert.areEqual(update_link_to_click, update_link);
                update_grantee_called = true;

            };
            var update_link_to_click =
                Y.one('#grantee-table span[id=update-fred] a');
            update_link_to_click.simulate('click');
            Y.Assert.isTrue(update_grantee_called);
        },

        // The update_grantee_interaction method shows the correctly
        // configured sharing picker.
        test_update_grantee_interaction: function() {
            this.view = this._create_Widget();
            this.view.render();
            var show_picker_called = false;
            var grantee_picker = this.view.get('grantee_picker');
            grantee_picker.show = function(config) {
                Y.Assert.areEqual(2, config.first_step);
                Y.Assert.areEqual('~john', config.grantee.person_uri);
                Y.Assert.areEqual('John', config.grantee.person_name);
                Y.Assert.areEqual(2, Y.Object.size(config.grantee_permissions));
                Y.Assert.areEqual('ALL', config.grantee_permissions.P1);
                Y.Assert.areEqual('SOME', config.grantee_permissions.P3);
                Y.ArrayAssert.itemsAreEqual(
                    ['ALL', 'NOTHING', 'SOME'],
                    config.allowed_permissions);
                Y.ArrayAssert.itemsAreEqual(
                    ['P1', 'P2'], config.disabled_some_types);
                show_picker_called = true;
            };
            var update_link =
                Y.one('#grantee-table span[id=update-smith] a');
            this.view.update_grantee_interaction(update_link, '~john', 'John');
            Y.Assert.isTrue(show_picker_called);
        },

        // Clicking the sharing link opens the sharing picker
        test_sharing_link_click: function() {
            this.view = this._create_Widget();
            this.view.render();
            Y.one('#add-grantee-link').simulate('click');
            Y.Assert.isFalse(
                Y.one('.yui3-grantee_picker')
                    .hasClass('yui3-grantee_picker-hidden'));
        },

        // Clicking a delete grantee link calls the confirm_grantee_removal
        // method with the correct parameters.
        test_delete_grantee_click: function() {
            this.view = this._create_Widget();
            this.view.render();
            var confirmRemove_called = false;
            this.view.confirm_grantee_removal = function(
                    delete_link, person_uri, person_name) {
                Y.Assert.areEqual('~fred', person_uri);
                Y.Assert.areEqual('Fred Bloggs', person_name);
                Y.Assert.areEqual(delete_link_to_click, delete_link);
                confirmRemove_called = true;

            };
            var delete_link_to_click =
                Y.one('#grantee-table span[id=remove-fred] a');
            delete_link_to_click.simulate('click');
            Y.Assert.isTrue(confirmRemove_called);
        },

        //Test the behaviour of the removal confirmation dialog.
        _test_confirm_grantee_removal: function(click_ok) {
            this.view = this._create_Widget();
            this.view.render();
            var performRemove_called = false;
            this.view.perform_remove_grantee = function(
                    delete_link, person_uri) {
                Y.Assert.areEqual('~fred', person_uri);
                Y.Assert.areEqual(delete_link, delete_link);
                performRemove_called = true;

            };
            var delete_link =
                Y.one('#grantee-table td[id=remove-fred] a');
            this.view.confirm_grantee_removal(
                delete_link, '~fred', 'Fred Bloggs');
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
            this._test_confirm_grantee_removal(true);
        },

        //Test the remove confirmation dialog when the user clicks Cancel.
        test_confirm_grantee_removal_cancel: function() {
            this._test_confirm_grantee_removal(false);
        },

        // The perform_remove_grantee method makes the expected XHR calls.
        test_perform_remove_grantee: function() {
            this.view = this._create_Widget();
            this.view.render();
            var remove_grantee_success_called = false;
            var self = this;
            this.view.remove_grantee_success = function(person_uri) {
                Y.Assert.areEqual('~fred', person_uri);
                remove_grantee_success_called = true;
            };
            var delete_link =
                Y.one('#grantee-table span[id=remove-fred] a');
            this.view.perform_remove_grantee(delete_link, '~fred');
            Y.Assert.areEqual(
                '/api/devel/+services/sharing',
                this.mockio.last_request.url);
            Y.Assert.areEqual(
                'ws.op=deletePillarGrantee&pillar=~pillar' +
                    '&grantee=~fred',
                this.mockio.last_request.config.data);
            this.mockio.last_request.successJSON(['Invisible']);
            Y.Assert.isTrue(remove_grantee_success_called);
            Y.ArrayAssert.itemsAreEqual(
                ['Invisible'], LP.cache.invisible_information_types);
        },

        // The removeGrantee callback updates the model and syncs the UI.
        test_remove_grantee_success: function() {
            this.view = this._create_Widget({anim_duration: 0.001});
            this.view.render();
            var syncUI_called = false;
            this.view.syncUI = function() {
                syncUI_called = true;
            };
            this.view.remove_grantee_success('~fred');
            Y.Assert.isTrue(syncUI_called);
            Y.Array.each(window.LP.cache.grantee_data,
                function(grantee) {
                    Y.Assert.areNotEqual('fred', grantee.name);
            });
        },

        // XHR calls display errors correctly.
        _assert_error_displayed_on_failure: function(invoke_operation) {
            this.view = this._create_Widget();
            this.view.render();
            var display_error_called = false;
            var grantee_table = this.view.get('grantee_table');
            grantee_table.display_error = function(grantee_name, error_msg) {
                Y.Assert.areEqual('fred', grantee_name);
                Y.Assert.areEqual(
                    'Server error, please contact an administrator.',
                    error_msg);
                display_error_called = true;
            };
            invoke_operation(this.view);
            this.mockio.last_request.respond({
                status: 500,
                statusText: 'An error occurred'
            });
            Y.Assert.isTrue(display_error_called);
        },

        // The perform_remove_grantee method handles errors correctly.
        test_perform_remove_grantee_error: function() {
            var invoke_remove = function(view) {
                var delete_link =
                    Y.one('#grantee-table span[id=remove-fred] a');
                view.perform_remove_grantee(delete_link, '~fred');
            };
            this._assert_error_displayed_on_failure(invoke_remove);
        },

        // When a grantee is added, the expected XHR calls are made.
        test_perform_add_grantee: function() {
            this.view = this._create_Widget();
            this.view.render();
            var save_sharing_selection_success_called = false;
            this.view.save_sharing_selection_success = function(grantee) {
                Y.Assert.areEqual('joe', grantee.name);
                save_sharing_selection_success_called = true;
            };
            // Use the picker to select a new grantee and information type.
            var grantee_picker = this.view.get('grantee_picker');
            var picker_results = [
                {"value": "joe", "title": "Joe", "css": "sprite-person",
                    "description": "joe@example.com", "api_uri": "~/joe",
                    "metadata": "person"}];
            Y.one('#add-grantee-link').simulate('click');
            grantee_picker.set('results', picker_results);
            grantee_picker.get('boundingBox').one(
                '.yui3-picker-results li:nth-child(1)').simulate('click');
            var cb = grantee_picker.get('contentBox');
            var step_two_content = cb.one('.picker-content-two');
            // All sharing permissions should initially be set to nothing.
            step_two_content.all('input[name^=field.permission]')
                    .each(function(radio_button) {
                if (radio_button.get('checked')) {
                    Y.Assert.areEqual('NOTHING', radio_button.get('value'));
                }
            });
            step_two_content
                .one('input[name=field.permission.P2][value="ALL"]')
                .simulate('click');
            var select_button = step_two_content.one('button.next');
            select_button.simulate('click');
            // Selection made using the picker, now check the results.
            Y.Assert.areEqual(
                '/api/devel/+services/sharing',
                this.mockio.last_request.url);
            var person_uri = Y.lp.client.normalize_uri('~/joe');
            person_uri = Y.lp.client.get_absolute_uri(person_uri);
            var expected_url;
            expected_url = Y.lp.client.append_qs(
                expected_url, 'ws.op', 'sharePillarInformation');
            expected_url = Y.lp.client.append_qs(
                expected_url, 'pillar', '~pillar');
            expected_url = Y.lp.client.append_qs(
                expected_url, 'grantee', person_uri);
            expected_url = Y.lp.client.append_qs(
                expected_url, 'permissions', 'Policy 1,Nothing');
            expected_url = Y.lp.client.append_qs(
                expected_url, 'permissions', 'Policy 2,All');
            expected_url = Y.lp.client.append_qs(
                expected_url, 'permissions', 'Policy 3,Nothing');
            Y.Assert.areEqual(
                    expected_url, this.mockio.last_request.config.data);
            this.mockio.last_request.successJSON({
                grantee_entry: {
                    'name': 'joe',
                    'self_link': '~joe'},
                invisible_information_types: ['Invisible']});
            Y.Assert.isTrue(save_sharing_selection_success_called);
            Y.ArrayAssert.itemsAreEqual(
                ['Invisible'], LP.cache.invisible_information_types);
        },

        // When a permission is updated, the expected XHR calls are made.
        test_perform_update_permission: function() {
            this.view = this._create_Widget();
            this.view.render();
            var save_sharing_selection_success_called = false;
            this.view.save_sharing_selection_success = function(grantee) {
                Y.Assert.areEqual('fred', grantee.name);
                save_sharing_selection_success_called = true;
            };
            // Use permission popup to select a new value.
             var permission_popup =
                Y.one('#grantee-table span[id=P1-permission-fred] a');
            permission_popup.simulate('click');
            var permission_choice = Y.one(
                '.yui3-ichoicelist-content a[href=#SOME]');
            permission_choice.simulate('click');

            // Selection made, now check the results.
            Y.Assert.areEqual(
                '/api/devel/+services/sharing',
                this.mockio.last_request.url);
            var person_uri = Y.lp.client.normalize_uri('~fred');
            person_uri = Y.lp.client.get_absolute_uri(person_uri);
            var expected_url;
            expected_url = Y.lp.client.append_qs(
                expected_url, 'ws.op', 'sharePillarInformation');
            expected_url = Y.lp.client.append_qs(
                expected_url, 'pillar', '~pillar');
            expected_url = Y.lp.client.append_qs(
                expected_url, 'grantee', person_uri);
            expected_url = Y.lp.client.append_qs(
                expected_url, 'permissions', 'Policy 1,Some');
            Y.Assert.areEqual(
                    expected_url, this.mockio.last_request.config.data);
            this.mockio.last_request.successJSON({
                grantee_entry: {
                    'name': 'fred',
                    'self_link': '~fred'},
                invisible_information_types: ['Invisible']});
            Y.Assert.isTrue(save_sharing_selection_success_called);
            Y.ArrayAssert.itemsAreEqual(
                ['Invisible'], LP.cache.invisible_information_types);
        },

        // The save_sharing_selection_success callback updates the model and
        // syncs the UI.
        test_save_sharing_selection_success: function() {
            this.view = this._create_Widget({anim_duration: 0.001});
            this.view.render();
            var new_grantee = {
                'name': 'joe'
            };
            var syncUI_called = false;
            this.view.syncUI = function() {
                syncUI_called = true;
            };
            this.view.save_sharing_selection_success(new_grantee);
            Y.Assert.isTrue(syncUI_called);
            var model_updated = false;
            Y.Array.some(window.LP.cache.grantee_data,
                function(grantee) {
                    model_updated = 'joe' === grantee.name;
                    return model_updated;
            });
            Y.Assert.isTrue(model_updated);
        },

        // The save_sharing_selection method handles errors correctly.
        test_save_sharing_selection_error: function() {
            var invoke_save = function(view) {
                view.save_sharing_selection("~fred", ["P1,All"]);
            };
            this._assert_error_displayed_on_failure(invoke_save);
        },

        // If the XHR result of a sharePillarInformation call is null, the user
        // is to be deleted.
        test_save_sharing_selection_null_result: function() {
            this.view = this._create_Widget();
            this.view.render();
            var remove_grantee_success_called = false;
            this.view.remove_grantee_success = function(grantee_uri) {
                Y.Assert.areEqual('file:///api/devel/~fred', grantee_uri);
                remove_grantee_success_called = true;
            };
            this.view.save_sharing_selection("~fred", ["P1,All"]);
            this.mockio.last_request.successJSON({
                invisible_information_types: [],
                grantee_entry: null});
            Y.Assert.isTrue(remove_grantee_success_called);
        },

        // Test that syncUI works as expected.
        test_syncUI: function() {
            this.view = this._create_Widget();
            this.view.render();
            var grantee_table = this.view.get('grantee_table');
            var table_syncUI_called = false;
            grantee_table.syncUI = function() {
                table_syncUI_called = true;
            };
            this.view.syncUI();
            Y.Assert.isTrue(table_syncUI_called);
        },

        // A warning is rendered when there are invisible access policies.
        test_invisible_access_policy: function() {
            window.LP.cache.invisible_information_types = ['Private'];
            this.view = this._create_Widget();
            this.view.render();
            Y.Assert.isNotNull(Y.one('.large-warning ul.bulleted'));
            Y.Assert.areEqual('Private',
                Y.one('.large-warning ul.bulleted li').get('text'));
        },

        // There is no warning when there are no invisible access policies.
        test_no_invisible_grantees: function() {
            this.view = this._create_Widget();
            this.view.render();
            Y.Assert.isNull(Y.one('.large-warning ul.bulleted'));
        }
    })));

    tests.suite.add(new Y.Test.Case(Y.merge(common_test_methods, {
        name: 'lp.registry.sharing.sharing_policy_tests',

        // A pillar's sharing policy is correctly rendered.
        _assert_sharing_policies_editable: function(editable) {
            var bug_edit_link = Y.one('#bug-sharing-policy .edit');
            Y.Assert.areEqual(editable, !bug_edit_link.hasClass('hidden'));
            var branch_edit_link = Y.one('#branch-sharing-policy .edit');
            Y.Assert.areEqual(editable, !branch_edit_link.hasClass('hidden'));
        },

        // When there is no sharing policy defined for a pillar, the default
        // policy becomes the legacy policy.
        test_sharing_policy_render_no_model_value: function() {
            window.LP.cache.has_edit_permission = true;
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policies_editable(true);
            var row = Y.one('#branch-sharing-policy-row');
            Y.Assert.isFalse(row.hasClass('hidden'));
            var desc_node = Y.one('#branch-sharing-policy-description');
            Y.Assert.areEqual('Legacy', desc_node.get('text'));
            var value_node = Y.one('#branch-sharing-policy .value');
            Y.Assert.areEqual('Legacy policy', value_node.get('text'));
        },

        // A pillar's sharing policy is correctly rendered.
        test_sharing_policy_render: function() {
            // If there is no permission to edit the policy, it's not editable
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policies_editable(false);

            // If there is permission, it is editable.
            window.LP.cache.has_edit_permission = true;
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policies_editable(true);
            var row = Y.one('#bug-sharing-policy-row');
            Y.Assert.isFalse(row.hasClass('hidden'));
            var desc_node = Y.one('#bug-sharing-policy-description');
            Y.Assert.areEqual('Bug Policy 1 description',
                desc_node.get('text').trim());
            var value_node = Y.one('#bug-sharing-policy .value');
            Y.Assert.areEqual(
                    'Bug Policy 1', value_node.get('text').trim());
        },

        // If there is only one policy choice, no edit links are available.
        test_sharing_policy_render_only_one_choice: function() {
            // Add a model value so the legacy choice is not used.
            window.LP.cache.context.branch_sharing_policy
                    = 'Branch Policy 1';
            this.view = this._create_Widget();
            this.view.render();
            var branch_edit_link = Y.one('#branch-sharing-policy .edit');
            Y.Assert.isTrue(branch_edit_link.hasClass('hidden'));

        },

        // A save operation makes the expected XHR call.
        _assert_sharing_policy_save: function(artifact_type, title) {
            Y.one('#' + artifact_type + '-sharing-policy a.edit')
                    .simulate('click');
            var permission_choice = Y.one(
                'a[href=#' + title + ' Policy 1]');
            permission_choice.simulate('click');
            Y.Assert.areEqual(
                '/api/devel/+services/sharing',
                this.mockio.last_request.url);
            Y.Assert.areEqual(
                'ws.op=updatePillarSharingPolicies&pillar=~pillar&' +
                artifact_type + '_sharing_policy=' + title + '%20Policy%201',
                this.mockio.last_request.config.data);
        },

        _assert_artifact_sharing_policy_save_success: function(
            artifact_type, title) {
            var artifact_key = artifact_type + '_sharing_policy';
            window.LP.cache.context[artifact_key] = null;
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policy_save(artifact_type, title);
            var reload_called = false;
            this.view._reload = function() {
                reload_called = true;
            };
            this.mockio.last_request.successJSON({});
            Y.Assert.isTrue(reload_called);
        },

        // Bug sharing policy is saved.
        test_bug_sharing_policy_save: function() {
            window.LP.cache.context.bug_sharing_policy = null;
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policy_save('bug', 'Bug');
        },

        test_bug_sharing_policy_save_success: function() {
            this._assert_artifact_sharing_policy_save_success('bug', 'Bug');
        },

        // When a failure occurs, the client retains the existing data.
        test_bug_sharing_policy_save_failure: function() {
            window.LP.cache.context.bug_sharing_policy = null;
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policy_save('bug', 'Bug');
            this.mockio.failure();
            // Check the cached context.
            Y.Assert.isNull(window.LP.cache.context.bug_sharing_policy);
            // Check the portlet.
            Y.Assert.areEqual(
                'Legacy policy',
                Y.one('#bug-sharing-policy .value').get('text'));
            Y.Assert.areEqual(
                'Legacy',
                Y.one('#bug-sharing-policy-description').get('text'));
        },

        // Branch sharing policy is saved.
        test_branch_sharing_policy_save: function() {
            window.LP.cache.context.bug_sharing_policy = null;
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policy_save('branch', 'Branch');
        },

        test_branch_sharing_policy_save_success: function() {
            this._assert_artifact_sharing_policy_save_success(
                'branch', 'Branch');
        },

        // When a failure occurs, the client retains the existing data.
        test_branch_sharing_policy_save_failure: function() {
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policy_save('branch', 'Branch');
            this.mockio.failure();
            // Check the cached context.
            Y.Assert.isNull(window.LP.cache.context.branch_sharing_policy);
            // Check the portlet.
            Y.Assert.areEqual(
                'Legacy policy',
                Y.one('#branch-sharing-policy .value').get('text'));
            Y.Assert.areEqual(
                'Legacy',
                Y.one('#branch-sharing-policy-description').get('text'));
        },

        // Specification sharing policy is saved.
        test_specification_sharing_policy_save: function() {
            window.LP.cache.context.specification_sharing_policy = null;
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policy_save(
                'specification', 'Specification');
        },

        test_specification_sharing_policy_save_success: function() {
            this._assert_artifact_sharing_policy_save_success(
                'specification', 'Specification');
        },

        // When a failure occurs, the client retains the existing data.
        test_specification_sharing_policy_save_failure: function() {
            this.view = this._create_Widget();
            this.view.render();
            this._assert_sharing_policy_save(
                'specification', 'Specification');
            this.mockio.failure();
            // Check the cached context.
            Y.Assert.isNull(
                window.LP.cache.context.specification_sharing_policy);
            // Check the portlet.
            Y.Assert.areEqual(
                'Legacy policy',
                Y.one('#specification-sharing-policy .value').get('text'));
            Y.Assert.areEqual(
                'Legacy',
                Y.one('#specification-sharing-policy-description').get(
                    'text'));
        }
    })));

}, '0.1', {'requires': ['test', 'test-console', 'event', 'node-event-simulate',
        'lp.testing.mockio', 'lp.registry.sharing.granteepicker',
        'lp.registry.sharing.granteetable', 'lp.app.errors',
        'lp.registry.sharing.pillarsharingview']});
