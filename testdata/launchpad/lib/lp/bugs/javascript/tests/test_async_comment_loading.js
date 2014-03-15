/* Copyright 2011-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.bugs.async_comments.test', function (Y) {

    // Local aliases.
    var Assert = Y.Assert,
        ArrayAssert = Y.ArrayAssert;
    var module = Y.lp.bugs.bugtask_index;
    var suite = new Y.Test.Suite("Async comment loading tests");

    var comments_markup =
        "<div>This is a comment</div>" +
        "<div>So is this</div>" +
        "<div>So is this</div>" +
        "<div>And this, too.</div>";


    var tests = Y.namespace('lp.bugs.async_comments.test');
    tests.suite = new Y.Test.Suite('Async Comment Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'Basic async comment loading tests',

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to make
            // some things work as expected.
            Y.lp.client.Launchpad.prototype.named_post =
              function(url, func, config) {
                config.on.success();
              };
            LP = {
                'cache': {
                    'bug': {
                        self_link: "http://bugs.example.com/bugs/1234"
                    },
                    'context': {
                        self_link: "http://bugs.example.com/bugs/1234"
                    }
                }
            };
            // Some tests monkey-patch load_more_comments, so we save it
            // here to restore it after each test.
            this.old_load_more_comments = module.load_more_comments;

            // Add some HTML to the page for us to use.
            this.comments_container = Y.Node.create(
                '<div id="comments-container"></div>');
            this.add_comment_form_container = Y.Node.create(
                '<div id="add-comment-form-container" class="hidden"></div>');
            Y.one('body').appendChild(this.comments_container);
            Y.one('body').appendChild(this.add_comment_form_container);
        },

        tearDown: function() {
            this.comments_container.remove();
            this.add_comment_form_container.remove();
            // Restore load_more_comments in case it's been monkey-patched.
            module.load_more_comments = this.old_load_more_comments;
        },

        /**
         * load_more_comments() calls the passed batch_commments_url of the
         * current bug task and loads more comments from it.
         */
        test_load_more_comments_loads_more_comments: function() {
            var mockio = new Y.lp.testing.mockio.MockIo();
            module.load_more_comments(
                '', this.comments_container, mockio);
            mockio.success({
                responseText: comments_markup,
                responseHeaders: {'Content-Type': 'application/xhtml'}
            });
            Assert.areEqual(
                '<div>' + comments_markup + '</div>',
                this.comments_container.get('innerHTML'));
        },

        /**
         * load_more_comments() sets the display style on the comment
         * container to "block" so that its contents don't end up
         * overflowing other parts of the page.
         */
        test_load_more_comments_sets_container_display_style: function() {
            var mockio = new Y.lp.testing.mockio.MockIo();
            module.load_more_comments(
                '', this.comments_container, mockio);
            mockio.success({
                responseText: comments_markup,
                responseHeaders: {'Content-Type': 'application/xhtml'}
            });
            Assert.areEqual(
                'block', this.comments_container.getStyle('display'));
        },

        /**
         * load_more_comments() will show the "add comment" form once all
         * the comments have loaded.
         */
        test_load_more_comments_shows_add_comment_form: function() {
            var add_comment_form_container = Y.one(
                '#add-comment-form-container');
            Assert.isTrue(add_comment_form_container.hasClass('hidden'));
            var mockio = new Y.lp.testing.mockio.MockIo();
            module.load_more_comments(
                '', this.comments_container, mockio);
            mockio.success({
                responseText: comments_markup,
                responseHeaders: {'Content-Type': 'application/xhtml'}
            });
            Assert.isFalse(add_comment_form_container.hasClass('hidden'));
        },

        /**
         * load_more_comments() will call itself recursively until there are
         * no more comments to load.
         */
        test_load_more_comments_is_recursive: function() {
            var next_batch_url_div =
                '<div id="next-batch-url">https://launchpad.dev/</div>';
            var more_comments_to_load_markup =
                '<div>Here, have a comment. There are more where this came' +
                'from</div>';
            var mockio = new Y.lp.testing.mockio.MockIo();
            module.load_more_comments(
                '', this.comments_container, mockio);
            mockio.success({
                responseText: next_batch_url_div + more_comments_to_load_markup,
                responseHeaders: {'Content-Type': 'application/xhtml'}
            });
            mockio.success({
                responseText: comments_markup,
                responseHeaders: {'Content-Type': 'application/xhtml'}
            });
            var expected_markup =
                '<div>' + more_comments_to_load_markup + '</div>' +
                '<div>' + comments_markup + '</div>';
            Assert.areEqual(
                expected_markup, this.comments_container.get('innerHTML'));
        },

        /**
         * setup_show_more_comments_link() will set the onClick handler for
         * the link passed to it, and will also add a js-action class to the
         * link.
         */
        test_setup_show_more_comments_link_jsifies_link: function() {
            // We monkey-patch load_mode_comments so that we can use it to
            // test whether the link has been JS-ified properly.
            var load_more_comments_called = false;
            module.load_more_comments = function() {
                load_more_comments_called = true;
            };
            var link = Y.Node.create('<a href="#">A link</a>');
            module.setup_show_more_comments_link(link, '#', Y.Node.create());
            Assert.isTrue(link.hasClass('js-action'));
            link.simulate('click');
            Assert.isTrue(load_more_comments_called);
        },

        /**
         * setup_load_comments() will call load_more_comments if it's told
         * to.
         */
        test_setup_load_comments_calls_load_more_comments: function() {
            // Monkey-patch load_more_comments for the purposes of this
            // test.
            var load_more_comments_called = false;
            module.load_more_comments = function() {
                load_more_comments_called = true;
            };
            // A parameterless call to setup_load_comments won't call
            // load_more_comments.
            module.setup_load_comments();
            Assert.isFalse(load_more_comments_called);
            // Passing true for the load_more_comments parameter will cause
            // load_more_comments to be called.
            module.setup_load_comments(true);
            Assert.isTrue(load_more_comments_called);
        }

    }));
}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'test-console',
        'lp.bugs.bugtask_index', 'lp.client', 'event', 'node',
        'lp.testing.mockio', 'test', 'widget-stack', 'node-event-simulate']

});
