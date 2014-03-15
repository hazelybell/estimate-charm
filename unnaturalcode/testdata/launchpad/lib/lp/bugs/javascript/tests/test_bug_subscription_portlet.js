/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.bugs.subscription_portlet.test', function (Y) {
    var module = Y.lp.bugs.bugtask_index.portlets.subscription;

    // Notification levels.
    var DISCUSSION = 'Discussion';
    var DETAILS = 'Details';
    var LIFECYCLE = 'Lifecycle';

    function make_status_node() {
        var status = Y.Node.create('<div/>')
            .set('id', 'current_user_subscription')
            .append(Y.Node.create('<span/>'));
        Y.one('body').appendChild(status);
        return status;
    }

    function add_link_to_status_node() {
        var status = Y.one('#current_user_subscription');
        status.append(
            Y.Node.create('<a/>')
                .addClass('menu-link-subscription')
                .addClass('sprite')
                .addClass('modify')
                .addClass('edit')
                .set('href', 'http://example.com')
                .set('text', 'Example text')
            );
    }

    function make_mute_node() {
        var parent = Y.Node.create('<div/>')
            .set('id', 'mute-link-container')
            .append(Y.Node.create('<a/>')
                .addClass('menu-link-mute_subscription')
                .addClass(module.UNMUTED_CLASS)
                .set('text', 'This is a mute link')
                .set('href', 'http://www.example.com/+mute')
            );
        Y.one('body').appendChild(parent);
        return parent;
    }

    function setup_LP(bug_link) {
        window.LP = {
            cache: {
                notifications_text: {
                    not_only_other_subscription: 'You are',
                    only_other_subscription:
                        'You have subscriptions that may cause you to receive ' +
                        'notifications, but you are',
                    direct_all: 'subscribed to all notifications for this bug.',
                    direct_metadata:
                        'subscribed to all notifications except comments for ' +
                        'this bug.',
                    direct_lifecycle:
                        'subscribed to notifications when this bug is closed ' +
                        'or reopened.',
                    not_direct:
                        "not directly subscribed to this bug's notifications.",
                    muted:
                        'Your personal email notifications from this bug ' +
                        'are muted.'
                    },
                context: {web_link: 'http://example.com', bug_link: bug_link},
                other_subscription_notifications: false
                },
            links: {me: '~tweedledee'}
        };
    }

    function make_subscription(level) {
        if (Y.Lang.isUndefined(level)) {
            level = DISCUSSION;
        }
        window.LP.cache.subscription = {'bug_notification_level': level};
    }

    var tests = Y.namespace('lp.bugs.subscription_portlet.test');
    tests.suite = new Y.Test.Suite('bugs.subscription_portlet Tests');

    /**
     * Test update_subscription_status.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'Test update_subscription_status',

        setUp: function() {
            this.status_node = make_status_node();
            this.mute_node = make_mute_node();
            add_link_to_status_node();
            setup_LP();
        },

        tearDown: function() {
            this.status_node.remove();
            this.mute_node.remove();
            delete window.LP;
        },

        test_can_create_link: function() {
            this.status_node.one('a').remove();
            make_subscription();
            Y.Assert.isTrue(Y.Lang.isNull(this.status_node.one('a')));
            module.update_subscription_status();
            var link = this.status_node.one('a');
            Y.Assert.isTrue(Y.Lang.isValue(link));
            Y.Assert.isTrue(link.hasClass('menu-link-subscription'));
            Y.Assert.isTrue(link.hasClass('sprite'));
            Y.Assert.isTrue(link.hasClass('modify'));
            Y.Assert.isTrue(link.hasClass('edit'));
            Y.Assert.isTrue(link.hasClass('js-action'));
            Y.Assert.areEqual(
                // window.LP.context.web_link + '/+subscribe',
                'http://example.com/+subscribe',
                link.get('href'));
        },

        test_no_subscription: function() {
            module.update_subscription_status();
            Y.Assert.areEqual(
                'You are',
                this.status_node.one('span').get('text'));
            Y.Assert.areEqual(
                "not directly subscribed to this bug's notifications.",
                this.status_node.one('a').get('text'));
        },

        test_other_subscription: function() {
            window.LP.cache.other_subscription_notifications = true;
            module.update_subscription_status();
            Y.Assert.areEqual(
                'You have subscriptions that may cause you to receive ' +
                'notifications, but you are',
                this.status_node.one('span').get('text'));
            Y.Assert.areEqual(
                "not directly subscribed to this bug's notifications.",
                this.status_node.one('a').get('text'));
        },

        test_full_subscription: function() {
            make_subscription(DISCUSSION);
            module.update_subscription_status();
            Y.Assert.areEqual(
                'You are',
                this.status_node.one('span').get('text'));
            Y.Assert.areEqual(
                "subscribed to all notifications for this bug.",
                this.status_node.one('a').get('text'));
        },

        test_metadata_subscription: function() {
            make_subscription(DETAILS);
            module.update_subscription_status();
            Y.Assert.areEqual(
                'You are',
                this.status_node.one('span').get('text'));
            Y.Assert.areEqual(
                'subscribed to all notifications except comments for this bug.',
                this.status_node.one('a').get('text'));
        },

        test_lifecycle_subscription: function() {
            make_subscription(LIFECYCLE);
            module.update_subscription_status();
            Y.Assert.areEqual(
                'You are',
                this.status_node.one('span').get('text'));
            Y.Assert.areEqual(
                'subscribed to notifications when this bug is closed or ' +
                'reopened.',
                this.status_node.one('a').get('text'));
        },

        test_direct_subscription_has_precedence: function() {
            window.LP.cache.other_subscription_notifications = true;
            make_subscription(LIFECYCLE);
            module.update_subscription_status();
            Y.Assert.areEqual(
                'You are',
                this.status_node.one('span').get('text'));
            Y.Assert.areEqual(
                'subscribed to notifications when this bug is closed or ' +
                'reopened.',
                this.status_node.one('a').get('text'));
        },

        test_muted_subscription: function() {
            make_subscription(LIFECYCLE);
            this.mute_node.one('a').replaceClass(
                module.UNMUTED_CLASS, module.MUTED_CLASS);
            Y.Assert.isTrue(Y.Lang.isValue(this.status_node.one('a')));
            module.update_subscription_status();
            Y.Assert.areEqual(
                'Your personal email notifications from this bug are muted.',
                this.status_node.one('span').get('text'));
            Y.Assert.isFalse(Y.Lang.isValue(this.status_node.one('a')));
        }

    }));

    /**
     * Test setup_mute_link_handlers.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'Test setup_mute_link_handlers',

        setUp: function() {
            this.status_node = make_status_node();
            this.mute_node = make_mute_node();
            this.link = this.mute_node.one('a');
            add_link_to_status_node();
            this.bug_link = 'http://example.net/firefox/bug/1';
            setup_LP(this.bug_link);
            make_subscription(DISCUSSION);
            module.update_subscription_status();
            module.setup_mute_link_handlers();
            module._lp_client = new Y.lp.testing.helpers.LPClient();
            module._lp_client.named_post.args = [];
        },

        tearDown: function() {
            this.status_node.remove();
            this.mute_node.remove();
            delete window.LP;
            delete module._lp_client;
            var error_overlay = Y.one('.yui3-lazr-formoverlay');
            if (Y.Lang.isValue(error_overlay)) {
                error_overlay.remove();
            }
        },

        test_mute_success: function() {
            this.link.simulate('click');
            Y.Assert.areEqual(1, module._lp_client.received.length);
            Y.Assert.areEqual('named_post', module._lp_client.received[0][0]);
            var args = module._lp_client.received[0][1];
            Y.Assert.areEqual(this.bug_link, args[0]);
            Y.Assert.areEqual('mute', args[1]);
            Y.ObjectAssert.areEqual({}, args[2].parameters);
            Y.Assert.isTrue(this.link.hasClass(module.MUTED_CLASS));
            Y.Assert.isFalse(this.link.hasClass('spinner'));
            Y.Assert.isFalse(this.link.hasClass(module.UNMUTED_CLASS));
            Y.Assert.areEqual(
                'Your personal email notifications from this bug are muted.',
                this.status_node.one('span').get('text'));
        },

        test_unmute_success: function() {
            this.link.replaceClass(module.UNMUTED_CLASS, module.MUTED_CLASS);
            this.link.simulate('click');
            Y.Assert.areEqual(1, module._lp_client.received.length);
            Y.Assert.areEqual('named_post', module._lp_client.received[0][0]);
            var args = module._lp_client.received[0][1];
            Y.Assert.areEqual(this.bug_link, args[0]);
            Y.Assert.areEqual('unmute', args[1]);
            Y.ObjectAssert.areEqual({}, args[2].parameters);
            Y.Assert.isTrue(this.link.hasClass(module.UNMUTED_CLASS));
            Y.Assert.isFalse(this.link.hasClass('spinner'));
            Y.Assert.isFalse(this.link.hasClass(module.MUTED_CLASS));
            Y.Assert.areEqual(
                'You are',
                this.status_node.one('span').get('text'));
            Y.Assert.areEqual(
                "subscribed to all notifications for this bug.",
                this.status_node.one('a').get('text'));
        },

        test_mute_spinner_and_failure: function() {
            module._lp_client.named_post.fail = true;
            module._lp_client.named_post.args = [
                true,
                {status: 400, responseText: 'Rutebegas!'}];
            module._lp_client.named_post.halt = true;
            this.link.simulate('click');
            // Right now, this is as if we are waiting for the server to
            // reply. The link is spinning.
            Y.Assert.isTrue(this.link.hasClass('spinner'));
            Y.Assert.isFalse(this.link.hasClass(module.UNMUTED_CLASS));
            // Now the server replies with an error.
            module._lp_client.named_post.resume();
            // We have no spinner.
            Y.Assert.isTrue(this.link.hasClass(module.UNMUTED_CLASS));
            Y.Assert.isFalse(this.link.hasClass('spinner'));
            // The page has rendered the error overlay.
            var error_box = Y.one('.yui3-lazr-formoverlay-errors');
            Y.Assert.isTrue(Y.Lang.isValue(error_box));
        }
    }));

    /**
     * Test setup_subscription_link_handlers.
     */
    tests.suite.add(new Y.Test.Case({
        name: 'Test setup_subscription_link_handlers',

        setUp: function() {
            this.status_node = make_status_node();
            this.mute_node = make_mute_node();
            this.mute_link = this.mute_node.one('a');
            this.bug_link = 'http://example.net/firefox/bug/1';
            setup_LP(this.bug_link);
            module._lp_client = new Y.lp.testing.helpers.LPClient();
        },

        tearDown: function() {
            this.status_node.remove();
            this.mute_node.remove();
            delete window.LP;
            delete module._lp_client;
            var error_overlay = Y.one('.yui3-lazr-formoverlay');
            if (Y.Lang.isValue(error_overlay)) {
                error_overlay.remove();
            }
            var pretty_overlay = Y.one('.pretty-overlay-window');
            if (Y.Lang.isValue(pretty_overlay)) {
                pretty_overlay.remove();
            }
        },

        init: function(sub_level, has_other_subs, response) {
            if (Y.Lang.isValue(sub_level)) {
                make_subscription(sub_level);
            } else if (!has_other_subs) {
                this.mute_node.addClass('hidden');
            }
            window.LP.cache.other_subscription_notifications = has_other_subs;
            var args = [];
            if (Y.Lang.isValue(response)) {
                args = [
                    {getAttrs: function () {
                        return {bug_notification_level: response};
                    }}];
            }
            module._lp_client.named_post.args = args;
            module.update_subscription_status();
            module.setup_mute_link_handlers();
        },

        link: function() {
            return this.status_node.one('a');
        },

        test_overlay_add_subscription: function() {
            this.init(null, false);
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            // We have the "Add" title, not the "Change" title.
            Y.Assert.areEqual('Add a mail subscription for this bug',
                              overlay.one('h2').get('text'));
            // There is no status.
            Y.Assert.isFalse(Y.Lang.isValue(overlay.one('.subscription-status')));
            // The action links are visible.
            var action_links = overlay.one('.subscription-actions');
            Y.Assert.isFalse(action_links.one(
                '.Discussion a').hasClass('hidden'));
            Y.Assert.isFalse(action_links.one('.Details a').hasClass('hidden'));
            Y.Assert.isFalse(action_links.one('.Lifecycle a').hasClass('hidden'));
            // The "Remove" link is not present.
            Y.Assert.isFalse(Y.Lang.isValue(overlay.one('a.remove')));
            // The link is spinning.
            Y.Assert.isTrue(this.link().hasClass('spinner'));
            Y.Assert.isFalse(this.link().hasClass('edit'));
            // When we click on the "x," the overlay goes away, and the spinner
            // is gone.
            overlay.one('a.close-button').simulate('click');
            Y.Assert.isFalse(Y.Lang.isValue(Y.one('.pretty-overlay-window')));
            Y.Assert.isFalse(this.link().hasClass('spinner'));
            Y.Assert.isTrue(this.link().hasClass('edit'));
        },

        test_overlay_with_discussion_subscription: function() {
            // Starting with a DISCUSSION subscription, we get a "change" overlay.
            this.init(DISCUSSION, false);
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            // We have the "Change" title, not the "Add" title.
            Y.Assert.areEqual('Change your mail subscription for this bug',
                              overlay.one('h2').get('text'));
            // We show the Discussion status.
            var status = overlay.one('.subscription-status');
            Y.Assert.isFalse(overlay.one('span.Discussion').hasClass('hidden'));
            Y.Assert.isTrue(overlay.one('span.Details').hasClass('hidden'));
            Y.Assert.isTrue(overlay.one('span.Lifecycle').hasClass('hidden'));
            // The action links are visible except for Discussion.
            var action_links = overlay.one('.subscription-actions');
            Y.Assert.isTrue(action_links.one('.Discussion a').hasClass('hidden'));
            Y.Assert.isFalse(action_links.one('.Details a').hasClass('hidden'));
            Y.Assert.isFalse(action_links.one('.Lifecycle a').hasClass('hidden'));
            // We have a remove link.
            Y.Assert.isTrue(Y.Lang.isValue(overlay.one('a.remove')));
            Y.Assert.areEqual(
                'Remove your direct subscription',
                overlay.one('div.subscription-actions+div').get('text'));
        },

        test_overlay_with_details_subscription: function() {
            // Test overlay with existing DETAILS subscription.
            this.init(DETAILS, true);
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            // We show the Lifecycle status.
            var status = overlay.one('.subscription-status');
            Y.Assert.isTrue(overlay.one('span.Discussion').hasClass('hidden'));
            Y.Assert.isFalse(overlay.one('span.Details').hasClass('hidden'));
            Y.Assert.isTrue(overlay.one('span.Lifecycle').hasClass('hidden'));
            // The action links are visible except for Lifecycle.
            var action_links = overlay.one('.subscription-actions');
            Y.Assert.isFalse(action_links.one(
                '.Discussion a').hasClass('hidden'));
            Y.Assert.isTrue(action_links.one('.Details a').hasClass('hidden'));
            Y.Assert.isFalse(action_links.one('.Lifecycle a').hasClass('hidden'));
            // We have a remove link.
            Y.Assert.isTrue(Y.Lang.isValue(overlay.one('a.remove')));
            Y.Assert.areEqual(
                'Remove your direct subscription',
                overlay.one('div.subscription-actions+div').get('text'));
        },

        test_overlay_with_lifecycle_subscription: function() {
            // Test overlay with existing LIFECYCLE subscription.
            this.init(LIFECYCLE, true);
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            // We show the Lifecycle status.
            var status = overlay.one('.subscription-status');
            Y.Assert.isTrue(overlay.one('span.Discussion').hasClass('hidden'));
            Y.Assert.isTrue(overlay.one('span.Details').hasClass('hidden'));
            Y.Assert.isFalse(overlay.one('span.Lifecycle').hasClass('hidden'));
            // The action links are visible except for Lifecycle.
            var action_links = overlay.one('.subscription-actions');
            Y.Assert.isFalse(action_links.one(
                '.Discussion a').hasClass('hidden'));
            Y.Assert.isFalse(action_links.one('.Details a').hasClass('hidden'));
            Y.Assert.isTrue(action_links.one('.Lifecycle a').hasClass('hidden'));
            // We have a remove link.
            Y.Assert.isTrue(Y.Lang.isValue(overlay.one('a.remove')));
            Y.Assert.areEqual(
                'Remove your direct subscription',
                overlay.one('div.subscription-actions+div').get('text'));
        },

        test_subscribe_discussion: function() {
            this.init(null, false, DISCUSSION);
            // The mute node is hidden initially.
            Y.Assert.isTrue(this.mute_node.hasClass('hidden'));
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            overlay.one('.subscription-actions .Discussion a').simulate('click');
            // The overlay has been destroyed, and the spinner is gone.
            Y.Assert.isFalse(Y.Lang.isValue(Y.one('.pretty-overlay-window')));
            Y.Assert.isFalse(this.link().hasClass('spinner'));
            // We got an appropriate call to the webservice.
            Y.Assert.areEqual('named_post', module._lp_client.received[0][0]);
            var args = module._lp_client.received[0][1];
            Y.Assert.areEqual(this.bug_link, args[0]);
            Y.Assert.areEqual('subscribe', args[1]);
            Y.ObjectAssert.areEqual({person: '~tweedledee', level: DISCUSSION},
                                    args[2].parameters);
            // There is now a subscription object in the cache.
            Y.Assert.isTrue(Y.Lang.isValue(window.LP.cache.subscription));
            // The mute node is not hidden.
            Y.Assert.isFalse(this.mute_node.hasClass('hidden'));
            // The link has updated its text.
            Y.Assert.areEqual(
                "You are subscribed to all notifications for this bug.",
                this.status_node.get('text'));
        },

        test_subscribe_details: function() {
            this.init(null, false, DETAILS);
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            overlay.one('.subscription-actions .Details a').simulate('click');
            // We got an appropriate call to the webservice.
            Y.Assert.areEqual('named_post', module._lp_client.received[0][0]);
            var args = module._lp_client.received[0][1];
            Y.Assert.areEqual(this.bug_link, args[0]);
            Y.Assert.areEqual('subscribe', args[1]);
            Y.ObjectAssert.areEqual({person: '~tweedledee', level: DETAILS},
                                    args[2].parameters);
            // The link has updated its text.
            Y.Assert.areEqual(
                "You are subscribed to all notifications except comments for "+
                "this bug.",
                this.status_node.get('text'));
        },

        test_subscribe_lifecycle: function() {
            this.init(null, false, LIFECYCLE);
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            overlay.one('.subscription-actions .Lifecycle a').simulate('click');
            // We got an appropriate call to the webservice.
            Y.Assert.areEqual('named_post', module._lp_client.received[0][0]);
            var args = module._lp_client.received[0][1];
            Y.Assert.areEqual(this.bug_link, args[0]);
            Y.Assert.areEqual('subscribe', args[1]);
            Y.ObjectAssert.areEqual({person: '~tweedledee', level: LIFECYCLE},
                                    args[2].parameters);
            // The link has updated its text.
            Y.Assert.areEqual(
                "You are subscribed to notifications when this bug is closed "+
                "or reopened.",
                this.status_node.get('text'));
        },

        test_unsubscribe: function() {
            this.init(LIFECYCLE, false);
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            overlay.one('a.remove').simulate('click');
            // There is no warning.
            var warning = overlay.one('.private-bug-warning');
            Y.Assert.isNull(warning);
            // We got an appropriate call to the webservice.
            Y.Assert.areEqual('named_post', module._lp_client.received[0][0]);
            var args = module._lp_client.received[0][1];
            Y.Assert.areEqual(this.bug_link, args[0]);
            Y.Assert.areEqual('unsubscribe', args[1]);
            Y.ObjectAssert.areEqual({}, args[2].parameters);
            // The overlay has been destroyed, and the spinner is gone.
            Y.Assert.isFalse(Y.Lang.isValue(Y.one('.pretty-overlay-window')));
            Y.Assert.isFalse(this.link().hasClass('spinner'));
            // The mute node is hidden.
            Y.Assert.isTrue(this.mute_node.hasClass('hidden'));
            // The link has updated its text.
            Y.Assert.areEqual(
                "You are not directly subscribed to this bug's notifications.",
                this.status_node.get('text'));
        },

        test_unsubscribe_from_private_bug: function() {
            this.init(LIFECYCLE, false);
            window.LP.cache.bug_is_private = true;
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            overlay.one('a.remove').simulate('click');
            // The overlay now has a warning.
            var warning = overlay.one('.private-bug-warning');
            Y.Assert.isTrue(Y.Lang.isValue(warning));
            // Find and click the OK button.
            var ok_btn = warning.one('.ok-btn');
            ok_btn.simulate('click');
            // We got an appropriate call to the webservice.
            Y.Assert.areEqual('named_post', module._lp_client.received[0][0]);
            var args = module._lp_client.received[0][1];
            Y.Assert.areEqual(this.bug_link, args[0]);
            Y.Assert.areEqual('unsubscribe', args[1]);
            Y.ObjectAssert.areEqual({}, args[2].parameters);
            // The overlay has been destroyed, and the spinner is gone.
            Y.Assert.isFalse(Y.Lang.isValue(Y.one('.pretty-overlay-window')));
            Y.Assert.isFalse(this.link().hasClass('spinner'));
        },

        test_unsubscribe_from_private_bug_cancel: function() {
            this.init(LIFECYCLE, false);
            window.LP.cache.bug_is_private = true;
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            overlay.one('a.remove').simulate('click');
            // The overlay now has a warning.
            var warning = overlay.one('.private-bug-warning');
            Y.Assert.isTrue(Y.Lang.isValue(warning));
            // Find and click the Cancel button.
            var cancel_btn = warning.one('.cancel-btn');
            cancel_btn.simulate('click');
            // The warning is gone.
            warning = overlay.one('.private-bug-warning');
            Y.Assert.isNull(warning);
        },

        test_unsubscribe_with_other: function() {
            this.init(LIFECYCLE, true);
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            overlay.one('a.remove').simulate('click');
            // We got an appropriate call to the webservice.
            Y.Assert.areEqual('named_post', module._lp_client.received[0][0]);
            var args = module._lp_client.received[0][1];
            Y.Assert.areEqual(this.bug_link, args[0]);
            Y.Assert.areEqual('unsubscribe', args[1]);
            Y.ObjectAssert.areEqual({}, args[2].parameters);
            // The overlay has been destroyed, and the spinner is gone.
            Y.Assert.isFalse(Y.Lang.isValue(Y.one('.pretty-overlay-window')));
            Y.Assert.isFalse(this.link().hasClass('spinner'));
            // The mute node is not hidden.
            Y.Assert.isFalse(this.mute_node.hasClass('hidden'));
            // The link has updated its text.
            Y.Assert.areEqual(
                "You have subscriptions that may cause you to receive "+
                "notifications, but you are not directly subscribed to this "+
                "bug's notifications.",
                this.status_node.get('text'));
        },

        test_io_spinner_and_error: function() {
            this.init(LIFECYCLE, true);
            module._lp_client.named_post.fail = true;
            module._lp_client.named_post.args = [
                true,
                {status: 400, responseText: 'Rutebegas!'}];
            module._lp_client.named_post.halt = true;
            this.link().simulate('click');
            var overlay = Y.one('.pretty-overlay-window');
            var unsub = overlay.one('a.remove');
            unsub.simulate('click');
            // Right now, this is as if we are waiting for the server to
            // reply. The link is spinning.
            Y.Assert.isTrue(unsub.hasClass('spinner'));
            Y.Assert.isFalse(unsub.hasClass('remove'));
            // Now the server replies with an error.
            module._lp_client.named_post.resume();
            // We have no spinner.
            Y.Assert.isTrue(unsub.hasClass('remove'));
            Y.Assert.isFalse(unsub.hasClass('spinner'));
            // The page has rendered the error overlay.
            var error_box = Y.one('.yui3-lazr-formoverlay-errors');
            Y.Assert.isTrue(Y.Lang.isValue(error_box));
            // The overlay is still hanging around too, as expected, but for
            // better or worse (popup-on-popup is not the best UI).
            Y.Assert.isTrue(Y.Lang.isValue(Y.one('.pretty-overlay-window')));
        }
    }));

}, '0.1', {
    'requires': ['test', 'lp.testing.helpers', 'test-console',
        'lp.bugs.bugtask_index.portlets.subscription', 'node-event-simulate']
});
