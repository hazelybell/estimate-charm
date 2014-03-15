/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Classes for managing subscribers list for entities (bugs, questions etc).
 *
 * Entities must expose two specific web service methods:
 *   - subscribe(person)
 *   - unsubscribe(person)
 *
 * Two classes are provided:
 *
 *   - SubscribersList: deals with node construction/removal for the
 *     list of subscribers, including activity indication and animations.
 *
 *     Public methods to use:
 *       startActivity, stopActivity,
 *       addSubscriber, removeSubscriber, indicateSubscriberActivity,
 *       stopSubscriberActivity, addUnsubscribeAction
 *
 *   - SubscribersLoader: loads subscribers from LP, allows subscribing
 *     someone else and sets unsubscribe actions where appropriate.
 *     Depends on the SubscribersList to do the actual node construction.
 *
 *     No public methods are available: it all gets run from the constructor.
 *
 * @module app.subscribers
 * @submodule subscribers_list
 */

YUI.add('lp.app.subscribers.subscribers_list', function(Y) {

var namespace = Y.namespace('lp.app.subscribers.subscribers_list');

var CSS_CLASSES = {
    section : 'subscribers-section',
    list: 'subscribers-list',
    subscriber: 'subscriber',
    no_subscribers: 'no-subscribers-indicator',
    activity: 'global-activity-indicator',
    activity_text: 'global-activity-text',
    subscriber_activity: 'subscriber-activity-indicator',
    actions: 'subscriber-actions',
    unsubscribe: 'unsubscribe-action'
};

var MAX_DISPLAYNAME_LENGTH = 20;

var CONFIG_DEFAULTS = {
    default_subscriber_level: '',
    subscribers_label: 'subscribers',
    subscribe_label:'Subscribe',
    unsubscribe_label:'Unsubscribe',
    subscribe_api: 'subscribe',
    unsubscribe_api: 'unsubscribe'
};

/**
 * Load subscribers for an entity from Launchpad and put them in the web page.
 *
 * Uses SubscribersList class to manage actual node construction
 * and handling, and is mostly in charge of communication with Launchpad.
 *
 * Loading is triggered automatically on instance construction.
 *
 * @class SubscribersLoader
 * @param config {Object} Defines `container_box' CSS selector for the
 *     SubscribersList container box, `context' holding context metadata (at
 *     least with `web_link') and `subscribers_details_view' holding
 *     a relative URI to load subscribers' details from.
 */
function SubscribersLoader(config) {
    if (!Y.Lang.isValue(config.subscriber_levels)) {
        Y.error("No subscriber levels specified in `config'.");
    }
    var config_var;
    for (config_var in CONFIG_DEFAULTS) {
        if (CONFIG_DEFAULTS.hasOwnProperty(config_var)) {
            if (Y.Lang.isString(config[config_var])) {
                this[config_var] = config[config_var];
            } else {
                this[config_var] = CONFIG_DEFAULTS[config_var];
                config[config_var] = CONFIG_DEFAULTS[config_var];
            }
        }
    }
    this.subscriber_levels = config.subscriber_levels;
    var sl = this.subscribers_list = new SubscribersList(config);
    sl.container_node.setData('subscribers_loader', this);

    if (!Y.Lang.isValue(config.context) ||
        !Y.Lang.isString(config.context.web_link)) {
        Y.error(
            "No context specified in `config' or " +
            "context.web_link is invalid.");
    }
    this.context = config.context;

    // Get SubscribersWithDetails portlet link to load subscribers from.
    if (!Y.Lang.isString(config.subscribers_details_view)) {
        Y.error(
            "No config.subscribers_details_view specified to load " +
                "other subscribers from.");
    }
    this.subscribers_portlet_uri = (
        this.context.web_link + config.subscribers_details_view);

    this.error_handler = new Y.lp.client.FormErrorHandler();
    this.error_handler.showError = function (error_msg) {
        sl.stopActivity("Problem loading subscribers. " + error_msg);
    };

    // Allow tests to override lp_client.
    if (Y.Lang.isValue(config.lp_client)) {
        this.lp_client = config.lp_client;
    } else {
        this.lp_client = new Y.lp.client.Launchpad();
    }

    // Check for CSS class for the link to subscribe someone me.
    if (Y.Lang.isString(config.subscribe_me_link)) {
        if (!Y.Lang.isString(config.subscribe_me_level)) {
            Y.error("No config.subscribe_me_level specified.");
        }
        this.subscribe_me_link = config.subscribe_me_link;
        this.subscribe_me_level = config.subscribe_me_level;

        // The title text for the Subscribe me link.
        this.subscribed_help_text = '';
        if (Y.Lang.isString(config.subscribed_help_text)) {
            this.subscribed_help_text = config.subscribed_help_text;
        }
        this.unsubscribed_help_text = '';
        if (Y.Lang.isString(config.unsubscribed_help_text)) {
            this.unsubscribed_help_text = config.unsubscribed_help_text;
        }
    }
    // Should the current user be shown in the subscribers list if they are in
    // the subscriber results or use the Subscribe Me link.
    this.display_me_in_list = false;
    if (Y.Lang.isBoolean(config.display_me_in_list)) {
        this.display_me_in_list = config.display_me_in_list;
    }

    this._unsubscribe_me = undefined;
    this._loadSubscribers();

    // Check for CSS class for the link to subscribe someone else.
    if (Y.Lang.isString(config.subscribe_someone_else_link)) {
        if (!Y.Lang.isString(config.subscribe_someone_else_level)) {
            Y.error("No config.subscribe_someone_else_level specified.");
        }
        this.subscribe_someone_else_link = config.subscribe_someone_else_link;
        this._setupSubscribeSomeoneElse(config.subscribe_someone_else_level);
    }
}
namespace.SubscribersLoader = SubscribersLoader;

/**
 * Return true if the subscriber is the logged in user.
 * @method _subscriber_is_me
 * @param subscriber
 */
SubscribersLoader.prototype._subscriber_is_me = function(subscriber) {
    return subscriber.self_link.match(LP.links.me + "$") !== null;
};

/**
 * Adds a subscriber along with the unsubscribe callback if needed.
 *
 * @method _addSubscriber
 * @param subscriber {Object} A common subscriber object passed
 *     directly to SubscribersList.addSubscriber().
 *     If subscriber.can_edit === true, adds an unsubscribe callback
 *     as returned by this._getUnsubscribeCallback().
 * @param level {String} A subscription level (one of
 *     subscriber_levels values).  When level doesn't match any of the
 *     supported levels, default_subscriber_level is used instead.
 */
SubscribersLoader.prototype._addSubscriber = function(subscriber, level) {
    if (!this.subscriber_levels.hasOwnProperty(level)) {
        // Default to 'subscribed at unknown level' for unrecognized
        // subscription levels.
        level = this.default_subscriber_level;
    }
    var unsubscribe_callback = this._getUnsubscribeCallback();

    var is_me = this._subscriber_is_me(subscriber);
    if (is_me) {
        this._unsubscribe_me = function() {
            unsubscribe_callback(this.subscribers_list, subscriber);
        };
    }
    if (this._updateSubscribersList(subscriber)) {
        if (subscriber.can_edit === true) {
            this.subscribers_list.addSubscriber(subscriber, level, 
            false, {
                unsubscribe_callback: unsubscribe_callback});
        } else {
            this.subscribers_list.addSubscriber(subscriber, level, false);
        }
    }
};

/**
 * Load subscribers from the list of subscribers and add subscriber rows
 * for them.
 *
 * @method _loadSubscribersFromList
 * @param details {List} List of subscribers with their subscription levels.
 */
SubscribersLoader.prototype._loadSubscribersFromList = function(details) {
    if (!Y.Lang.isArray(details)) {
        Y.error('Got non-array "'+ details +
                '" in _loadSubscribersFromList().');
    }
    this.subscribers_list.container_node.empty();
    var index, subscriber;
    for (index = 0; index < details.length; index++) {
        subscriber = details[index].subscriber;
        if (!Y.Lang.isObject(details[index])) {
            Y.error('Subscriber details at index ' + index + ' (' +
                    details[index] + ') are not an object.');
        }
        this._addSubscriber(subscriber,
                            details[index].subscription_level);
    }
};

/**
 * Load subscribers from the JSON portlet with details, adding them
 * to the actual subscribers list managed by this class.
 *
 * JSON string in the portlet should be of the following form:
 *
 *     [ { "subscriber": {
 *           "name": "foobar",
 *           "display_name": "Foo Bar",
 *           "can_edit": true/false,
 *           "is_team": true/false,
 *           "web_link": "https://launchpad.dev/~foobar",
 *           "display_subscribed_by": "Matt Zimmerman (mdz)"
 *           },
 *         "subscription_level": "Details"},
 *       { "subscriber": ... }
 *     ]
 * JSON itself is parsed by lp_client.get().
 *
 * Uses SubscribersList startActivity/stopActivity methods to indicate
 * progress and/or any errors it hits.
 *
 * @method _loadSubscribers
 */
SubscribersLoader.prototype._loadSubscribers = function() {
    var sl = this.subscribers_list;
    var loader = this;

    // Fetch the person and add a subscription.
    var on_success = function(subscribers) {
        loader._loadSubscribersFromList(subscribers);
        // We may need to set up the subscribe me link.
        // This has to be done after subscribers have been loaded so that we
        // know if the current user is currently subscribed.
        if (Y.Lang.isString(loader.subscribe_me_link)) {
            loader._setupSubscribeMe();
        }
        loader.subscribers_list.stopActivity();
    };

    var config = { on: {
        success: on_success,
        failure: this.error_handler.getFailureHandler()
    } };

    sl.startActivity("Loading " + this.subscribers_label + "...");
    this.lp_client.get(this.subscribers_portlet_uri, config);
};

/**
 * Check whether a (un)subscribe operation should indicate progress in the
 * subscribers list using the entry for the subscriber or whether a generic
 * progress indication should be used.
 *
 * @method _updateSubscribersList
 * @param subscriber {Object} the subscriber being (un)subscribed.
 */
SubscribersLoader.prototype._updateSubscribersList = function(subscriber) {
    var is_me = this._subscriber_is_me(subscriber);
    return !is_me || this.display_me_in_list;
};

/**
 * Return a function object that accepts SubscribersList and subscriber
 * objects as parameters.
 *
 * Constructed function tries to unsubscribe subscriber from the
 * this.context, and indicates activity in the subscribers list.
 *
 * @method _getUnsubscribeCallback
 */
SubscribersLoader.prototype._getUnsubscribeCallback = function() {
    var loader = this;
    return function(subscribers_list, subscriber) {
        var is_me = loader._subscriber_is_me(subscriber);
        var update_subscribers_list =
            loader._updateSubscribersList(subscriber);

        function on_success() {
            if (update_subscribers_list) {
                subscribers_list.stopSubscriberActivity(
                    subscriber, true, function() {
                    subscribers_list.removeSubscriber(subscriber);
                });
            } else {
                subscribers_list.stopActivity();
            }
            // If we have just unsubscribed ourselves, we need to update the
            // "subscribe me" link.
            if (is_me && Y.Lang.isString(loader.subscribe_me_link)) {
                loader._updateSubscribeMeLink(false);
            }
        }
        function on_failure(t_id, response) {
            if (update_subscribers_list) {
                subscribers_list.stopSubscriberActivity(subscriber, false);
            } else {
                subscribers_list.stopActivity();
            }
            Y.lp.app.errors.display_error(
                false,
                response.status + " (" + response.statusText + ")."
            );
        }

        var config = {
            on: { success: on_success,
                  failure: on_failure },
            parameters: { person: subscriber.self_link }
        };
        if (update_subscribers_list) {
            subscribers_list.indicateSubscriberActivity(subscriber);
        } else {
            subscribers_list.startActivity("Unsubscribing...");
        }
        loader.lp_client.named_post(
            loader.context.self_link, loader.unsubscribe_api, config);
    };
};

/**
 * Set-up subscribe-me link.
 *
 * @method _setupSubscribeMe
 */
SubscribersLoader.prototype._setupSubscribeMe = function() {
    var loader = this;
    if (!Y.Lang.isValue(LP.links.me)) {
        // No-op for anonymous users.
        return;
    }
    var link = Y.one(this.subscribe_me_link);
    if (link === null) {
        Y.error("No link matching CSS selector '" +
                this.subscribe_me_link +
                "' for subscribing me found.");
    }

    var is_subscribed = Y.Lang.isFunction(loader._unsubscribe_me);
    this._updateSubscribeMeLink(is_subscribed);

    link.on('click', function (e) {
        e.halt();
        var is_subscribed = Y.Lang.isFunction(loader._unsubscribe_me);
        if (is_subscribed) {
            loader._unsubscribe_me();
        } else {
            if (!loader.display_me_in_list) {
                loader.subscribers_list.startActivity("Subscribing...");
            }
            loader._subscribePersonURI(
                LP.links.me, loader.subscribe_me_level);
        }
    });
    link.addClass('js-action');
};

/**
 * Update the subscribe-me link after a (un)subscribe operation has completed.
 *
 * @method _updateSubscribeMeLink
 * @param is_subscribed {Boolean} True if the current user is subscribed.
 */
SubscribersLoader.prototype._updateSubscribeMeLink = function(is_subscribed) {
    var link = Y.one(this.subscribe_me_link);
    if (is_subscribed) {
        link.set('text', this.unsubscribe_label)
            .removeClass('add')
            .addClass('remove')
            .set('title', this.subscribed_help_text);
    } else {
        this._unsubscribe_me = undefined;
        link.set('text', this.subscribe_label)
            .removeClass('remove')
            .addClass('add')
            .set('title', this.unsubscribed_help_text);
    }
};

/**
 * Set-up subscribe-someone-else link to pop-up a picker and subscribe
 * the selected person/team.
 *
 * @method _setupSubscribeSomeoneElse
 * @param level {String} Level of the subscription.
 */
SubscribersLoader.prototype._setupSubscribeSomeoneElse = function(level) {
    var loader = this;
    var config = {
        header: 'Subscribe someone else',
        step_title: 'Search',
        picker_activator: this.subscribe_someone_else_link
    };
    if (!Y.Lang.isValue(LP.links.me)) {
        // No-op for anonymous users.
        return;
    }
    if (Y.one(this.subscribe_someone_else_link) === null) {
        Y.error("No link matching CSS selector '" +
                this.subscribe_someone_else_link +
                "' for subscribing someone else found.");
    }
    config.save = function(result) {
        var person_uri = Y.lp.client.get_absolute_uri(result.api_uri);
        loader._subscribePersonURI(person_uri, level);
    };
    // We store the picker for testing only.
    this._picker = Y.lp.app.picker.create('ValidPersonOrTeam', config);
};

/**
 * Subscribe a person or a team to the context, represented by their URI.
 * We fetch the actual person object via API and pass it into _subscribe().
 *
 * @method _subscribePersonURI
 * @param person_uri {String} URI representation of a person.
 * @param level {String} Level of the subscription.
 */
SubscribersLoader.prototype._subscribePersonURI =
                                        function(person_uri, level) {
    var loader = this;
    loader.lp_client.get(person_uri, {
        on: {
            success: function(person) {
                loader._subscribe(person, level);
            },
            failure: function(t_id, response) {
                Y.lp.app.errors.display_error(
                    false,
                    response.status + " (" + response.statusText + ")\n" +
                        "Couldn't get subscriber details from the " +
                        "server, so they have not been subscribed.\n"
                );
            }
        } });
};

/**
 * Subscribe a person or a team to the context.
 *
 * @method _subscribe
 * @param person {Object} Representation of a person returned by the API.
 *     It's an object that returns all attributes with getAttrs() method.
 *     Must have at least self_link attribute which is passed as
 *     a parameter to the API 'unsubscribe' call.
 * @param level {String} Level of the subscription.
 */
SubscribersLoader.prototype._subscribe = function(person, level) {
    var subscriber = person.getAttrs();

    var is_me = this._subscriber_is_me(subscriber);
    var update_subscribers_list = this._updateSubscribersList(subscriber);
    if (update_subscribers_list) {
        this.subscribers_list.addSubscriber(subscriber, level, true);
        this.subscribers_list.indicateSubscriberActivity(subscriber);
    }
    var loader = this;

    var on_success = function() {
        var unsubscribe_callback = loader._getUnsubscribeCallback();
        if (update_subscribers_list) {
            loader.subscribers_list.stopSubscriberActivity(subscriber, true);
            loader.subscribers_list.addUnsubscribeAction(
                subscriber, unsubscribe_callback);
        } else {
            loader.subscribers_list.stopActivity();
        }
        // If we have just subscribed ourselves, we need to update the
        // "unsubscribe me" link and wire up the unsubscribe function.
        if (is_me && loader.subscribe_me_link) {
            loader._unsubscribe_me = function() {
                unsubscribe_callback(
                    loader.subscribers_list, subscriber);
            };
            loader._updateSubscribeMeLink(true);
        }
    };
    var on_failure = function(t_id, response) {
        if (update_subscribers_list) {
            loader.subscribers_list.stopSubscriberActivity(
                subscriber, false, function() {
                    loader.subscribers_list.removeSubscriber(subscriber);
                }
            );
        } else {
            loader.subscribers_list.stopActivity();
        }
        if (response.status === 400 && response.responseText !== undefined) {
            error_msg = response.responseText;
        } else {
            error_msg = (
                response.status + " (" + response.statusText + "). " +
                "Failed to subscribe " + subscriber.display_name + ".");
        }
        Y.lp.app.errors.display_error(
            false,
            error_msg
        );
    };
    var config = {
        on: { success: on_success,
              failure: on_failure },
        parameters: { person: subscriber.self_link } };
    this.lp_client.named_post(
        this.context.self_link, this.subscribe_api, config);
};

/**
 * Manages entire subscribers' list for a single entity.
 *
 * If the passed in container_box is not present, or if there are multiple
 * nodes matching it, it throws an exception.
 *
 * @class SubscribersList
 * @param config {Object} Configuration object containing at least
 *   container_box value with the container div CSS selector
 *   where to add the subscribers list.
 */
function SubscribersList(config) {
    if (!Y.Lang.isValue(config.subscriber_levels)) {
        Y.error(
            "No subscriber levels specified in `config'.");
    }
    this.subscriber_levels = config.subscriber_levels;
    this.subscribers_label = config.subscribers_label;
    this.unsubscribe_label = config.unsubscribe_label;
    if (!Y.Lang.isValue(config.subscriber_level_order)) {
        // If no ordering is specified, we will create a default ordering.
        this.subscriber_level_order = [];
        var level;
        for (level in this.subscriber_levels) {
            if (this.subscriber_levels.hasOwnProperty(level)) {
                this.subscriber_level_order.push(level);
            }
        }
    } else {
        this.subscriber_level_order = config.subscriber_level_order;
    }

    var container_nodes = Y.all(config.container_box);
    if (container_nodes.size() === 0) {
        Y.error('Container node must be specified in config.container_box.');
    } else if (container_nodes.size() > 1) {
        Y.error("Multiple container nodes for selector '" +
                config.container_box + "' present in the page. " +
                "You need to be more explicit.");
    } else {
        this.container_node = container_nodes.item(0);
    }
}
namespace.SubscribersList = SubscribersList;

/**
 * Reset the subscribers list:
 *  - If no sections with subscribers are left, it adds an indication
 *    of no subscribers.
 *  - If there are subscribers left, it ensures there is no indication
 *    of no subscribers.
 *
 * @method resetNoSubscribers
 * @param force_hide {Boolean} Whether to force hiding of the "no subscribers"
 *     indication.
 */
SubscribersList.prototype.resetNoSubscribers = function(force_hide) {
    var has_sections = (
        this.container_node.one('.' + CSS_CLASSES.section) !== null);
    var no_subs;
    if (has_sections || force_hide === true) {
        // Make sure the indicator for no subscribers is not there.
        no_subs = this.container_node.one('.' + CSS_CLASSES.no_subscribers);
        if (no_subs !== null) {
            no_subs.remove();
        }
    } else {
        var no_text;
        if (Y.Object.size(this.subscriber_levels) > 0) {
            no_text = 'No other ' + this.subscribers_label + '.';
        } else {
            no_text = 'No ' + this.subscribers_label + '.';
        }
        no_subs = Y.Node.create('<div />')
            .addClass(CSS_CLASSES.no_subscribers)
            .set('text', no_text);
        this.container_node.appendChild(no_subs);
    }
};

/**
 * Returns or creates a node for progress indication for the subscribers list.
 *
 * If node is not present, it is created and added to the beginning of
 * subscribers list container node.
 *
 * @method _ensureActivityNode
 * @return {Y.Node} A node with the spinner img node and a span text node.
 */
SubscribersList.prototype._ensureActivityNode = function() {
    var activity_node = this.container_node.one('.' + CSS_CLASSES.activity);
    if (activity_node === null) {
        activity_node = Y.Node.create('<div />')
            .addClass(CSS_CLASSES.activity);
        progress_icon = Y.Node.create('<img />')
            .set('src', '/@@/spinner');
        activity_node.appendChild(progress_icon);
        activity_node.appendChild(
            Y.Node.create('<span />')
                .addClass(CSS_CLASSES.activity_text));
        this.container_node.prepend(activity_node);
    }
    return activity_node;
};

/**
 * Sets icon in the activity node to either 'error' or 'spinner' icon.
 *
 * @method _setActivityErrorIcon
 * @param node {Y.Node} An activity node as returned by _ensureActivityNode().
 * @param error {Boolean} Whether to show an error icon.
 *     Otherwise shows a spinner image.
 */
SubscribersList.prototype._setActivityErrorIcon = function(node, error) {
    var progress_icon = node.one('img');
    if (error === true) {
        progress_icon.set('src', '/@@/error');
    } else {
        progress_icon.set('src', '/@@/spinner');
    }
};

/**
 * Sets the activity text inside the activity node.
 *
 * @method _setActivityText
 * @param node {Y.Node} An activity node as returned by _ensureActivityNode().
 * @param text {String} Description of the activity currently in progress.
 */
SubscribersList.prototype._setActivityText = function(node, text) {
    var text_node = node.one('.' + CSS_CLASSES.activity_text);
    text_node.set('text', ' ' + text);
};

/**
 * Indicate some activity for the subscribers list with a progress spinner
 * and optionally some text.
 *
 * @method startActivity
 * @param text {String} Description of the action to indicate progress of.
 */
SubscribersList.prototype.startActivity = function(text) {
    // We don't ever want "No subscribers" to be shown when loading is in
    // progress.
    this.resetNoSubscribers(true);

    var activity_node = this._ensureActivityNode();
    // Ensure the icon is back to the spinner.
    this._setActivityErrorIcon(activity_node, false);
    this._setActivityText(activity_node, text);
};

/**
 * Stop any activity indication for the subscribers list and optionally
 * display an error message.
 *
 * @method stopActivity
 * @param error_text {String} Error message to display.  If not a string,
 *     it is considered that the operation was successful and no error
 *     indication is added to the subscribers list.
 */
SubscribersList.prototype.stopActivity = function(error_text) {
    var activity_node = this.container_node.one('.' + CSS_CLASSES.activity);
    if (Y.Lang.isString(error_text)) {
        // There is an error message, keep the node visible with
        // the error message in.
        activity_node = this._ensureActivityNode(true);
        this._setActivityErrorIcon(activity_node, true);
        this._setActivityText(activity_node, error_text);
        this.resetNoSubscribers(true);
    } else {
        // No errors, remove the activity node if present.
        if (activity_node !== null) {
            activity_node.remove();
        }
        // Restore "No subscribers" indication if needed.
        this.resetNoSubscribers();
    }
};

/**
 * Get a CSS class to use for the section of the subscribers' list
 * with subscriptions with the level `level`.
 *
 * @method _getSectionCSSClass
 * @param level {String} Level of the subscription.
 *     `this.subscriber_levels` has the acceptable values.
 * @return {String} CSS class to use for the section for the `level`.
 */
SubscribersList.prototype._getSectionCSSClass = function(level) {
    level = (level === '' ? 'default': level);
    return CSS_CLASSES.section + '-' + level.toLowerCase();
};

/**
 * Return the section node for a subscription level.
 *
 * @method _getSection
 * @param level {String} Level of the subscription.
 * @return {Object} Node containing the section or null.
 */
SubscribersList.prototype._getSection = function(level) {
    return this.container_node.one('.' + this._getSectionCSSClass(level));
};

/**
 * Create a subscribers section node depending on their level.
 *
 * @method _createSectionNode
 * @param level {String} Level of the subscription.
 *     See `subscriber_levels` for a list of acceptable values.
 * @return {Object} Node containing the entire section.
 */
SubscribersList.prototype._createSectionNode = function(level) {
    // Container node for the entire section.
    var node = Y.Node.create('<div />')
        .addClass(CSS_CLASSES.section)
        .addClass(this._getSectionCSSClass(level));
    // Header.
    if (level !== '') {
        node.appendChild(
            Y.Node.create('<h3 />')
                .set('text', this.subscriber_levels[level]));
    }
    // Node listing the actual subscribers.
    node.appendChild(
        Y.Node.create('<ul />')
            .addClass(CSS_CLASSES.list));
    return node;
};


/**
 * Inserts the section node in the appropriate place in the subscribers list.
 * Uses `subscriber_level_order` to figure out what position should a section
 * with subscribers on `level` hold.
 *
 * @method _insertSectionNode
 * @param level {String} Level of the subscription.
 * @param section_node {Object} Node to insert (containing
 *   the entire section).
 */
SubscribersList.prototype._insertSectionNode = function(level, section_node) {
    // We have no ordering so just prepend.
    if (this.subscriber_level_order.length === 0) {
        this.container_node.prepend(section_node);
        return;
    }
    var index, existing_level;
    var existing_level_node = null;
    for (index=0; index < this.subscriber_level_order.length; index++) {
        existing_level = this.subscriber_level_order[index];
        if (existing_level === level) {
            // Insert either at the beginning of the list,
            // or after the last section which comes before this one.
            if (existing_level_node === null) {
                this.container_node.prepend(section_node);
            } else {
                existing_level_node.insert(section_node, 'after');
            }
            break;
        } else {
            var existing_node = this._getSection(existing_level);
            if (existing_node !== null) {
                existing_level_node = existing_node;
            }
        }
    }
};


/**
 * Create a subscribers section depending on their level and
 * add it to the other subscribers list.
 * If section is already there, returns the existing node for it.
 *
 * @method _getOrCreateSection
 * @param level {String} Level of the subscription.
*     `this.subscriber_levels` has the acceptable values.
 * @return {Object} Node containing the entire section.
 */
SubscribersList.prototype._getOrCreateSection = function(level) {
    var section_node = this._getSection(level);
    if (section_node === null) {
        section_node = this._createSectionNode(level);
        this._insertSectionNode(level, section_node);
    }
    // Remove the indication of no subscribers if it's present.
    this.resetNoSubscribers();
    return section_node;
};

/**
 * Return whether subscribers section has any subscribers or not.
 *
 * @method _sectionHasSubscribers
 * @param node {Y.Node} Node containing the subscribers section.
 * @return {Boolean} True if there are still subscribers in the section.
 */
SubscribersList.prototype._sectionNodeHasSubscribers = function(node) {
    var list = node.one('.' + CSS_CLASSES.list);
    if (list !== null) {
        var has_any = (list.one('.' + CSS_CLASSES.subscriber) !== null);
        return has_any;
    } else {
        Y.error(
            'No div.subscribers-list found inside the passed `node`.');
    }
};

/**
 * Removes a subscribers section node if there are no remaining subscribers.
 * Silently passes if nothing to remove.
 *
 * @method _removeSectionNodeIfEmpty
 * @param node {Object} Section node containing all the subscribers.
 */
SubscribersList.prototype._removeSectionNodeIfEmpty = function(node) {
    if (node !== null && !node.hasClass(CSS_CLASSES.section)) {
        Y.error('Node is not a section node.');
    }
    if (node !== null && !this._sectionNodeHasSubscribers(node)) {
        node.remove();
        // Add the indication of no subscribers if this was the last section.
        this.resetNoSubscribers();
    }
};

/**
 * Get a string value usable as the ID for the node based on
 * the subscriber name.
 */
SubscribersList.prototype._getNodeIdForSubscriberName = function(name) {
    return CSS_CLASSES.subscriber + '-' + Y.lp.names.launchpad_to_css(name);
};

/**
 * Validate and sanitize a subscriber object.
 * It must have at least a `name` attribute.
 * If `display_name` is not set, the value from `name` is used instead.
 *
 * @method _validateSubscriber
 * @param subscriber {Object} Object containing `name`, `display_name`,
 *    `web_link` and `is_team` indicator for the subscriber.
 *    If `display_name` is undefined, sets it to the same value as `name`.
 *    If `web_link` is not set, sets it to "/~name".
 * @return {Object} Modified `subscriber` object.
 */
SubscribersList.prototype._validateSubscriber = function(subscriber) {
    if (!Y.Lang.isString(subscriber.name)) {
        Y.error('No `name` passed in `subscriber`.');
    }
    if (!Y.Lang.isString(subscriber.display_name)) {
        // Default to `name` for display_name.
        subscriber.display_name = subscriber.name;
    }
    if (!Y.Lang.isString(subscriber.web_link)) {
        // Default to `/~name` for web_link.
        subscriber.web_link = '/~' + subscriber.name;
    }
    return subscriber;
};

/**
 * Creates and returns a node for the `subscriber`.
 *
 * It makes a link using subscriber.display_name as the link text,
 * and linking to /~`subscriber.name`.
 * Everything is wrapped in a div.subscriber node.
 *
 * @method _createSubscriberNode
 * @param subscriber {Object} Object containing `name`, `display_name`
 *    `web_link`, `is_team` and `display_subscribed_by` attributes.
 * @return {Object} Node containing a subscriber link.
 */
SubscribersList.prototype._createSubscriberNode = function(subscriber) {
    var subscriber_node = Y.Node.create('<li />')
        .addClass(CSS_CLASSES.subscriber);

    var subscriber_link = Y.Node.create('<a />');
    subscriber_link.set('href', subscriber.web_link);

    var formatted_displayname;

    if (subscriber.display_name.length <= MAX_DISPLAYNAME_LENGTH) {
        formatted_displayname = subscriber.display_name;
    } else {
        formatted_displayname =
            subscriber.display_name.substring(0, MAX_DISPLAYNAME_LENGTH-3) +
                '...';
    }
    var subscriber_text = Y.Node.create('<span />')
        .addClass('sprite')
        .set('text', formatted_displayname);
    if (subscriber.is_team === true) {
        subscriber_text.addClass('team');
    } else {
        subscriber_text.addClass('person');
    }
    if (Y.Lang.isString(subscriber.display_subscribed_by)) {
        subscriber_link.set('title', subscriber.display_subscribed_by);
    }
    subscriber_link.appendChild(subscriber_text);

    subscriber_node.appendChild(subscriber_link);
    return subscriber_node;
};

/**
 * Checks if the subscription level is one of the acceptable ones.
 * Throws an error if not, otherwise silently returns.
 */
SubscribersList.prototype._checkSubscriptionLevel = function(level) {
    if (Y.Object.size(this.subscriber_levels) > 0
            && !this.subscriber_levels.hasOwnProperty(level)) {
        Y.error(
            'Level "' + level + '" is not an acceptable subscription level.');
    }
};

/**
 * Add or change a subscriber in the subscribers list.
 *
 * If subscriber is already in the list and in a different subscription
 * level section, it is moved to the appropriate section indicated by
 * `level` parameter.  If subscriber is already in the list and subscribed
 * at the same level, nothing happens.
 *
 * @method addSubscriber
 * @param subscriber {Object} Object containing `name`, `display_name`
 *    `web_link`, `is_team`, and `display_subscribed_by` attributes describing
 *    the subscriber.
 * @param level {String} Level of the subscription.
 * @param config {Object} Object containing potential 'unsubscribe' callback
 *     in the `unsubscribe_callback` attribute.
 * @param add_new {Boolean} True if the subscriber was newly added
 */
SubscribersList.prototype.addSubscriber = function(subscriber, level,
                                                   add_new, config) {
    this._checkSubscriptionLevel(level);
    subscriber = this._validateSubscriber(subscriber);

    var section_node = this._getOrCreateSection(level);
    var list_node = section_node.one('.' + CSS_CLASSES.list);

    var subscriber_id = this._getNodeIdForSubscriberName(subscriber.name);
    var subscriber_node = this.container_node.one('#' + subscriber_id);

    if (subscriber_node === null) {
        subscriber_node = this._createSubscriberNode(subscriber);
        subscriber_node.set('id', subscriber_id);
        if (add_new === true) {
            // Add new subscriber to the start of the list.
            list_node.prepend(subscriber_node);
        } else {
            // Add the subscriber at the end of the list.
            list_node.append(subscriber_node);
        }
        // Add the unsubscribe action if needed.
        if (Y.Lang.isValue(config) &&
            Y.Lang.isFunction(config.unsubscribe_callback)) {
            this.addUnsubscribeAction(
                subscriber, config.unsubscribe_callback);
        }
    } else {
        // Move the subscriber node from the existing section to the new one.
        var existing_section = subscriber_node.ancestor(
            '.' + CSS_CLASSES.section);
        if (existing_section === null) {
            Y.error("Matching subscriber node doesn't seem to be in any " +
                    "subscribers list sections.");
        }
        if (existing_section !== section_node) {
            // We do not destroy the node so we can insert it into
            // the appropriate position.
            subscriber_node.remove();
            this._removeSectionNodeIfEmpty(existing_section);
            // Insert the subscriber at the start of the list.
            list_node.prepend(subscriber_node);
        }
        // else:
        //   Subscriber is already there in the same section. A no-op.
    }

    return subscriber_node;
};

/**
 * Get a subscriber node for the passed in subscriber.
 *
 * If subscriber is not in the list already, it fails with an exception.
 *
 * @method _getSubscriberNode
 * @param subscriber {Object} Object containing at least `name`
 *     for the subscriber.
 */
SubscribersList.prototype._getSubscriberNode = function(subscriber) {
    subscriber = this._validateSubscriber(subscriber);

    var subscriber_id = this._getNodeIdForSubscriberName(subscriber.name);
    var subscriber_node = this.container_node.one('#' + subscriber_id);

    if (subscriber_node === null) {
        Y.error('Subscriber is not present in the subscribers list. ' +
                'Please call addSubscriber(subscriber) first.');
    }
    return subscriber_node;
};

/**
 * Create a subscriber actions node to hold actions like unsubscribe.
 * If the node already exists, returns it instead.
 *
 * @method _getOrCreateActionsNode
 * @param subscriber_node {Object} Node for a particular subscriber.
 * @return {Object} A node suitable for putting subscriber actions in.
 */
SubscribersList.prototype._getOrCreateActionsNode = function(subscriber_node)
{
    var actions_node = subscriber_node.one('.' + CSS_CLASSES.actions);
    if (actions_node === null) {
        // Create a node to hold all the actions.
        actions_node = Y.Node.create('<span />')
            .addClass(CSS_CLASSES.actions)
            .setStyle('float', 'right');
        subscriber_node.appendChild(actions_node);
    }
    return actions_node;
};

/**
 * Adds an unsubscribe action for the subscriber.
 *
 * It creates a separate actions node which will hold any actions
 * (including unsubscribe one), and creates a "remove" link with the
 * on.click action set to call `callback` function with subscriber
 * passed in as the parameter.
 *
 * If `subscriber` does not have at least the `name` attribute,
 * an exception is thrown.
 * If `callback` is not a function, it throws an exception.
 *
 * @method addUnsubscribeAction
 * @param subscriber {Object} Object containing `name`, `display_name`
 *    `web_link` and `is_team` attributes describing the subscriber.
 * @param callback {Function} Function to call on clicking the unsubscribe
 *     button.  It will be passed `this` (a SubscribersList) as the first,
 *     and `subscriber` as the second parameter.
 */
SubscribersList.prototype.addUnsubscribeAction = function(subscriber,
                                                          callback) {
    subscriber = this._validateSubscriber(subscriber);
    if (!Y.Lang.isFunction(callback)) {
        Y.error('Passed in callback for unsubscribe action ' +
                'is not a function.');
    }
    var subscriber_node = this._getSubscriberNode(subscriber);
    var actions_node = this._getOrCreateActionsNode(subscriber_node);
    var unsubscribe_node = actions_node.one('.' + CSS_CLASSES.unsubscribe);
    if (unsubscribe_node === null) {
        unsubscribe_node = Y.Node.create('<a />')
            .addClass(CSS_CLASSES.unsubscribe)
            .set('href', '+subscribe')
            .set('title',
                this.unsubscribe_label + ' ' + subscriber.display_name);
        unsubscribe_node.appendChild(
            Y.Node.create('<img />')
                .set('src', '/@@/remove')
                .set('alt', 'Remove'));
        var subscriber_list = this;
        unsubscribe_node.on('click', function(e) {
            e.halt();
            callback(subscriber_list, subscriber);
        });
        actions_node.appendChild(unsubscribe_node);
    }
};

/**
 * Remove a subscriber node for the `subscriber`.
 *
 * If subscriber is not in the list already, it fails with an exception.
 *
 * @method removeSubscriber
 * @param subscriber {Object} Object containing at least `name`
 *     for the subscriber.
 */
SubscribersList.prototype.removeSubscriber = function(subscriber) {
    subscriber = this._validateSubscriber(subscriber);
    var subscriber_node = this._getSubscriberNode(subscriber);
    var existing_section = subscriber_node.ancestor(
        '.' + CSS_CLASSES.section);
    subscriber_node.remove(true);
    if (existing_section === null) {
        Y.error("Matching subscriber node doesn't seem to be in any " +
                "subscribers list sections.");
    }
    this._removeSectionNodeIfEmpty(existing_section);
};

/**
 * Indicates some activity for a subscriber in the subscribers list.
 * Uses a regular Launchpad progress spinner UI.
 *
 * If subscriber is not in the list already, it fails with an exception.
 * If there are any actions available for the subscriber (such as unsubscribe
 * action), they are hidden.
 *
 * @method indicateSubscriberActivity
 * @param subscriber {Object} Object containing at least `name`
 *     for the subscriber.
 */
SubscribersList.prototype.indicateSubscriberActivity = function(subscriber) {
    var subscriber_node = this._getSubscriberNode(subscriber);
    var progress_node = subscriber_node.one(
        '.' + CSS_CLASSES.subscriber_activity);

    // No-op if there is already indication of progress,
    // and creates a new node with the spinner if there isn't.
    if (progress_node === null) {
        var actions_node = subscriber_node.one('.' + CSS_CLASSES.actions);
        if (actions_node !== null) {
            actions_node.setStyle('display', 'none');
        }
        var progress_icon = Y.Node.create('<img />')
            .set('src', '/@@/spinner');

        progress_node = Y.Node.create('<span />')
            .addClass(CSS_CLASSES.subscriber_activity)
            .setStyle('float', 'right');
        progress_node.appendChild(progress_icon);
        subscriber_node.appendChild(progress_node);
    }
};

/**
 * Stop any indication of activity for a subscriber in the subscribers list.
 *
 * If the spinner is present, it removes it.  If `success` parameter is
 * passed in, it determines if success or failure animation will be shown
 * as well.
 *
 * If subscriber is not in the list already, it fails with an exception.
 * If there are any actions available for the subscriber (such as unsubscribe
 * action), they are re-displayed if hidden.
 *
 * @method stopSubscriberActivity
 * @param subscriber {Object} Object containing at least `name`
 *     for the subscriber.
 * @param success {Boolean} Whether to indicate success (`success` == true,
 *     flash green) or failure (false, red).  Otherwise, perform no
 *     animation.
 * @param callback {Function} Function to call if and when success/failure
 *     animation completes.
 */
SubscribersList.prototype.stopSubscriberActivity = function(subscriber,
                                                            success,
                                                            callback) {
    var subscriber_node = this._getSubscriberNode(subscriber);
    var progress_node = subscriber_node.one(
        '.' + CSS_CLASSES.subscriber_activity);
    if (progress_node !== null) {
        // Remove and destroy the node if present.
        progress_node.remove(true);
    }
    // If actions node is present and hidden, show it.
    var actions_node = subscriber_node.one('.' + CSS_CLASSES.actions);
    if (actions_node !== null) {
        actions_node.setStyle('display', 'inline');
    }

    if (success === true || success === false) {
        var anim;
        if (success === true) {
            anim = Y.lp.anim.green_flash({ node: subscriber_node });
        } else {
            anim = Y.lp.anim.red_flash({ node: subscriber_node });
        }
        anim.on('end', callback);
        anim.run();
    }
};


}, "0.1", {"requires": ["node", "lp.anim", "lp.app.picker", "lp.app.errors",
                        "lp.client", "lp.names"]});
