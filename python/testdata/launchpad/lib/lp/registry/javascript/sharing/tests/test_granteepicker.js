/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.registry.sharing.granteepicker.test', function (Y) {

    var tests = Y.namespace('lp.registry.sharing.granteepicker.test');
    tests.suite = new Y.Test.Suite(
        'lp.registry.sharing.granteepicker Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.registry.sharing.granteepicker_tests',

        setUp: function () {
            this.vocabulary = [
                {"value": "fred", "title": "Fred", "css": "sprite-person",
                    "description": "fred@example.com", "api_uri": "~/fred",
                    "metadata": "person"},
                {"value": "frieda", "title": "Frieda", "css": "sprite-team",
                    "description": "frieda@example.com", "api_uri": "~/frieda",
                    "metadata": "team"}
            ];
            this.information_types = [
                {index: '0', value: 'P1', title: 'Policy 1',
                 description: 'Policy 1 description'},
                {index: '1', value: 'P2', title: 'Policy 2',
                 description: 'Policy 2 description'},
                {index: '2', value: 'P3', title: 'Policy 3',
                 description: 'Policy 3 description'}];
            this.sharing_permissions = [
                {'index': 0, 'value': 'ALL', 'title': 'All',
                 'description': 'Everything'},
                {'index': 1, 'value': 'NOTHING', 'title': 'Nothing',
                 'description': 'Nothing'},
                {'index': 2, 'value': 'SOME', 'title': 'Some',
                 'description': 'Some'}
            ];
        },

        tearDown: function () {
            if (Y.Lang.isObject(this.picker)) {
                this.cleanup_widget(this.picker);
            }
        },

        /* Helper function to clean up a dynamically added widget instance. */
        cleanup_widget: function(widget) {
            // Nuke the boundingBox, but only if we've touched the DOM.
            if (widget.get('rendered')) {
                var bb = widget.get('boundingBox');
                bb.get('parentNode').removeChild(bb);
            }
            // Kill the widget itself.
            widget.destroy();
        },

        _create_picker: function(overrides) {
            var config = {
                use_animation: false,
                progressbar: true,
                progress: 50,
                headerContent: "<h2>Share with a user or team</h2>",
                steptitle: "Search for user or exclusive team " +
                            "with whom to share",
                zIndex: 1000,
                visible: false,
                information_types: this.information_types,
                sharing_permissions: this.sharing_permissions
            };
            if (overrides !== undefined) {
                config = Y.merge(config, overrides);
            }
            var ns = Y.lp.registry.sharing.granteepicker;
            var picker = new ns.GranteePicker(config);
            Y.lp.app.picker.setup_vocab_picker(picker, "TestVocab", config);
            return picker;
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.registry.sharing.granteepicker,
                "Could not locate the " +
                "lp.registry.sharing module");
        },

        test_picker_can_be_instantiated: function() {
            this.picker = this._create_picker();
            Y.Assert.isInstanceOf(
                Y.lp.registry.sharing.granteepicker.GranteePicker,
                this.picker,
                "Picker failed to be instantiated");
        },

        // Test that the picker initially displays a normal search and select
        // facility and transitions to step two when a result is selected.
        test_first_step: function() {
            this.picker = this._create_picker();
            // Select a person to trigger transition to next step.
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            var cb = this.picker.get('contentBox');
            Y.Assert.areEqual(
                'Share with a user or team',
                this.picker.get('headerContent').get('text'));
            var steptitle = cb.one('.contains-steptitle h2').getContent();
            Y.Assert.areEqual(
                'Search for user or exclusive team with whom to share',
                steptitle);
            this.picker.get('boundingBox').one(
                '.yui3-picker-results li:nth-child(1)').simulate('click');
            // There should be no saved value at this stage.
            Y.Assert.isUndefined(this.saved_picker_value);

            // The progress should be 75%
            Y.Assert.areEqual(75, this.picker.get('progress'));
            // The first step ui should be hidden.
            Y.Assert.isTrue(cb.one('.yui3-widget-bd').hasClass('hidden'));
            // The step title should be updated according to the selected
            // person. The title should remain unchanged.
            Y.Assert.areEqual(
                'Share with a user or team',
                this.picker.get('headerContent').get('text'));
            steptitle = cb.one('.contains-steptitle h2').getContent();
            Y.Assert.areEqual(
                'Select sharing policies for Fred', steptitle);
            // The second step ui should be visible.
            var step_two_content = cb.one('.picker-content-two');
            Y.Assert.isFalse(step_two_content.hasClass('hidden'));
            // The second step ui should contain input buttons for each access
            // policy type for each sharing permission.
            Y.Array.each(this.information_types, function(info_type) {
                Y.Array.each(this.sharing_permissions, function(permission) {
                    var rb = step_two_content.one(
                        'input[name="field.permission.' + info_type.value +
                        '"][value="' + permission.value + '"]');
                    Y.Assert.isNotNull(rb);
                });
            });
            // There should be a link back to previous step.
            Y.Assert.isNotNull(step_two_content.one('button.prev'));
            // There should be a button and link to finalise the selection.
            Y.Assert.isNotNull(step_two_content.one('button.next'));
        },

        // Test that by default, show() opens the first picker screen.
        test_default_show: function() {
            this.picker = this._create_picker();
            // Select a person to trigger transition to next step.
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.picker.show();
            var cb = this.picker.get('contentBox');
            var steptitle = cb.one('.contains-steptitle h2').getContent();
            Y.Assert.areEqual(
                'Search for user or exclusive team with whom to share',
                steptitle);
        },

        // Test that show() can be used to open the second picker screen with
        // specified information displayed.
        test_show_selected_screen: function() {
            var selected_result;
            this.picker = this._create_picker(
                {
                    save: function(result) {
                        selected_result = result;
                    }
                }
            );

            // Select a person to trigger transition to next step.
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.picker.show({
                first_step: 2,
                grantee: {
                    person_uri: '~/fred',
                    person_name: 'Fred'
                },
                grantee_permissions: {'P1': 'ALL'}
            });
            var cb = this.picker.get('contentBox');
            // Check the title and step title are correct.
            var steptitle = cb.one('.contains-steptitle h2').getContent();
            Y.Assert.areEqual(
                'Update sharing policies',
                this.picker.get('headerContent').get('text'));
            Y.Assert.areEqual(
                'Update sharing policies for Fred', steptitle);
            // By default, selections only for ALL and NOTHING are available
            // (and no others).
            Y.Assert.isNotNull(cb.one('input[value="ALL"]'));
            Y.Assert.isNotNull(cb.one('input[value="NOTHING"]'));
            Y.Assert.isNull(cb.one('input[value="SOME"]'));
            // Selected permission checkboxes should be ticked.
            cb.all('input[name="field.permission.P1"]')
                    .each(function(node) {
                if (node.get('checked')) {
                    Y.Assert.areEqual('ALL', node.get('value'));
                } else {
                    Y.Assert.areEqual('NOTHING', node.get('value'));
                }
            });
            Y.Array.each(['P2', 'P3'], function(info_type) {
                cb.all('input[name="field.permission.' + info_type + '"]')
                        .each(function(node) {
                    if (node.get('checked')) {
                        Y.Assert.areEqual('NOTHING', node.get('value'));
                    }
                });
            });
            // Back button should not he shown
            var back_button = cb.one('button.prev');
            Y.Assert.isNull(back_button);
            // When submit is clicked, the correct person uri is used.
            var select_link = cb.one('button.next');
            select_link.simulate('click');
            Y.Assert.areEqual('~/fred', selected_result.api_uri);
        },

        // Test that show() can be used to open the second picker screen and
        // that we can filter what permissions are shown.
        test_filtered_permissions: function() {
            this.picker = this._create_picker();
            // Select a person to trigger transition to next step.
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.picker.show({
                first_step: 2,
                grantee: {
                    person_uri: '~/fred',
                    person_name: 'Fred'
                },
                allowed_permissions: ['SOME']
            });
            var cb = this.picker.get('contentBox');
            Y.Assert.isNull(cb.one('input[value="ALL"]'));
            Y.Assert.isNull(cb.one('input[value="NOTHING"]'));
            Y.Assert.isNotNull(cb.one('input[value="SOME"]'));
        },

        // Test that selected radio buttons for permission type 'Some' can be
        // disabled.
        test_some_permission_disabled: function() {
            this.picker = this._create_picker();
            // Select a person to trigger transition to next step.
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.picker.show({
                first_step: 2,
                grantee: {
                    person_uri: '~/fred',
                    person_name: 'Fred'
                },
                allowed_permissions: ['ALL', 'SOME', 'NOTHING'],
                disabled_some_types: ['P1']
            });

            var check_permission_node = function(node) {
                var expected_disabled =
                    node.get('name') === 'field.permission.P1' &&
                    node.get('value') === 'SOME';
                Y.Assert.areEqual(expected_disabled, node.get('disabled'));
            };
            var cb = this.picker.get('contentBox');
            cb.all('input[type="radio"][name^="field.permission"]').each(
                check_permission_node);
        },

        // Test that the back button goes back to step one when step two is
        // active.
        test_second_step_back_button: function() {
            this.picker = this._create_picker();
            // Select a person to trigger transition to next step.
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.picker.get('boundingBox').one(
                '.yui3-picker-results li:nth-child(1)').simulate('click');
            var cb = this.picker.get('contentBox');
            var step_two_content = cb.one('.picker-content-two');
            var back_button = step_two_content.one('button.prev');
            back_button.simulate('click');
            // The progress should be 50%
            Y.Assert.areEqual(50, this.picker.get('progress'));
            // The first step ui should be visible.
            Y.Assert.isFalse(cb.one('.yui3-widget-bd').hasClass('hidden'));
            // The title and step title should be updated.
            Y.Assert.areEqual(
                'Share with a user or team',
                this.picker.get('headerContent').get('text'));
            var steptitle = cb.one('.contains-steptitle h2').getContent();
            Y.Assert.areEqual(
                'Search for user or exclusive team with whom to share',
                steptitle);
            // The second step ui should be hidden.
            Y.Assert.isTrue(step_two_content.hasClass('hidden'));
        },

        // Test that a selection made in step two is correctly passed to the
        // specified save function.
        test_second_step_final_selection: function() {
            var selected_result;
            this.picker = this._create_picker(
                {
                    save: function(result) {
                        selected_result = result;
                    }
                }
            );
            // Select a person to trigger transition to next step.
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.picker.get('boundingBox').one(
                '.yui3-picker-results li:nth-child(1)').simulate('click');
            var cb = this.picker.get('contentBox');
            var step_two_content = cb.one('.picker-content-two');
            // Select an access policy.
            step_two_content
                .one('input[name="field.permission.P2"][value="ALL"]')
                .simulate('click');
            var select_button = step_two_content.one('button.next');
            select_button.simulate('click');
            Y.Assert.areEqual(
                3, Y.Object.size(selected_result.selected_permissions));
            Y.Assert.areEqual(
                selected_result.selected_permissions.P1, 'NOTHING');
            Y.Assert.areEqual(
                selected_result.selected_permissions.P2, 'ALL');
            Y.Assert.areEqual(
                selected_result.selected_permissions.P3, 'NOTHING');
            Y.Assert.areEqual('~/fred', selected_result.api_uri);
        },

        // Test that a new grantee can be selected after click the Back button
        // and the new grantee is correctly used in the final result.
        test_grantee_reselection: function() {
            var selected_result;
            this.picker = this._create_picker(
                {
                    save: function(result) {
                        selected_result = result;
                    }
                }
            );
            // Select a person to trigger transition to next step.
            this.picker.set('results', this.vocabulary);
            this.picker.render();
            this.picker.get('boundingBox').one(
                '.yui3-picker-results li:nth-child(1)').simulate('click');
            var cb = this.picker.get('contentBox');
            var step_two_content = cb.one('.picker-content-two');
            var back_button = step_two_content.one('button.prev');
            back_button.simulate('click');
            // Select a different person.
            this.picker.get('boundingBox').one(
                '.yui3-picker-results li:nth-child(2)').simulate('click');
            // Select an access policy.
            step_two_content
                .one('input[name="field.permission.P2"][value="ALL"]')
                .simulate('click');
            var select_button = step_two_content.one('button.next');
            select_button.simulate('click');
            // Check the results.
            Y.Assert.areEqual(
                3, Y.Object.size(selected_result.selected_permissions));
            Y.Assert.areEqual(
                selected_result.selected_permissions.P1, 'NOTHING');
            Y.Assert.areEqual(
                selected_result.selected_permissions.P2, 'ALL');
            Y.Assert.areEqual(
                selected_result.selected_permissions.P3, 'NOTHING');
            Y.Assert.areEqual('~/frieda', selected_result.api_uri);
        },

        // When no info types are selected, the Submit links are disabled.
        test_no_selected_info_types: function() {
            var save_called = false;
            this.picker = this._create_picker(
                {
                    save: function(result) {
                        save_called = true;
                    }
                }
            );
            this.picker.render();
            this.picker.show({
                first_step: 2,
                grantee: {
                    person_uri: '~/fred',
                    person_name: 'Fred'
                }
            });
            var cb = this.picker.get('contentBox');
            // Check when first showing the picker.
            cb.all('.next', function(button) {
                Y.Assert.isTrue(button.get('disabled'));
            });
            // Check that save is not called even if button is clicked.
            var select_button = cb.one('button.next');
            select_button.simulate('click');
            Y.Assert.isFalse(save_called);
            // Select one info type and check submit button is enabled.
            cb.one('input[name="field.permission.P1"][value="ALL"]')
                .simulate('click');
            cb.all('button.next', function(button) {
                Y.Assert.isFalse(button.get('disabled'));
            });
            // De-select info type and submit button is disabled again.
            cb.one('input[name="field.permission.P1"][value="NOTHING"]')
                .simulate('click');
            cb.all('button.next', function(button) {
                Y.Assert.isTrue(button.get('disabled'));
            });
            select_button.simulate('click');
            Y.Assert.isFalse(save_called);
            // Once at least one info type is selected, save is called.
            cb.one('input[name="field.permission.P1"][value="ALL"]')
                .simulate('click');
            select_button.simulate('click');
            Y.Assert.isTrue(save_called);
        }
    }));

}, '0.1', {'requires': ['test', 'test-console', 'event', 'node-event-simulate',
        'lp.app.picker', 'lp.registry.sharing.granteepicker']});
