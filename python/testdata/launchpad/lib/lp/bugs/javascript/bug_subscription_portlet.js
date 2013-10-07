/* Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Provide information and actions on all bug subscriptions a person holds.
 *
 * @module bugs
 * @submodule bugtask_index_subscription_portlet
 */

YUI.add('lp.bugs.bugtask_index.portlets.subscription', function(Y) {

var namespace = Y.namespace('lp.bugs.bugtask_index.portlets.subscription');

// We begin with fairly generic helpers for the main functions.

/*
 * Internal helper to build tags.
 */
function tag(name) {
    return Y.Node.create('<'+name+'/>');
}

/*
 * Internal helper to build sprite link tags.
 */
function make_link(text, css_class) {
    return tag('a')
        .set('href', '#')
        .addClass('sprite')
        .addClass('modify')
        .addClass(css_class)
        .set('text', text);
}

/*
 * Hack to work around YUI whitespace trim behavior. :-(
 */
function ws() {
    return Y.Node.create('<span> </span>');
}

/*
 * This returns a launchpad client.  It is factored in a way to be a hook
 * point for tests.
 */
function lp_client() {
    if (!Y.Lang.isValue(namespace._lp_client)) {
        namespace._lp_client = new Y.lp.client.Launchpad();
    }
    return namespace._lp_client;
}

// Now we are ready for code that more directly does what we want here.

var MUTED_CLASS = namespace.MUTED_CLASS = 'unmute';
var UNMUTED_CLASS = namespace.UNMUTED_CLASS = 'mute';

/*
 * Update the text and link at the top of the subscription portlet.
 */
function update_subscription_status(skip_animation) {
    var status = Y.one('#current_user_subscription');
    var span = status.one('span');
    var whitespace = status.one('span+span');
    var link = status.one('a');
    var mute_link = Y.one('.menu-link-mute_subscription');
    var is_muted = (Y.Lang.isValue(mute_link) &&
                    mute_link.hasClass(MUTED_CLASS));
    var messages = LP.cache.notifications_text;
    if (is_muted) {
        span.set('text', messages.muted);
        if (Y.Lang.isValue(link)) {
            link.remove();
        }
        if (Y.Lang.isValue(whitespace)) {
            whitespace.remove(); // Tests can be persnickety.
        }
    } else {
        if (!Y.Lang.isValue(link)) {
            if (!Y.Lang.isValue(whitespace)) {
                status.appendChild(ws());
            }
            link = tag('a')
                .addClass('menu-link-subscription')
                .addClass('sprite')
                .addClass('modify')
                .addClass('edit');
            link.set('href', LP.cache.context.web_link + '/+subscribe');
            status.appendChild(link);
            setup_subscription_link_handlers();
        }
        span.set('text', messages.not_only_other_subscription);
        if (Y.Lang.isUndefined(LP.cache.subscription)) {
            if (LP.cache.other_subscription_notifications) {
                span.set('text', messages.only_other_subscription);
            }
            link.set('text', messages.not_direct);
        } else {
            switch (LP.cache.subscription.bug_notification_level) {
                case 'Discussion':
                    link.set('text', messages.direct_all);
                    break;
                case 'Details':
                    link.set('text', messages.direct_metadata);
                    break;
                case 'Lifecycle':
                    link.set('text', messages.direct_lifecycle);
                    break;
                default:
                    Y.error(
                        'Programmer error: unknown bug notification level: '+
                        LP.cache.subscription.bug_notification_level);
            }
        }
    }
    if(!Y.Lang.isBoolean(skip_animation) || !skip_animation) {
        Y.lp.anim.green_flash({ node: status }).run();
    }
}
namespace.update_subscription_status = update_subscription_status;

/*
 * Set up the handlers for the mute / unmute link.
 */
function setup_mute_link_handlers() {
    var link = Y.one('.menu-link-mute_subscription');
    if (Y.Lang.isNull(link)) {
        return;
    }
    link.addClass('js-action');
    link.on('click', function (e) {
        e.halt();
        var subscribe_link = Y.one('#current_user_subscription a');
        if (link.hasClass('spinner') ||
            (Y.Lang.isValue(subscribe_link) &&
             subscribe_link.hasClass('spinner'))) {
            return;
        }
        var is_muted = link.hasClass(MUTED_CLASS);
        var method_name, current_class, destination_class, destination_text;
        if (is_muted) {
            method_name = 'unmute';
            current_class = MUTED_CLASS;
            destination_class = UNMUTED_CLASS;
            destination_text = 'Mute bug mail';
        } else {
            method_name = 'mute';
            current_class = UNMUTED_CLASS;
            destination_class = MUTED_CLASS;
            destination_text = 'Unmute bug mail';
        }
        link.replaceClass(current_class, 'spinner');
        var handler = new Y.lp.client.ErrorHandler();
        handler.showError = function(error_msg) {
            Y.lp.app.errors.display_error(link.get('parentNode'), error_msg);
        };
        handler.clearProgressUI = function () {
            link.replaceClass('spinner', current_class);
        };
        var config = {
            on: {
                success: function(response) {
                    link.replaceClass('spinner', destination_class);
                    link.set('text', destination_text);
                    update_subscription_status();
                    Y.lp.anim.green_flash(
                        { node: link.get('parentNode') }).run();
                },
                failure: handler.getFailureHandler()
            },
            parameters: {}
        };
        lp_client().named_post(
            LP.cache.context.bug_link, method_name, config);
    });
}
namespace.setup_mute_link_handlers = setup_mute_link_handlers;

/*
 * Set up the handler for the subscription link.
 */
function setup_subscription_link_handlers() {
    // First we determine if we should bother to run.
    var link = Y.one('#current_user_subscription a');
    if (!Y.Lang.isValue(link)) {
        return;
    }
    // Mark the link as in-page.
    link.addClass('js-action');
    // Make some helpers.
    var mute_link = Y.one('.menu-link-mute_subscription');
    var mute_div = mute_link.get('parentNode');
    // We define the overlay early so the functions that we declare here
    // can access it.  It's effectively a "global" for clean_up and for
    // the functions generated by make_action, below.
    var overlay;
    // This function encapsulates what we need to do whenever we stop
    // using the overlay, whether because of a successful action or because
    // of cancelling the overlay.
    var clean_up = function() {
        overlay.hide();
        overlay.destroy();
        link.replaceClass('spinner', 'edit');
    };
    // The on-click handler for make_action nodes.
    var make_action_on_click = function (
        e, method_name, css_class, parameters) {
        var active_link = e.currentTarget;
        active_link.replaceClass(css_class, 'spinner');
        var handler = new Y.lp.client.ErrorHandler();
        handler.showError = function(error_msg) {
            Y.lp.app.errors.display_error(
                active_link.get('parentNode'), error_msg);
        };
        handler.clearProgressUI = function () {
            active_link.replaceClass('spinner', css_class);
        };
        var config = {
            on: {
                success: function(response) {
                    if (Y.Lang.isValue(response)) {
                        // This is a subscription.  Update the cache.
                        LP.cache.subscription = response.getAttrs();
                    }
                    if (method_name === 'mute') {
                        // Special case: update main mute link.
                        mute_link.replaceClass(
                            UNMUTED_CLASS, MUTED_CLASS);
                        mute_link.set('text', 'Unmute bug mail');
                        Y.lp.anim.green_flash(
                            { node: mute_link.get('parentNode') }).run();
                    } else if (method_name === 'unsubscribe') {
                        // Special case: delete cache.
                        delete LP.cache.subscription;
                        if (!LP.cache.other_subscription_notifications) {
                            // Special case: hide mute link.
                            mute_div.addClass('hidden');
                        }
                    } else if (method_name === 'subscribe') {
                        // Special case: reveal mute link.
                        mute_div.removeClass('hidden');
                    }
                    active_link.replaceClass('spinner', css_class);
                    update_subscription_status();
                    clean_up();
                },
                failure: handler.getFailureHandler()
            },
            parameters: parameters
        };
        lp_client().named_post(
            LP.cache.context.bug_link, method_name, config);
    };
    // The make_action function is the workhorse for creating all the
    // JavaScript action links we need. Given the `text` that the link
    // should display, the `class` name to show the appropriate sprite,
    // the `method_name` to call on the server, and the `parameters` to
    // send across, it returns a link node with the click handler properly
    // set.
    var make_action = function(text, css_class, method_name, parameters) {
        result = make_link(text, css_class)
            .addClass('js-action');
        result.on('click', function (e) {
            e.halt();
            var method_call = function() {
                make_action_on_click(e, method_name, css_class, parameters);
            };
            var is_private = Y.Lang.isBoolean(LP.cache.bug_is_private) &&
                                LP.cache.bug_is_private;
            var private_bug_warning = function() {
                var private_bug_warning_node = Y.Node.create(
                    ['<div class="private-bug-warning"><p>You will not ',
                    'have access to this bug or any of its pages if you ',
                    'unsubscribe. If you want to stop emails, choose the ',
                    '"Mute bug mail" option.</p>',
                    '<p>Do you really want to unsubscribe from this bug?',
                    '</p><div class="extra-form-buttons">',
                    '<button class="ok-btn" ',
                    'type="submit">Unsubscribe</button>',
                    '<button class="cancel-btn" ',
                    'type="button">Cancel</button></div></div>'].join(''));
                var remove_div = Y.one('.remove-direct-subscription');
                var ok_btn = private_bug_warning_node.one('.ok-btn');
                ok_btn.on('click', function (internal_e) {
                    e.halt();
                    method_call();
                });
                var cancel_btn = private_bug_warning_node.one(
                    '.cancel-btn');
                cancel_btn.on('click', function() {
                    private_bug_warning_node.remove();
                });
                remove_div.insert(private_bug_warning_node, 'after');
            };
            if (is_private && method_name === 'unsubscribe') {
                private_bug_warning();
            } else {
                method_call();
            }
            });
        return result;
    };
    // Now we start building the nodes that will be used within the overlay.
    // We reuse these, so we create them once and then the main subscription
    // click handler updates and assembles them.
    // The first that we create is the header node.  The text alternates
    // depending on circumstance, so we set that in the main click handler.
    var header = tag('h2')
        .setStyle('display', 'block')
        .setStyle('overflow', 'hidden')
        .setStyle('textOverflow', 'ellipsis')
        .setStyle('whiteSpace', 'nowrap')
        .setStyle('width', '21em');
    // This is the node that description of the current subscription
    // status.
    var status_node = tag('div')
        .addClass('subscription-status')
        .setStyle('margin-top', '1em')
        .append(tag('span')
            .addClass('Discussion')
            .set('text',
                 'You currently receive all emails about this bug.')
        ).append(tag('span')
            .addClass('Details')
            .set('text',
                 'You currently receive all emails about this bug '+
                 'except comments.')
        ).append(tag('span')
            .addClass('Lifecycle')
            .set('text',
                 'You currently only receive email when this bug is closed.')
        );
    // This is the node that contains the links to subscribe at a certain
    // level.
    var actions_node = tag('div')
        .addClass('subscription-actions')
        .setStyle('margin-top', '1em')
        .append(tag('div')
            .addClass('Discussion')
            .append(make_action(
                'Receive all emails about this bug', 'edit',
                'subscribe', {person: LP.links.me, level: 'Discussion'})
            )
        ).append(tag('div')
            .addClass('Details')
            .append(make_action(
                'Receive all emails about this bug except comments', 'edit',
                'subscribe', {person: LP.links.me, level: 'Details'})
            )
        ).append(tag('div')
            .addClass('Lifecycle')
            .append(make_action(
                'Only receive email when this bug is closed', 'edit',
                'subscribe', {person: LP.links.me, level: 'Lifecycle'})
            )
        );
    // The last node we create is the node that includes the ability to
    // unsubscribe.  As you'd expect, this is only pertinent if the user
    // has an existing direct subscription.
    var unsubscribe_node = tag('div')
        .setStyle('margin-top', '1.5em')
        .addClass('remove-direct-subscription')
        .append(make_action(
            'Remove your direct subscription', 'remove',
            'unsubscribe', {})
        );
    // Now we have all of the nodes ready.  We can define our click handler.
    link.on('click', function (e) {
        e.halt();
        // Don't start something if something else related is already in
        // progress.  The "link.hasClass('spinner')" will probably never be
        // true because the overlay blocks access to the rest of the page
        // while it is active.  The mute_link might be active, though.
        if (link.hasClass('spinner') || mute_link.hasClass('spinner')) {
            return;
        }
        link.replaceClass('edit', 'spinner');
        var body = tag('div');
        // Set up all level links to be visible, and all "currently
        // subscribed" spans to be hidden.  This is what we need if we are
        // creating a new subscription.  If not, we will flip the right switch
        // below.
        actions_node.all('a').removeClass('hidden');
        status_node.all('span').addClass('hidden');
        if (Y.Lang.isValue(LP.cache.subscription)) {
            // We are going to edit a subscription.
            header.set('text',
                       'Change your mail subscription for this bug');
            var class_id = '.'+LP.cache.subscription.bug_notification_level;
            actions_node.one(class_id+' a').addClass('hidden');
            status_node.one('span'+class_id).removeClass('hidden');
            body.append(status_node)
                .append(actions_node)
                .append(unsubscribe_node);
        } else {
            // We are going to create a new subscription.
            header.set('text',
                       'Add a mail subscription for this bug');
            body.append(actions_node);
        }
        // Now we just make an overlay and show it, and we are done.
        overlay = new Y.lp.ui.PrettyOverlay({
            headerContent: header,
            bodyContent: body,
            visible: false,
            centered: true
        });
        overlay.on('cancel', clean_up);
        overlay.render();
        overlay.show();
    });
}
namespace.setup_subscription_link_handlers = setup_subscription_link_handlers;

namespace.initialize = function () {
    if (Y.Lang.isUndefined(LP.links.me)) {
        return;
    }
    setup_subscription_link_handlers();
    setup_mute_link_handlers();
};

}, '0.1', {requires: [
    'dom', 'event', 'node', 'substitute', 'lp.ui.effects', 'lp.ui.overlay',
    'lp.app.errors', 'lp.client'
]});
