/* Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.bugs.bug_notification_level.test', function (Y) {
    var module = Y.lp.bugs.bug_notification_level;

    /**
     * Helper for creating radio buttons for different actions
     * in an advanced subscription overlay.
     */
    function createRadioButton(value, checked) {
        if (checked === undefined) {
            checked = false;
        }
        return Y.Node.create('<input type="radio"></input>')
            .set('name', 'field.subscription')
            .set('value', value)
            .set('checked', checked);
    }

    var tests = Y.namespace('lp.bugs.bug_notification_level.test');
    tests.suite = new Y.Test.Suite('bugs.bug_notification_level Tests');

    /**
     * Test is_notification_level_shown() for a given set of
     * conditions.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'Is the selection of notification levels shown?',

        setUp: function () {
            this.MY_NAME = "ME";
            window.LP = { links: { me: "/~" + this.MY_NAME } };
        },

        tearDown: function() {
            delete window.LP;
        },

        test_subscribe_me: function() {
            // Person wants to subscribe so levels are shown:
            // the selected radio button has a value of the username,
            // and there is no option to update a subscription.
            Y.Assert.isTrue(
                module._is_notification_level_shown(this.MY_NAME, false));
        },

        test_unsubscribe_someone_else: function() {
            // Not subscribed (thus no option to update a subscription)
            // and wants to unsubscribe a team: levels are not shown.
            Y.Assert.isFalse(
                module._is_notification_level_shown('TEAM', false));
        },

        test_edit_subscription_me: function() {
            // There is either an existing subscription, or bug mail
            // is muted, so one can 'update existing subscription'.
            // If unmute/unsubscribe options are chosen, no level
            // options are shown.
            Y.Assert.isFalse(
                module._is_notification_level_shown(this.MY_NAME, true));
        },

        test_edit_subscription_update: function() {
            // There is either an existing subscription, or bug mail
            // is muted, so one can 'update existing subscription'.
            // If 'update-subscription' option is chosen, level
            // options are shown.
            Y.Assert.isTrue(
                module._is_notification_level_shown('update-subscription',
                                                    true));
        },

        test_edit_subscription_someone_else: function() {
            // There is either an existing subscription, or bug mail
            // is muted, so one can 'update existing subscription'.
            // If unsubscribe a team option is chosen, no level
            // options are shown.
            Y.Assert.isFalse(
                module._is_notification_level_shown('TEAM', true));
        }

    }));

    /**
     * Test needs_toggling() which compares two sets of conditions and
     * returns if the need for notification level has changed.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'State of the notification level visibility should change',

        setUp: function () {
            this.MY_NAME = "ME";
            window.LP = { links: { me: "/~" + this.MY_NAME } };
        },

        tearDown: function() {
            delete window.LP;
        },

        test_no_change: function() {
            // Both current_value and new_value are identical.
            Y.Assert.isFalse(
                module._needs_toggling('value', 'value', false));
            Y.Assert.isFalse(
                module._needs_toggling('value', 'value', true));
        },

        test_unsubscribe_to_team: function() {
            // Changing the option from 'unsubscribe me' (no levels shown)
            // to 'unsubscribe team' (no levels shown) means no change.
            Y.Assert.isFalse(
                module._needs_toggling(this.MY_NAME, 'TEAM', true));
        },

        test_edit_subscription_to_team: function() {
            // Changing the option from 'update-subscription' (levels shown)
            // to 'unsubscribe team' (no levels shown) means a change.
            Y.Assert.isTrue(
                module._needs_toggling('update-subscription', 'TEAM', true));
        }

    }));

    /**
     * Test toggle_field_visibility() which shows/hides a node based on
     * the value of bug_notification_level_visible value.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'Toggle visibility of the notification levels with animations',

        setUp: function() {
            // Monkey patch effects duration to make effects instant.
            // This keeps wait times to a minimum.
            this.original_defaults = Y.lp.ui.effects.slide_effect_defaults;
            Y.lp.ui.effects.slide_effect_defaults.duration = 0;
        },

        tearDown: function() {
            // Restore the default value.
            module._bug_notification_level_visible = true;
            Y.lp.ui.effects.slide_effect_defaults = this.original_defaults;
        },

        test_quick_close: function() {
            // When quick_close===true, no animation happens and the
            // node is hidden.
            var node = Y.Node.create('<div></div>');
            module._toggle_field_visibility(node, true);
            Y.Assert.isTrue(node.hasClass('lazr-closed'));
            Y.Assert.areEqual('0px', node.getStyle('height'));
            Y.Assert.areEqual('hidden', node.getStyle('overflow'));
            Y.Assert.isFalse(module._bug_notification_level_visible);
        },

        test_hide_node: function() {
            // Initially a node is shown, so 'toggling' makes it hidden.
            var node = Y.Node.create('<div></div>');
            module._toggle_field_visibility(node);
            this.wait(function() {
                // Wait for the animation to complete.
                Y.Assert.isTrue(node.hasClass('lazr-closed'));
                Y.Assert.isFalse(module._bug_notification_level_visible);
            }, 20);
        },

        test_show_node: function() {
            // When the node is closed, toggling shows it.
            module._bug_notification_level_visible = false;
            var node = Y.Node.create('<div></div>');
            module._toggle_field_visibility(node);
            this.wait(function() {
                // Wait for the animation to complete.
                Y.Assert.isTrue(node.hasClass('lazr-opened'));
                Y.Assert.isTrue(module._bug_notification_level_visible);
            }, 20);
        },

        test_show_and_hide: function() {
            // Showing and then quickly hiding the node stops the
            // slide out animation for nicer rendering.
            module._bug_notification_level_visible = false;
            var node = Y.Node.create('<div></div>');
            // This triggers the 'slide-out' animation.
            module._toggle_field_visibility(node);
            // Now we wait 100ms (<400ms for the animation) and
            // trigger the 'slide-in' animation.
            this.wait(function() {
                module._toggle_field_visibility(node);
                // The slide-out animation should be stopped now.
                Y.Assert.isFalse(module._slideout_animation.get('running'));
            }, 20);
        }

    }));

    /**
     * Test initialize() which sets up the initial state as appropriate.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'Test initial set-up of the level options display.',

        setUp: function () {
            this.MY_NAME = "ME";
            window.LP = { links: { me: "/~" + this.MY_NAME } };
        },

        tearDown: function() {
            delete window.LP;
        },

        test_bug_notification_level_default: function() {
            // `bug_notification_level_visible` is always restored to true.
            var level_node = Y.Node.create('<div></div>');
            var node = Y.Node.create('<div></div>');
            node.appendChild(createRadioButton(this.MY_NAME, true));
            var radio_buttons = node.all('input[name="field.subscription"]');

            module._bug_notification_level_visible = false;
            var state = module._initialize(radio_buttons, level_node);
            Y.Assert.isTrue(module._bug_notification_level_visible);
        },

        test_value_undefined: function() {
            // When there is no selected radio button, the returned value
            // is undefined.
            var level_node = Y.Node.create('<div></div>');
            var node = Y.Node.create('<div></div>');
            node.appendChild(createRadioButton(this.MY_NAME));
            node.appendChild(createRadioButton('TEAM'));
            var radio_buttons = node.all('input[name="field.subscription"]');

            var state = module._initialize(radio_buttons, level_node);
            Y.Assert.isUndefined(state.value);
        },

        test_value_selected: function() {
            // When there is a selected radio button, returned value matches
            // the value from that radio button.
            var level_node = Y.Node.create('<div></div>');
            var node = Y.Node.create('<div></div>');
            node.appendChild(createRadioButton('VALUE', true));
            node.appendChild(createRadioButton('TEAM'));
            var radio_buttons = node.all('input[name="field.subscription"]');

            var state = module._initialize(radio_buttons, level_node);
            Y.Assert.areEqual('VALUE', state.value);
        },

        test_has_update_subscription_button_false: function() {
            // When there is no radio button with value 'update-subscription',
            // returned state indicates that.
            var level_node = Y.Node.create('<div></div>');
            var node = Y.Node.create('<div></div>');
            node.appendChild(createRadioButton(this.MY_NAME, true));
            var radio_buttons = node.all('input[name="field.subscription"]');
            var state = module._initialize(radio_buttons, level_node);
            Y.Assert.isFalse(state.has_update_subscription_button);
        },

        test_has_update_subscription_button_true: function() {
            // When there is a radio button with value 'update-subscription',
            // returned state indicates that.
            var level_node = Y.Node.create('<div></div>');
            var node = Y.Node.create('<div></div>');
            node.appendChild(createRadioButton('update-subscription', true));
            var radio_buttons = node.all('input[name="field.subscription"]');
            var state = module._initialize(radio_buttons, level_node);
            Y.Assert.isTrue(state.has_update_subscription_button);
        },

        test_no_toggling_for_visible: function() {
            // No toggling happens when options should be shown
            // since that's the default.
            var level_node = Y.Node.create('<div></div>');
            var node = Y.Node.create('<div></div>');
            node.appendChild(createRadioButton(this.MY_NAME, true));
            var radio_buttons = node.all('input[name="field.subscription"]');
            module._initialize(radio_buttons, level_node);
            Y.Assert.isFalse(level_node.hasClass('lazr-opened'));
            Y.Assert.isFalse(level_node.hasClass('lazr-closed'));
        },

        test_toggling_for_hiding: function() {
            // Quick toggling happens when options should be hidden.
            var level_node = Y.Node.create('<div></div>');
            var node = Y.Node.create('<div></div>');
            node.appendChild(createRadioButton(this.MY_NAME, true));
            node.appendChild(
                createRadioButton('update-subscription', false));
            var radio_buttons = node.all('input[name="field.subscription"]');
            module._initialize(radio_buttons, level_node);
            Y.Assert.areEqual('0px', level_node.getStyle('height'));
            Y.Assert.isTrue(level_node.hasClass('lazr-closed'));
        }

    }));


    /**
     * Test setup() of level options display toggling.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'Test initial set-up of the level options display.',

        _should: {
            error: {
                test_multiple_nodes_with_level_options: new Error(
                    'There are multiple bug-notification-level-field nodes.')
            }
        },

        setUp: function () {
            this.MY_NAME = "ME";
            window.LP = { links: { me: "/~" + this.MY_NAME } };
            this.root = Y.one('body').appendChild(
                Y.Node.create('<div></div>'));
            // Monkey patch effects duration to make effects instant.
            // This keeps wait times to a minimum.
            this.original_defaults = Y.lp.ui.effects.slide_effect_defaults;
            Y.lp.ui.effects.slide_effect_defaults.duration = 0;
        },

        tearDown: function() {
            delete window.LP;
            this.root.empty();
            Y.lp.ui.effects.slide_effect_defaults = this.original_defaults;
        },

        test_multiple_nodes_with_level_options: function() {
            // Multiple nodes with bug notification level options
            // make the set-up fail.
            this.root.appendChild(
                Y.Node.create('<div></div>')
                    .addClass('bug-notification-level-field'));
            this.root.appendChild(
                Y.Node.create('<div></div>')
                    .addClass('bug-notification-level-field'));
            module.setup();
        },

        test_no_level_options: function() {
            // When there are no level options, no animation is set-up.
            var options_node = Y.Node.create('<div></div>');
            options_node.appendChild(createRadioButton(this.MY_NAME, true));

            var event_fired = false;
            Y.on('bugnotificationlevel:contentready', function () {
                event_fired = true;
            });

            this.root.appendChild(options_node);
            Y.Assert.isFalse(module.setup());

            // Event is fired regardless.
            this.wait(function() {
                Y.Assert.isTrue(event_fired);
            }, 5);
        },

        test_single_option_no_animation: function() {
            // When there is only a single option, no animation is set-up.
            var level_node = Y.Node.create('<div></div>')
                .addClass('bug-notification-level-field');
            var options_node = Y.Node.create('<div></div>');
            options_node.appendChild(createRadioButton(this.MY_NAME, true));

            this.root.appendChild(options_node);
            this.root.appendChild(level_node);

            var event_fired = false;
            Y.on('bugnotificationlevel:contentready', function () {
                event_fired = true;
            });

            Y.Assert.isFalse(module.setup());

            // Event is fired regardless.
            this.wait(function() {
                Y.Assert.isTrue(event_fired);
            }, 5);
        },

        test_animation_set_up: function() {
            // With multiple options (eg. "subscribe me", "unsubscribe team")
            // toggling of visibility (with animation) is set-up for all items.
            var level_node = Y.Node.create('<div></div>')
                .addClass('bug-notification-level-field');

            var subscribe_me = createRadioButton(this.MY_NAME, true);
            var unsubscribe_team = createRadioButton('TEAM', false);

            var options_node = Y.Node.create('<div></div>');
            options_node.appendChild(subscribe_me);
            options_node.appendChild(unsubscribe_team);

            this.root.appendChild(options_node);
            this.root.appendChild(level_node);

            var event_fired = false;
            Y.on('bugnotificationlevel:contentready', function () {
                event_fired = true;
            });

            // Set-up is successful.
            Y.Assert.isTrue(module.setup());

            // And event is fired when the form set-up has been completed.
            this.wait(function() {
                Y.Assert.isTrue(event_fired);
            }, 5);

            // Clicking the second option hides the initially shown
            // notification level options.
            unsubscribe_team.simulate('click');
            this.wait(function() {
                Y.Assert.isTrue(level_node.hasClass('lazr-closed'));
                Y.Assert.isFalse(level_node.hasClass('lazr-opened'));
                Y.Assert.isFalse(module._bug_notification_level_visible);
                // Clicking it again does nothing.
                unsubscribe_team.simulate('click');
                Y.Assert.isFalse(module._bug_notification_level_visible);

                // Clicking the other option slides the options out again.
                subscribe_me.simulate('click');
                this.wait(function() {
                    Y.Assert.isTrue(level_node.hasClass('lazr-opened'));
                    Y.Assert.isFalse(level_node.hasClass('lazr-closed'));
                    Y.Assert.isTrue(module._bug_notification_level_visible);
                }, 20);
            }, 20);
        }

    }));


}, '0.1', {
    'requires': ['test', 'lp.testing.helpers', 'test-console',
        'lp.bugs.bug_notification_level', 'node-event-simulate',
        'lp.ui.effects']
});
