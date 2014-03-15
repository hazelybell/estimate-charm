/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Team mailinglists
 *
 * @module lp.registry.team.mailinglists
 */

YUI.add('lp.registry.team.mailinglists', function(Y) {

var module = Y.namespace('lp.registry.team.mailinglists');

function MessageList(config) {
    MessageList.superclass.constructor.apply(this, arguments);
}

MessageList.NAME = "messageList";

MessageList.ATTR = {
    forwards_nagivation: {
        value: null
    },

    backwards_navigation: {
        value: null
    },

    messages: {
        value: []
    },

    container: {
        value: null
    },

    template: {
        value: null
    }
};

Y.extend(MessageList, Y.Base, {

    initializer: function (config) {
        this.set('container', config.container);
        if (Y.Lang.isValue(config.messages)) {
            this.set('messages', config.messages);
        }
        if (Y.Lang.isValue(config.forwards_navigation)) {
            this.set('forwards_navigation', config.forwards_navigation);
        }

        if (Y.Lang.isValue(config.backwards_navigation)) {
            this.set('backwards_navigation', config.backwards_navigation);
        }
        this._bind_nav();

        var template = '<div class="message-list">' +
                       '{{#items}}' +
                       '<li style="margin-left: {{indent}}em">' +
                       '<a href="#" id="message-{{message_id}}">' +
                       '{{subject}}</a>' +
                       '<div>{{from}}, {{date}}</div>' +
                       '</li>' +
                       '{{/items}}' +
                       '</div>';
        this.set('template', template);
    },

    _bind_nav: function () {
        /* XXX j.c.sackett 2012-02-01
         * These signals aren't currently caught by anything in the message
         * list. They exist so that once we have batching calls from grackle
         * ironed out we can easily add the functions in wherever they make
         * the most sense, be that here or in a grackle js module.
         *
         * When we are actually integrating grackle, these may need updating,
         * and we'll need tests ensuring the signals actually *do* something.
         */
        var forwards = this.get('forwards_navigation');
        var backwards = this.get('backwards_navigation');

        forwards.on('click', function(e) {
            Y.fire('messageList:forwards', e);
        });

        backwards.on('click', function(e) {
            Y.fire('messageList:backwards', e);
        });
    },

    display_messages: function () {
        var mustache_model = [];
        var processed_ids = [];
        var messages = Y.Array(this.get('messages'));
        var container = this.get('container');
        this._create_mustache_model(
            messages, mustache_model, processed_ids, 0);
        var content = Y.lp.mustache.to_html(
            this.get('template'), {items: mustache_model});
        container.setContent(content);
    },

    _create_mustache_model: function
        (messages, mustache_model, processed_ids, indent) {
        // Right now messages are only being displayed treaded, by date. More
        // sophisticated model creation will be needed for threaded by
        // subject.
        var i;
        filter_func = function(item) {
            var nested_ids = messages[i].nested_messages;
            var index = Y.Array.indexOf(nested_ids, item.message_id);
            return (index !== -1);
        };
        for (i = 0; i < messages.length; i++) {
            var message = messages[i];
            // Only create mustache data for messages not already processed.
            // Messages will have been processed already if they were part of
            // the nested messages for an earlier message in the list.
            if (Y.Array.indexOf(processed_ids, message.message_id) === -1) {
                processed_ids.push(message.message_id);
                mustache_model.push({
                    message_id: message.message_id,
                    indent: indent,
                    subject: message.headers.Subject,
                    to: message.headers.To,
                    from: message.headers.From,
                    date: message.headers.Date
                });

                if (message.nested_messages !== undefined) {
                    indent = indent + 2;
                    // Create a new array of the nested messages from the ids
                    // provided by the current message's `nested_messages`
                    // parameter.
                    nested_messages = Y.Array.filter(messages, filter_func);
                    this._create_mustache_model(
                        nested_messages,
                        mustache_model,
                        processed_ids,
                        indent);
                }
            }
        }
    }
});
module.MessageList = MessageList;


}, '0.1', {
    requires: [
        'array-extras', 'base', 'node', 'datatype', 'lp.mustache']
});
