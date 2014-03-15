/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Setup for managing subscribers list for questions.
 *
 * @module answers
 * @submodule subscribers
 */

YUI.add('lp.answers.subscribers', function(Y) {

var namespace = Y.namespace('lp.answers.subscribers');

/**
 * Possible subscriber levels with descriptive headers for
 * sections that will hold them.
 */
var subscriber_levels = {
    'Direct': 'Direct subscribers',
    'Indirect': 'Also notified'
};

/**
 * Order of subscribers sections.
 */
var subscriber_level_order = ['Direct', 'Indirect'];


/**
 * Create the SubscribersLoader instance which will load subscribers for
 * a question and put them in the web page.
 */
function createQuestionSubscribersLoader(setup_config) {
    var question = {
        self_link: LP.cache.context.self_link,
        web_link: LP.cache.context.web_link };
    var default_config = {
        container_box: '#other-question-subscribers',
        question: question,
        subscribers_details_view:
            '/+portlet-subscribers-details',
        subscribe_someone_else_link: '.menu-link-addsubscriber',
        subscribe_me_link: '.menu-link-subscription',
        subscribed_help_text: 'You will stop receiving email notifications ' +
            'about updates to this question',
        unsubscribed_help_text: 'You will receive email notifications ' +
            'about updates to this question',
        subscriber_levels: subscriber_levels,
        subscriber_level_order: subscriber_level_order,
        context: question,
        subscribe_me_level: 'Direct',
        subscribe_someone_else_level: 'Direct',
        default_subscriber_level: 'Indirect'};
    var module = Y.lp.app.subscribers.subscribers_list;

    if (Y.Lang.isValue(setup_config)) {
        setup_config = Y.mix(setup_config, default_config);
    } else {
        setup_config = default_config;
    }
    return new module.SubscribersLoader(setup_config);
}
namespace.createQuestionSubscribersLoader = createQuestionSubscribersLoader;

}, "0.1", {"requires": ["lp.app.subscribers.subscribers_list"]});
