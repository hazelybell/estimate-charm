/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.registry.team.mailinglists.test', function (Y) {
    // Local aliases.
    var Assert = Y.Assert,
        ArrayAssert = Y.ArrayAssert;
    var team_mailinglists = Y.lp.registry.team.mailinglists;

    var tests = Y.namespace('lp.registry.team.mailinglists.test');
    tests.suite = new Y.Test.Suite('lp.registry.team.mailinglists Tests');
    tests.suite.add(new Y.Test.Case({

        name: 'Team Mailinglists',

        setUp: function() {
            window.LP = {
                links: {},
                cache: {}
            };
        },

        tearDown: function() {
        },

        test_render_message: function () {
            var config = {
                messages: [
                    {
                        'message_id': 3,
                        'headers': {
                            'Subject': 'Please stop breaking things',
                            'To': 'the_list@example.hu',
                            'From': 'someone@else.com',
                            'Date': '2011-10-13'
                        },
                        'nested_messages': [],
                        'attachments': []
                    }
                ],
                container: Y.one('#messagelist'),
                forwards_navigation: Y.all('.last,.next'),
                backwards_navigation: Y.all('.first,.previous')
            };
            var message_list = new Y.lp.registry.team.mailinglists.MessageList(
                config);
            message_list.display_messages();
            var message = Y.one("#message-3");
            Assert.areEqual(message.get('text'), 'Please stop breaking things');
        },

        test_nav: function () {
            var config = {
                messages: [],
                container: Y.one('#messagelist'),
                forwards_navigation: Y.all('.last,.next'),
                backwards_navigation: Y.all('.first,.previous')
            };
            var message_list = new Y.lp.registry.team.mailinglists.MessageList(
                config);

            var fired = false;
            Y.on('messageList:backwards', function () {
                fired = true;
            });

            var nav_link = Y.one('.first');
            nav_link.simulate('click');
            Assert.isTrue(fired);
        }
    }));

}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'test-console',
        'lp.registry.team.mailinglists', 'lp.mustache',
        'node-event-simulate', 'widget-stack', 'event']
});
