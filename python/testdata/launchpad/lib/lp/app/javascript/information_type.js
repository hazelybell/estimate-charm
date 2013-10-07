/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Base functionality for displaying Information Type data.
 */

YUI.add('lp.app.information_type', function(Y) {

var ns = Y.namespace('lp.app.information_type');
ns.EV_CHANGE = 'information_type:change';
ns.EV_ISPUBLIC = 'information_type:is_public';
ns.EV_ISPRIVATE = 'information_type:is_private';

/**
 * Any time the information type changes during a page we need an event we can
 * watch out for that.
 *
 * @event information_type:change
 * @param value The new information type value.
 */
Y.publish(ns.EV_CHANGE, {
    emitFacade: true
});

/*
 * We also want shortcuts we can use to fire specific events if the new
 * information type is public or private (generally speaking).
 *
 * @event information_type:is_public
 * @param value The new information type value.
 */
Y.publish(ns.EV_ISPUBLIC, {
    emitFacade: true
});

/**
 * The information type has been changed to a private type.
 *
 * @event information_type:is_private
 * @param value The new information type value.
 * @param text A message about the new information type value.
 */
Y.publish(ns.EV_ISPRIVATE, {
    emitFacade: true
});


/**
 * Provide some logic to check if this is a private inducing event. This could
 * be due to a non-public information type or as security related information
 * type/value.
 */
var is_private_event = function (value) {
    var is_private = false;
    if (ns.get_cache_data_from_key(value,
                                  'value',
                                  'is_private')) {

        is_private = true;
    }

    if (value.indexOf('PRIVATESECURITY') !== -1) {
        is_private = true;
    }

    return is_private;
};


/**
 * Wire up a helper event so that if someone changes the event, we take care
 * of also firing any is_private/is_public event shortcuts others want to
 * listen on.
 *
 * This enables us to keep the looking up of information type to ourselves
 * instead of having each module needing to know the location in the LP.cache
 * and such.
 */
Y.on(ns.EV_CHANGE, function (ev) {
    if (!ev.value) {
        throw('Information type change event without new value');
    }

    if (is_private_event(ev.value)) {
        Y.fire(ns.EV_ISPRIVATE, {
            text: ns.get_banner_text(ev.value),
            value: ev.value
        });
    } else {
        Y.fire(ns.EV_ISPUBLIC, {
            value: ev.value
        });
    }
});


// For testing.
var skip_animation = false;

/**
 * Save the new information type. If validate_change is true, then a check
 * will be done to ensure the bug will not become invisible. If the bug will
 * become invisible, a confirmation popup is used to confirm the user's
 * intention. Then this method is called again with validate_change set to
 * false to allow the change to proceed.
 *
 * @param widget
 * @param initial_value
 * @param value
 * @param lp_client
 * @param validate_change
 */
ns.save = function(widget, initial_value, value,
                                           lp_client, context,
                                           subscribers_list, validate_change) {
    var error_handler = new Y.lp.client.FormErrorHandler();
    error_handler.showError = function(error_msg) {
        Y.lp.app.errors.display_error(
            Y.one('#information-type'), error_msg);
    };
    error_handler.handleError = function(ioId, response) {
        if( response.status === 400
                && response.statusText === 'Bug Visibility') {
            ns._confirm_change(
                    widget, initial_value, lp_client, context,
                    subscribers_list);
            return true;
        }
        var orig_value = ns.get_cache_data_from_key(
            context.information_type, 'name', 'value');
        widget.set('value', orig_value);
        widget._showFailed();
        ns.update_privacy_portlet(orig_value);
        return false;
    };
    var submit_url = document.URL + "/+secrecy";
    var qs = Y.lp.client.append_qs('', 'field.actions.change', 'Change');
    qs = Y.lp.client.append_qs(qs, 'field.information_type', value);
    qs = Y.lp.client.append_qs(
            qs, 'field.validate_change', validate_change?'on':'off');
    var config = {
        method: "POST",
        headers: {'Accept': 'application/xhtml;application/json'},
        data: qs,
        on: {
            start: function () {
                widget._uiSetWaiting();
                if (Y.Lang.isValue(subscribers_list)){
                    subscribers_list.subscribers_list.startActivity(
                        'Updating subscribers...');
                }
            },
            end: function () {
                widget._uiClearWaiting();
                if (Y.Lang.isValue(subscribers_list)){
                    subscribers_list.subscribers_list.stopActivity();
                }
            },
            success: function (id, response) {
                var result_data = null;
                if (response.responseText !== '' &&
                    response.getResponseHeader('Content-Type') ===
                    'application/json')
                {
                    result_data = Y.JSON.parse(response.responseText);
                }
                ns.save_success(
                    widget, context, value, subscribers_list, result_data);
                Y.lp.client.display_notifications(
                    response.getResponseHeader('X-Lazr-Notifications'));
            },
            failure: error_handler.getFailureHandler()
        }
    };
    lp_client.io_provider.io(submit_url, config);
};

ns.get_banner_text = function(value) {
    // Construct a different message for security related banner content.
    var text;
    if (value.indexOf('PRIVATESECURITY') !== -1) {
        var security_text = "This report will be private " +
                            "because it is a security " +
                            "vulnerability. You can " +
                            "disclose it later.";
        text = security_text;
    } else {
        var text_template = "This page contains {info_type} information.";
        var info_type = ns.get_cache_data_from_key(value, 'value', 'name');
        text = Y.Lang.sub(text_template, {'info_type': info_type});
    }
    return text;
};

ns.save_success = function(widget, context, value, subscribers_list,
                           result_data) {
    context.information_type =
        ns.get_cache_data_from_key(value, 'value', 'name');

    // Let the world know the information type has been updated. Allows
    // banners to update.
    Y.fire(ns.EV_CHANGE, {
        value: value
    });

    widget._showSucceeded();
    if (Y.Lang.isObject(result_data)) {
        var subscribers = result_data.subscription_data;
        subscribers_list._loadSubscribersFromList(subscribers);
        var cache_data = result_data.cache_data;
        var item;
        for (item in cache_data) {
            if (cache_data.hasOwnProperty(item)) {
                LP.cache[item] = cache_data[item];
            }
        }
        // Update the bugtask actions.
        var project_span = Y.one('#also-affects-product');
        if (Y.Lang.isValue(project_span)) {
            project_span.toggleClass(
                'private-disallow', !result_data.can_add_project_task);
        }
        var package_span = Y.one('#also-affects-package');
        if (Y.Lang.isValue(project_span)) {
            package_span.toggleClass(
                'private-disallow', !result_data.can_add_package_task);
        }
    }
    if (Y.Lang.isValue(subscribers_list)){
        var subscription_ns = Y.lp.bugs.bugtask_index.portlets.subscription;
        subscription_ns.update_subscription_status(skip_animation);
    }
};

/**
 * Possibly prompt the user to confirm the change of information type.
 * If the old value is public, and the new value is private, we want to
 * confirm that the user really wants to make the change.
 *
 * @param widget
 * @param initial_value
 * @param lp_client
 * @private
 */
ns._confirm_change = function(widget, initial_value, lp_client, context,
                              subscribers_list) {
    var value = widget.get('value');
    var do_save = function() {
        ns.update_privacy_portlet(value);
        ns.save(
            widget, initial_value, value, lp_client, context, subscribers_list,
            false);
    };
    // Reset the widget back to it's original value so the user doesn't see it
    // change while the confirmation dialog is showing.
    var new_value = widget.get('value');
    widget.set('value', initial_value);
    ns.update_privacy_portlet(initial_value);
    var confirm_text_template = [
        '<p class="block-sprite large-warning">',
        '    You are about to mark this bug as ',
        '    <strong>{{information_type}}</strong>.<br/>',
        '    The bug will become invisible because there is no-one with',
        '    permissions to see {{information_type}} bugs.',
        '</p><p>',
        '    <strong>Please confirm you really want to do this.</strong>',
        '</p>'
        ].join('');
    var title = ns.get_cache_data_from_key(value, 'value', 'name');
    var confirm_text = Y.lp.mustache.to_html(confirm_text_template,
            {information_type: title});
    var co = new Y.lp.app.confirmationoverlay.ConfirmationOverlay({
        submit_fn: function() {
            widget.set('value', new_value);
            ns.update_privacy_portlet(new_value);
            do_save();
        },
        form_content: confirm_text,
        headerContent: '<h2>Confirm information type change</h2>',
        submit_text: 'Confirm'
    });
    co.show();
};

ns.setup_choice = function(privacy_link, lp_client, context, subscribers_list,
                           skip_anim) {
    skip_animation = skip_anim;
    var initial_value = ns.get_cache_data_from_key(
        context.information_type, 'name', 'value');
    var information_type_value = Y.one('#information-type');
    var choice_list = ns.cache_to_choicesource(
        LP.cache.information_type_data);

    var information_type_edit = new Y.ChoiceSource({
        editicon: privacy_link,
        contentBox: Y.one('#privacy'),
        value_location: information_type_value,
        value: initial_value,
        title: "Change information type",
        items: choice_list,
        backgroundColor: '#FFFF99',
        flashEnabled: false
    });
    Y.lp.app.choice.hook_up_choicesource_spinner(information_type_edit);
    information_type_edit.render();
    information_type_edit.on("save", function(e) {
        var value = information_type_edit.get('value');
        ns.update_privacy_portlet(value);
        ns.save(
            information_type_edit, initial_value, value, lp_client, context,
            subscribers_list, true);
    });
    privacy_link.addClass('js-action');
    return information_type_edit;
};

/**
 * Lookup the information_type property, keyed on the named value.
 *
 * We might want to find based on the name Public or the value PUBLIC so we
 * allow for the user to request what cache field to search on.
 *
 * @param cache_key_value the key value to lookup
 * @param key_property_name the key property name used to access the key value
 * @param value_property_name the value property name
 * @return {*}
 */
ns.get_cache_data_from_key = function(cache_value,
                                              cache_field,
                                              data_field) {
    var cache = LP.cache.information_type_data;
    var key;
    for (key in cache) {
        if (cache.hasOwnProperty(key)) {
            if (cache[key][cache_field] === cache_value) {
                return cache[key][data_field];
            }
        }
    }
};


/**
 * The LP.cache for information type data is an object and needs to be sent to
 * the choicesource as a list of ordered data.
 *
 * @function cache_to_choicesource
 * @param {Object}
 *
 */
ns.cache_to_choicesource = function (cache) {
    var data = [];
    var key;
    for (key in cache) {
        if (cache.hasOwnProperty(key)) {
            data.push(cache[key]);
        }
    }
    // We need to order data based on the order attribute.
    data.sort(function(a, b) { return a.order - b.order; });
    return data;
};

/**
 * Update the privacy portlet to display the specified information type value.
 *
 * @param value
 */
ns.update_privacy_portlet = function(value) {
    var description = ns.get_cache_data_from_key(
        value, 'value', 'description');
    var desc_node = Y.one('#information-type-description');
    if (Y.Lang.isValue(desc_node)) {
        desc_node.set('text', description);
    }
    var summary = Y.one('#information-type-summary');
    var private_type = LP.cache.information_type_data[value].is_private;
    if (private_type) {
        summary.replaceClass('public', 'private');
    } else {
        summary.replaceClass('private', 'public');
    }
};


}, "0.1", {"requires": [
    "base", "oop", "node", "event", "io-base", "lp.mustache", "lp.app.choice",
    "lp.bugs.bugtask_index", "lp.ui.choiceedit"]});
