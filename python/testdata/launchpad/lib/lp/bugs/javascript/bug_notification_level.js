/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Animation for IBugTask:+subscribe LaunchpadForm.
 * Also used in "Edit subscription" advanced overlay.
 *
 * @namespace Y.lp.bugs.bug_notification_level
 * @requires  dom, "node, lp.anim, lp.ui.effects
 */
YUI.add('lp.bugs.bug_notification_level', function(Y) {
var namespace = Y.namespace('lp.bugs.bug_notification_level');

/**
 * Should notification level options be shown for these conditions?
 *
 * @param value {String} Value of the selected radio button.  Special
 *     value 'update-subscription' is used for the radio button that
 *     indicates editing of the existing subscription.
 * @param can_update_subscription {Boolean} Is there a radio button to
 *     update the existing subscription?  If there is, it is the only
 *     radio button that should show the notification level options.
 * @returns {Boolean} True if notification level options should be shown
 *     for this set of conditions.
 */
function is_notification_level_shown(value, can_update_subscription) {
    // Is the new selected option the "subscribe me" option?
    // It is when there is no button to update existing subscription,
    // and the selected radio button is for the current user.
    var needs_to_subscribe = (
        (can_update_subscription === false) &&
            ('/~' + value === LP.links.me));

    // Notification levels selection box is shown when either the
    // radio button is for updating a subscription to set the level,
    // or if a user wants to subscribe.
    if ((value === 'update-subscription') || needs_to_subscribe) {
        return true;
    } else {
        return false;
    }
}
namespace._is_notification_level_shown = is_notification_level_shown;

/**
 * Is the change of the radio buttons such that the notification level options
 * need toggling?
 *
 * @param current_value {String} Previously selected radio button value.
 * @param new_value {String} Newly selected radio button value.
 * @param can_update_subscription {Boolean} Is there a radio button to
 *     update the existing subscription?  If there is, it is the only
 *     radio button that should show the notification level options.
 * @returns {Boolean} True if change from `current_value` to `new_value`
 *     requires toggling the visibility of bug notification level options.
 */
function needs_toggling(current_value, new_value, can_update_subscription) {
    if (current_value !== new_value) {
        var was_shown = is_notification_level_shown(
            current_value, can_update_subscription);
        var should_be_shown = is_notification_level_shown(
            new_value, can_update_subscription);
        return was_shown !== should_be_shown;
    } else {
        return false;
    }
}
namespace._needs_toggling = needs_toggling;

/**
 * Slide-out animation used in the toggle_field_visibility() needs
 * to be stopped if someone quickly selects an option that triggers the
 * slide-in animation.  We keep these globally to be able to stop
 * the running animation. (Exposed for testing)
 */
namespace._slideout_animation = undefined;
var slideout_running = false;

/**
 * Is the bug_notification_level visible in the current view?
 * A global state that we alternate with toggle_field_visibility().
 * (exposed for testing purposes).
 */
namespace._bug_notification_level_visible = true;

/**
 * Change the visibility of the bug notification level options.
 * Uses appropriate animation for nicer effect.
 *
 * @param level_div {Object} A Y.Node to show/hide.
 * @param quick_close {Boolean} Should animation be short-circuited?
 *     Useful for initial set-up, and only allows closing the node.
 */
function toggle_field_visibility(level_div, quick_close) {
    if (quick_close === true) {
        level_div.setStyle('height', '0');
        level_div.setStyle('overflow', 'hidden');
        level_div.addClass('lazr-closed');
        namespace._bug_notification_level_visible = false;
        return;
    }
    if (!namespace._bug_notification_level_visible) {
        namespace._slideout_animation = Y.lp.ui.effects.slide_out(level_div);
        namespace._slideout_animation.after('end', function () {
            slideout_running = false;
        });
        slideout_running = true;
        namespace._slideout_animation.run();
    } else {
        if (Y.Lang.isValue(namespace._slideout_animation) &&
            slideout_running) {
            // It's currently expanding, stop that animation
            // and slide in.
            namespace._slideout_animation.stop();
        }
        Y.lp.ui.effects.slide_in(level_div).run();
    }
    namespace._bug_notification_level_visible = (
        !namespace._bug_notification_level_visible);
}
namespace._toggle_field_visibility = toggle_field_visibility;

/**
 * Sets up an initial state for the bug notification level options,
 * and returns the current state from the selected radio button.
 *
 * @param radio_buttons {NodeList} A list of radio buttons in
 *     the level picker.
 * @param level_div {Node} A node to hide if not needed.
 * @returns {Object} An object containing a string `value` and a boolean
 *     `has_update_subscription_button`.  `value` is undefined if no
 *     radio button is selected.
 */
function initialize(radio_buttons, level_div) {
    var state = {
        value: undefined,
        has_update_subscription_button: false
    };

    var checked_box = radio_buttons.filter(':checked').pop();
    if (Y.Lang.isValue(checked_box)) {
        state.value = checked_box.get('value');
    }

    // Is there a radio button for changing the bug notification level?
    state.has_update_subscription_button = (
        radio_buttons
            .filter('[value="update-subscription"]')
            .size() === 1);

    // Level options are always initially shown in the form.
    namespace._bug_notification_level_visible = true;

    var should_be_shown = is_notification_level_shown(
        state.value, state.has_update_subscription_button);
    if (should_be_shown === false) {
        toggle_field_visibility(level_div, true);
    }

    return state;
}
namespace._initialize = initialize;

/**
 * Set-up showing of bug notification levels as appropriate in the
 * bug subscription form.
 *
 * This form is visible on either IBugTask:+subscribe page, or in the
 * advanced subscription overlay on the IBugTask pages (when
 * 'Edit subscription' or 'Unmute' is clicked).
 *
 * Just before returning, it emits a 'bugnotificationlevel:contentready'
 * event to indicate that the form is ready to be displayed.
 *
 * @returns {Boolean} True if animated showing/hiding was set-up, false
 *     otherwise.
 */
namespace.setup = function() {
    var level_divs = Y.all('.bug-notification-level-field');
    if (level_divs.size() > 1) {
        // There can be no more than one advanced subscription overlay,
        // or this code is going to break.
        Y.error('There are multiple bug-notification-level-field nodes.');
    }
    var level_div = level_divs.pop();
    var subscription_radio_buttons = Y.all('input[name="field.subscription"]');

    // Only collapse the bug_notification_level field if the buttons are
    // available to display it again.
    if (Y.Lang.isValue(level_div) && subscription_radio_buttons.size() > 1) {
        var current_state = initialize(subscription_radio_buttons, level_div);

        subscription_radio_buttons.each(function(subscription_button) {
            subscription_button.on('click', function(e) {
                var value = e.target.get('value');
                if (needs_toggling(
                      current_state.value, value,
                      current_state.has_update_subscription_button)) {
                    toggle_field_visibility(level_div);
                }
                current_state.value = value;
            });
        });
        // Fire event to indicate that initialization of the form was done.
        Y.fire('bugnotificationlevel:contentready');
        // Set-up done.
        return true;
    } else {
        // Nothing was set-up, but we still have to fire the event to
        // indicate that the form is ready to render.
        Y.fire('bugnotificationlevel:contentready');
        return false;
    }
};

}, "0.1", {"requires": ["dom", "event-custom", "node",
                        "lp.anim", "lp.ui.effects"]});
