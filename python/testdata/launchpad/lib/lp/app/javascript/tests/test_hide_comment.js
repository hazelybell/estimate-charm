/* Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 */

YUI.add('lp.app.comment.hide.test', function (Y) {

    var tests = Y.namespace('lp.app.comment.hide.test');
    tests.suite = new Y.Test.Suite("lp.comments.hide Tests");
    tests.suite.add(new Y.Test.Case({
        name: 'lp.app.comments.hide_test',

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to allow
            // insertion of test data.
            window.LP = {
                links: {},
                cache: {}
            };
            Y.lp.client.Launchpad = function() {};
            Y.lp.client.Launchpad.prototype.named_post =
                function(url, func, config) {
                    LP.cache.call_data = {
                        called_url: url,
                        called_func: func,
                        called_config: config
                    };
                    // our setup assumes success, so we just do the
                    // success callback.
                    config.on.success();
                };
            LP.cache.comment_context = {
                self_link: 'https://launchpad.dev/api/devel/some/comment/'
            };
            this.comment_list = new Y.lp.app.comment.CommentList();
            this.comment_list.render();
        },

        tearDown: function() {
            this.comment_list.destroy();
        },

        test_hide: function () {
            var link = Y.one('#mark-spam-0');
            var comment_node = Y.one('.boardComment');
            link.simulate('click');
            Y.Assert.isTrue(comment_node.hasClass('adminHiddenComment'));
            Y.Assert.areEqual('Unhide comment', link.get('text'),
                'Link text should be \'Unhide comment\'');
            Y.Assert.areEqual(
                'https://launchpad.dev/api/devel/some/comment/',
                LP.cache.call_data.called_url, 'Call with wrong url.');
            Y.Assert.areEqual(
                'setCommentVisibility', LP.cache.call_data.called_func,
                'Call with wrong func.');
            Y.Assert.isFalse(
                LP.cache.call_data.called_config.parameters.visible);
            Y.Assert.areEqual(
                0, LP.cache.call_data.called_config.parameters.comment_number,
                'Called with wrong wrong comment number.');
        },

        test_unhide: function () {
            var link = Y.one('#mark-spam-1');
            var comment_node = Y.one('#hidden-comment');
            link.simulate('click');
            Y.Assert.isFalse(comment_node.hasClass('adminHiddenComment'));
            Y.Assert.areEqual('Hide comment', link.get('text'),
                'Link text should be \'Hide comment\'');
            Y.Assert.areEqual(
                'https://launchpad.dev/api/devel/some/comment/',
                LP.cache.call_data.called_url, 'Call with wrong url.');
            Y.Assert.areEqual(
                'setCommentVisibility', LP.cache.call_data.called_func,
                'Call with wrong func.');
            Y.Assert.isTrue(
                LP.cache.call_data.called_config.parameters.visible);
            Y.Assert.areEqual(
                1, LP.cache.call_data.called_config.parameters.comment_number,
                'Called with wrong wrong comment number.');
            }
        }));

}, '0.1', {'requires': ['test', 'lp.testing.helpers', 'test-console',
                        'node-event-simulate', 'lp.app.comment']});
