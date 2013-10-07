/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Setup for managing subscribers list for bugs.
 *
 * @module bugs
 * @submodule subscribers
 */

YUI.add('lp.bugs.subscribers', function(Y) {

var namespace = Y.namespace('lp.bugs.subscribers');

/**
 * Possible subscriber levels with descriptive headers for
 * sections that will hold them.
 *
 * These match BugNotificationLevel enum options (as defined in
 * lib/lp/bugs/enums.py).
 */
var subscriber_levels = {
    'Discussion': 'Notified of all changes',
    'Details': 'Notified of all changes except comments',
    'Lifecycle': 'Notified when the bug is closed or reopened',
    'Maybe': 'May be notified'
};

/**
 * Order of subscribers sections.
 */
var subscriber_level_order = ['Discussion', 'Details', 'Lifecycle', 'Maybe'];


/**
 * Create the SubscribersLoader instance which will load subscribers for
 * a bug and put them in the web page.
 *
 * @param config {Object} Defines `container_box' CSS selector for the
 *     SubscribersList container box, `context' holding context metadata (at
 *     least with `web_link') and `subscribers_details_view' holding
 *     a relative URI to load subscribers' details from.
 */
function createBugSubscribersLoader(config) {
    var url_data = LP.cache.subscribers_portlet_url_data;
    if (!Y.Lang.isValue(url_data)) {
        url_data = { self_link: LP.cache.context.bug_link,
                    web_link: LP.cache.context.web_link };
    }
    config.subscriber_levels = subscriber_levels;
    config.subscriber_level_order = subscriber_level_order;
    config.context = url_data;
    config.subscribe_someone_else_level = 'Discussion';
    config.default_subscriber_level = 'Maybe';
    var module = Y.lp.app.subscribers.subscribers_list;
    return new module.SubscribersLoader(config);
}
namespace.createBugSubscribersLoader = createBugSubscribersLoader;

}, "0.1", {"requires": ["lp.app.subscribers.subscribers_list"]});
