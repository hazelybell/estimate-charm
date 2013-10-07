/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.comment.test', function (Y) {

    var tests = Y.namespace('lp.app.comment.test');
    tests.suite = new Y.Test.Suite('lp.app.comment Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'lp.app.comment_tests',

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.app.comment,
                "Could not locate the lp.app.comment module");
        },

        test_init: function () {
            var comment = new Y.lp.app.comment.Comment();
            Y.Assert.isObject(comment.comment_input);
            Y.Assert.isObject(comment.submit_button);
            Y.Assert.isTrue(
                comment.progress_message.hasClass('update-in-progress-message'));
        },

        test_validation: function () {
            var comment = new Y.lp.app.comment.Comment();
            comment.comment_input.set('value', 'foo ');
            Y.Assert.isTrue(comment.validate());

            comment.comment_input.set('value', '    ');
            Y.Assert.isFalse(comment.validate());
        },

        _get_mocked_comment: function () {
            window.LP = {
                cache: {
                    bug: { self_link: '/bug/1/' }
                }
            };
            var mock_client = new Y.lp.testing.helpers.LPClient();
            mock_client.named_post.args = [];
            mock_client.get.args = [];
            var comment = new Y.lp.app.comment.Comment({
                animate: false,
                lp_client: mock_client
            });
            return comment;
        },

        test_add_comment_calls: function () {
            // Test which functions Comment.add_comment calls.
            var comment = this._get_mocked_comment();
            var progress_ui_called = false;
            var post_comment_called = false;
            var extra_call_called = false;
            comment.activateProgressUI = function () {
                progress_ui_called = true;
            };
            comment.post_comment = function () {
                post_comment_called = true;
            };
            comment._add_comment_success = function () {
                extra_call_called = true;
            };
            comment.validate = function () { return true };
            var mock_event = { halt: function () {} };

            comment.add_comment(mock_event);
            Y.Assert.isTrue(
                progress_ui_called, 'activateProgressUI not called');
            Y.Assert.isTrue(
                post_comment_called, 'post_comment not called');
        },

        test_get_comment_html: function () {
            // Test that get_comment_HTML has the correct args and calls the
            // correct callbacks.
            var comment = this._get_mocked_comment();
            var message_entry = {
                get: function (ignore) {
                    // `get` is only called with `self_link` in this function.
                    // If that changes, this will need to be mocked better.
                    return "https://example.com/comments/3";
                }
            };
            var callback_called = false;
            var callback = function () {
                callback_called = true;
            };
            comment.get_comment_HTML(message_entry, callback);
            Y.Assert.isTrue(callback_called);
            var client = comment.get('lp_client');
            var url = client.received[0][1][0].split("?")[0];
            Y.Assert.areEqual(url, 'https://example.com/comments/3');
        },

        test_post_comment: function () {
            // Test Comment.post_comment
            var comment = this._get_mocked_comment();
            var no_op_called = false;
            var no_op = function () {
                no_op_called = true;
            };
            comment.post_comment(no_op);
            var client = comment.get('lp_client');
            Y.Assert.areEqual(
                client.received[0][1][0],
                '/bug/1/',
                'post_comment called with bad bug url.');
            Y.Assert.areEqual(
                client.received[0][1][1],
                'newMessage',
                'post_comment called wrong named post.');
            Y.Assert.isTrue(no_op_called);
        },

        test_insert_comment_html: function () {
            // Test Comment.insert_comment_HTML
            var comment = this._get_mocked_comment();
            var reset_contents_called = false;
            comment.reset_contents = function () {
                reset_contents_called = true; 
            };
            comment.insert_comment_HTML('<span id="fake"></span>');
            Y.Assert.isTrue(reset_contents_called);
            Y.Assert.isObject(Y.one('#fake'));
        }
    }));

}, '0.1', {'requires': ['test', 'lp.testing.helpers', 'test-console',
                        'lp.app.comment']});
