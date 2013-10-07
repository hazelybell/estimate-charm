/* Copyright 2009-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

// XXX: rharding 2012-07-03 bug=1020671: The tests should be adjusted to not
// require the 1000s wait waiting for the animation. We should allow a
// skip_animation or some other method of allowing tests to run synchronously
// without wait times.

YUI.add('lp.registry.distroseriesdifferences_details.test', function (Y) {
    var module = Y.lp.registry.distroseriesdifferences_details;

    /**
     * Utility function to create a row of the diff pages.
     *
     * @param package_name {String} The name of the package for this row.
     * @param parent_version {String} The version for the package in the parent
     *     series.
     * @param derived_version {String} The version for the package in the derived
     *     series.
     * @missing_row {Boolean} If false, generate a row of the +localpackagediffs
     *      page, if true, generate a row of te +missingpackages page.
     */
    var create_row = function(package_name, parent_version, derived_version,
                             missing_row) {
        var derivedtd = '';
        if (!missing_row) {
            derivedtd = Y.Lang.sub(derivedtd_html, {
                package_name: package_name,
                derived_version: derived_version
            });
        }
        return Y.Lang.sub( row_html, {
            package_name: package_name,
            parent_version: parent_version,
            derived_version: derived_version,
            derivedrow: derivedtd
        });
    };

    var assertAllDisabled = function(node, selector) {
        var all_input_status = node.all(selector).get('disabled');
        Y.ArrayAssert.doesNotContain(false, all_input_status);
    };

    var assertAllEnabled = function(node, selector) {
        var all_input_status = node.all(selector).get('disabled');
        Y.ArrayAssert.doesNotContain(true, all_input_status);
    };

    var Comment = function () {
        this.data = {
            comment_date: "2011-08-08T13:15:50.636269+00:00",
            body_text: 'This is the comment',
            self_link:  ["https://lp.net/api/devel/u/d//+source/",
                         "evolution/+difference/ubuntu/warty/comments/6"
                        ].join(''),
            web_link: ["https://lp.net/d/d/+source/evolution/",
                       "+difference/ubuntu/warty/comments/6"
                      ].join('')
        };
        this.get = function (key) {
            return this.data[key];
        };
    };

    var dsd_uri = '/duntu/dwarty/+source/evolution/+difference/ubuntu/warty';
    var row_html = Y.one('#localpackagediffs-template').getContent();
    var derivedtd_html = Y.one('#derivedtd-template').getContent();
    var blacklist_html = Y.one('#blacklist_html').getContent();
    var extra_row = Y.one('#blacklist_extra_row').getContent();
    extra_row = Y.Lang.sub(extra_row, {
        blacklist_html: blacklist_html
    });
    var whole_table = Y.one('#blacklist_whole_table').getContent();
    whole_table = Y.Lang.sub(whole_table, {
        row: create_row('evolution', '2.0.9-1', '2.0.8-4', false),
        extra_row: extra_row
    });

    var tests = Y.namespace('lp.registry.distroseriesdifferences_details.test');
    tests.suite = new Y.Test.Suite('lp.registry.distroseriesdifferences_details Tests');
    tests.suite.add(new Y.Test.Case({
        name: 'expandable-row-widget',
        setUp: function() {
            module.io = new Y.lp.testing.mockio.MockIo();
            var row = create_row('evolution', '2.0.9-1', '2.0.8-4', false);
            Y.one("#placeholder").append(Y.Node.create(row));
            this.toggle = Y.one('a.toggle-extra');
        },

        tearDown: function () {
            Y.one('#placeholder').empty();
            delete this.toggle;
            module.io = Y.io;
        },

        test_initializer: function() {
            var row = new module.ExpandableRowWidget({toggle: this.toggle});
            Y.Assert.isTrue(this.toggle.hasClass('treeCollapsed'));
            Y.Assert.isTrue(this.toggle.hasClass('sprite'));
        },

        test_parse_row_data: function() {
            var row = new module.ExpandableRowWidget({toggle: this.toggle});
            var parsed = row.parse_row_data();
            var res = {
                source_name: 'evolution',
                parent_series_name: 'warty',
                parent_distro_name: 'ubuntu',
                nb_columns: 7};
            Y.ObjectAssert.areEqual(res, parsed);
        },

        test_expander_handler_adds_new_row: function() {
            var row = new module.ExpandableRowWidget({toggle: this.toggle});
            row._toggle.simulate('click');
            var new_row = row._row.next();
            Y.Assert.isTrue(new_row.hasClass('evolution'));
            Y.Assert.isTrue(new_row.hasClass('diff-extra'));
            Y.Assert.areEqual(7, new_row.one('td').getAttribute('colspan'));
        },

        test_expand_handler_toggles_hiding: function() {
            var row = new module.ExpandableRowWidget({toggle: this.toggle});
            Y.Assert.isTrue(row._toggle.hasClass('treeCollapsed'));
            // First click opens up the new row.
            row._toggle.simulate('click');
            var new_row = row._row.next();
            Y.Assert.isTrue(row._toggle.hasClass('treeExpanded'), 'is expanded');
            Y.Assert.isFalse(new_row.hasClass('hidden'), 'not hidden');
            Y.Assert.isTrue(new_row.one('div').hasClass('diff-extra-container'));
            // Second click hides it.
            row._toggle.simulate('click');
            Y.Assert.isTrue(row._toggle.hasClass('treeCollapsed'), 'is collapsed');
            Y.Assert.isTrue(new_row.hasClass('hidden'), 'is hidden');
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'package-diff',
        setUp: function() {
            Y.one("#placeholder").append(Y.Node.create(extra_row));
        },

        tearDown: function () {
            Y.one('#placeholder').empty();
        },

        test_vocabulary_helper: function() {
            // The vocabulary helper extracts the selected item from a
            // jsonified vocabulary.
            var voc = [
                {"token": "PENDING", "title": "Pending"},
                {"token": "COMPLETED", "selected": true, "title": "Completed"},
                {"token": "FAILED", "title": "Failed"}];
            var res = module.get_selected(voc);
            Y.Assert.areEqual('COMPLETED', res.token);
            Y.Assert.areEqual('Completed', res.title);
            var voc_nothing_selected = [
                {"token": "PENDING", "title": "Pending"},
                {"token": "COMPLETED", "title": "Completed"},
                {"token": "FAILED", "title": "Failed"}];
            Y.Assert.isUndefined(module.get_selected(voc_nothing_selected));
        },

        test_add_msg_node: function() {
            var msg_txt = 'Exemple text';
            var msg_node = Y.Node.create(msg_txt);
            placeholder = Y.one('#placeholder');
            module.add_msg_node(placeholder, msg_node);
            Y.Assert.areEqual(
                placeholder.one('.package-diff-placeholder').get('innerHTML'),
                msg_txt);
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'package-diff-update-interaction',
        setUp: function() {
            Y.one("#placeholder").append(Y.Node.create(whole_table));
            this.node = Y.one('.blacklist-options');
            this.commentWidget = null;
            this.widget = new module.BlacklistWidget({
                srcNode: this.node,
                sourceName: 'evolution',
                dsdLink: '/a/link',
                commentWidget: this.commentWidget
            });
            // Set the animation duration to 0.1 to avoid having to wait for its
            // completion for too long.
            this.widget.ANIM_DURATION = 0.1;
        },

        tearDown: function () {
            Y.one('#placeholder').empty();
            delete this.widget;

            if (!Y.Lang.isUndefined(this._fired)) {
                delete this._fired;
            }
        },

        assertIsLocked: function() {
            var node = this.widget.get('srcNode');
            Y.Assert.isNotNull(node.one('img[src="/@@/spinner"]'));
            assertAllDisabled(node, 'div.blacklist-options input');
        },

        assertIsUnlocked: function() {
            var node = this.widget.get('srcNode');
            Y.Assert.isNull(node.one('img[src="/@@/spinner"]'));
            assertAllEnabled(node, 'div.blacklist-options input');
        },

        test_lock: function() {
            this.widget.lock();
            this.assertIsLocked();
        },

        test_unlock: function() {
            this.widget.unlock();
            this.assertIsUnlocked();
        },

        test_lock_unlock: function() {
            this.widget.lock();
            this.widget.unlock();
            this.assertIsUnlocked();
        },

        patchNamedPost: function(method_name, expected_parameters) {
            var that = this;
            var comment_entry = new Comment();
            module.lp_client.named_post = function(url, func, config) {
                Y.Assert.areEqual(func, method_name);
                Y.ObjectAssert.areEqual(expected_parameters, config.parameters);
                that.assertIsLocked();
                config.on.success(comment_entry);
                that.assertIsUnlocked();
            };
        },

        test_initializer: function() {
            Y.Assert.areEqual(this.node, this.widget.get('srcNode'));
            Y.Assert.areEqual('evolution', this.widget.sourceName);
            Y.Assert.areEqual('/a/link', this.widget.dsdLink);
            Y.Assert.areEqual(
                this.latestCommentContainer,
                this.widget.latestCommentContainer);
            Y.Assert.areEqual(this.commentWidget, this.widget.commentWidget);
        },

        test_wire_blacklist_click: function() {
            var input = Y.one(
                'div.blacklist-options input[value="BLACKLISTED_CURRENT"]');
            var fired = false;

            var show_comment_overlay = function(target) {
                fired = true;
                Y.Assert.areEqual(input, target);
            };
            this.widget.show_comment_overlay = show_comment_overlay;
            input.simulate('click');

            Y.Assert.isTrue(fired);
        },

        test_wire_blacklist_changed: function() {
            var fired = false;

            var blacklist_submit_handler = function(arg1, arg2, arg3, arg4) {
                fired = true;
                Y.Assert.areEqual(1, arg1);
                Y.Assert.areEqual(2, arg2);
                Y.Assert.areEqual(3, arg3);
                Y.Assert.areEqual(4, arg4);
            };
            this.widget.blacklist_submit_handler = blacklist_submit_handler;
            this.widget.fire('blacklist_changed', 1, 2, 3, 4);
            Y.Assert.isTrue(fired);
        },

        test_containing_rows: function() {
            var expected = [Y.one('.evolution'), Y.one('#extra_row')];
            Y.ArrayAssert.itemsAreEqual(expected, this.widget.relatedRows);
        },

        test_show_comment_overlay_creates_overlay: function() {
            var input = Y.one('div.blacklist-options input');
            var overlay = this.widget.show_comment_overlay(input);
            // Check overlay's structure.
            Y.Assert.isInstanceOf(Y.lp.ui.FormOverlay, overlay);
            Y.Assert.isNotNull(overlay.form_node.one('textarea'));
            Y.Assert.areEqual(
                'OK',
                overlay.form_node.one('button[type="submit"]').get('text'));
            Y.Assert.areEqual(
                'Cancel',
                overlay.form_node.one('button[type="button"]').get('text'));
            Y.Assert.isTrue(overlay.get('visible'));
        },

        test_show_comment_overlay_cancel_hides_overlay: function() {
            var input = Y.one('div.blacklist-options input');
            var overlay = this.widget.show_comment_overlay(input);
            var cancel_button = overlay.form_node.one('button[type="button"]');
            Y.Assert.isTrue(overlay.get('visible'));
            cancel_button.simulate('click');
            Y.Assert.isFalse(overlay.get('visible'));
         },

        test_show_comment_overlay_ok_hides_overlay: function() {
            var input = Y.one('div.blacklist-options input');
            var overlay = this.widget.show_comment_overlay(input);
            Y.Assert.isTrue(overlay.get('visible'));
            overlay.form_node.one('button[type="submit"]').simulate('click');
            Y.Assert.isFalse(overlay.get('visible'));
        },

        test_show_comment_overlay_fires_event: function() {
            var input = Y.one('div.blacklist-options input[value="NONE"]');
            input.set('checked', true);
            var overlay = this.widget.show_comment_overlay(input);
            var event_fired = false;
            var method = null;
            var all = null;
            var comment = null;
            var target = null;

            var handleEvent = function(e, e_method, e_all, e_comment, e_target) {
                event_fired = true;
                method = e_method;
                all = e_all;
                comment = e_comment;
                target = e_target;
            };

            this.widget.on("blacklist_changed", handleEvent, this.widget);

            overlay.form_node.one('textarea').set('text', 'Test comment');
            overlay.form_node.one('button[type="submit"]').simulate('click');

            Y.Assert.isTrue(event_fired);
            Y.Assert.areEqual('unblacklist', method);
            Y.Assert.areEqual(false, all);
            Y.Assert.areEqual('Test comment', comment);
            Y.Assert.areEqual(input, target);
        },

        test_show_comment_overlay_fires_event_blacklist_all: function() {
            var input = Y.one(
                'div.blacklist-options input[value="BLACKLISTED_ALWAYS"]');
            input.set('checked', true);
            var overlay = this.widget.show_comment_overlay(input);
            var method = null;
            var all = null;
            var target = null;

            var handleEvent = function(e, e_method, e_all, e_comment, e_target) {
                method = e_method;
                all = e_all;
                target = e_target;
            };
            this.widget.on("blacklist_changed", handleEvent, this.widget);
            overlay.form_node.one('button[type="submit"]').simulate('click');

            Y.Assert.areEqual('blacklist', method);
            Y.Assert.areEqual(true, all);
            Y.Assert.areEqual(input, target);
        },

        test_show_comment_overlay_fires_event_blacklist: function() {
            var input = Y.one(
                'div.blacklist-options input[value="BLACKLISTED_CURRENT"]');
            input.set('checked', true);
            var overlay = this.widget.show_comment_overlay(input);
            var method = null;
            var all = null;
            var target = null;

            var handleEvent = function(e, e_method, e_all, e_comment, e_target) {
                method = e_method;
                all = e_all;
                target = e_target;
            };
            this.widget.on("blacklist_changed", handleEvent, this.widget);
            overlay.form_node.one('button[type="submit"]').simulate('click');

            Y.Assert.areEqual('blacklist', method);
            Y.Assert.areEqual(false, all);
            Y.Assert.areEqual(input, target);
        },

        test_blacklist_submit_handler_blacklist_null_comment_widget: function() {
            // The widget can cope with a null commentWidget.
            Y.Assert.isNull(this.widget.commentWidget);
            var input = Y.one(
                'div.blacklist-options input[value="BLACKLISTED_CURRENT"]');
            this.widget.blacklist_submit_handler(
                'blacklist', false, "Test comment", input);
        },

        test_blacklist_submit_handler_blacklist_simple: function() {
            var mockCommentWidget = Y.Mock();
            Y.Mock.expect(mockCommentWidget, {
                method: "display_new_comment",
                args: [Y.Mock.Value.Object]
            });
            this.widget.commentWidget = mockCommentWidget;

            this.patchNamedPost(
                'blacklist',
                {comment: 'Test comment', all: false});
            var input = Y.one(
                'div.blacklist-options input[value="BLACKLISTED_CURRENT"]');
            input.set('checked', false);

            var fired = 0;
            var listener = function(e) {
                // Only call resume if the test is waiting, this is
                // required because we sometimes hit this code before
                // we had the chance to call this.wait().
                fired += 1;
            };
            this.widget.on('blacklisting_animation_ended', listener);
            this.widget.blacklist_submit_handler(
                'blacklist', false, "Test comment", input);

            Y.Assert.isTrue(input.get('checked'));

            this.wait(function () {
                // There are two rows that get worked across.
                Y.Assert.areEqual(2, fired);
            }, 1000);
        },

        test_blacklist_submit_handler_blacklist_all: function() {
            var mockCommentWidget = Y.Mock();
            Y.Mock.expect(mockCommentWidget, {
                method: "display_new_comment",
                args: [Y.Mock.Value.Object]
            });
            this.widget.commentWidget = mockCommentWidget;

            this.patchNamedPost(
                'blacklist',
                {comment: 'Test comment', all: true});
            var input = Y.one(
                'div.blacklist-options input[value="BLACKLISTED_CURRENT"]');
            input.set('checked', false);

            var fired = 0;
            var listener = function(e) {
                // Only call resume if the test is waiting, this is
                // required because we sometimes hit this code before
                // we had the chance to call this.wait().
                fired += 1;
            };
            this.widget.on('blacklisting_animation_ended', listener);
            this.widget.blacklist_submit_handler(
                'blacklist', true, "Test comment", input);

            Y.Assert.isTrue(input.get('checked'));

            this.wait(function () {
                // There are two rows that get worked across.
                Y.Assert.areEqual(2, fired);
            }, 1000);
        },

        test_blacklist_submit_handler_unblacklist: function() {
            var fired = false;
            var mockCommentWidget = Y.Mock();
            Y.Mock.expect(mockCommentWidget, {
                method: "display_new_comment",
                args: [Y.Mock.Value.Object]
            });
            this.widget.commentWidget = mockCommentWidget;

            this.patchNamedPost(
                'unblacklist', {
                    comment: 'Test comment',
                    all: true
            });

            var input = Y.one('div.blacklist-options input[value="NONE"]');
            input.set('checked', false);

            var listener = function (ev) {
                fired = true;
            };

            this.widget.on('blacklisting_animation_ended', listener);
            this.widget.blacklist_submit_handler(
                'unblacklist', true, "Test comment", input);

            Y.Assert.isTrue(input.get('checked'));
            this.wait(function () {
                // There are two rows that get worked across.
                Y.Assert.isTrue(fired);
            }, 1000);
        },

        test_blacklist_submit_handler_failure: function() {
            var that = this;
            module.lp_client.named_post = function(url, func, config) {
                that.assertIsLocked();
                config.on.failure();
                that.assertIsUnlocked();
            };
            var input = Y.one('div.blacklist-options input');
            input.set('checked', false);
            this.widget.blacklist_submit_handler(
                null, 'unblacklist', true, "Test comment", input);
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'test-add-comment-widget',
        setUp: function() {
            Y.one("#placeholder").append(Y.Node.create(whole_table));
            this.latestCommentContainer = Y.one('td.latest-comment-fragment');
            this.addCommentPlaceholder = Y.one('div.add-comment-placeholder');
            this.apiUri = '/testuri/';
            this.widget = new module.AddCommentWidget({
                srcNode: this.node,
                apiUri: this.apiUri,
                latestCommentContainer: this.latestCommentContainer,
                addCommentPlaceholder: this.addCommentPlaceholder
                });
            this.widget.render(this.addCommentPlaceholder);
        },

        tearDown: function() {
            this.widget.destroy();
            Y.one('#placeholder').empty();
        },

        test_initializer: function() {
            Y.Assert.areEqual(
                this.latestCommentContainer, this.widget.latestCommentContainer);
            Y.Assert.areEqual(
                this.addCommentPlaceholder, this.widget.addCommentPlaceholder);
            Y.Assert.areEqual(
                this.apiUri, this.widget.apiUri);
        },

        test_comment_text_getter: function() {
            this.widget.get('srcNode').one('textarea').set('value', 'Content');
            Y.Assert.areEqual(
                'Content',
                this.widget.get('comment_text'));
        },

        test_comment_text_setter: function() {
            this.widget.set('comment_text', 'Content');
            Y.Assert.areEqual(
                'Content',
                this.widget.get('srcNode').one('textarea').get('value'));
        },

        test_slide_in: function() {
            // 'Manually' open the widget.
            var that = this;
            var fired = false;
            var node = this.widget.get('srcNode');
            node.one('div.widget-bd').setStyle('height', '1000px');
            var listener = function (e) {
                fired = true;
                that.resume();
            };
            this.widget.on('slid_in', listener);
            this.widget.slide_in();
            this.wait(function () {
                Y.Assert.isTrue(fired);
            }, 2000);
        },

        test_slide_out: function() {
            var fired = false;
            var that = this;
            var listener = function(e) {
                that.resume(function(){
                    fired = true;
                });
            };
            this.widget.on('slid_out', listener);
            this.widget.slide_out();
            this.wait(1000);
        },

        assertIsLocked: function() {
            var node = this.widget.get('srcNode');
            Y.Assert.isNotNull(node.one('img[src="/@@/spinner"]'));
            assertAllDisabled(node, 'textarea, button');
        },

        assertIsUnlocked: function() {
            var node = this.widget.get('srcNode');
            Y.Assert.isNull(node.one('img[src="/@@/spinner"]'));
            assertAllEnabled(node, 'textarea, button');
        },

        test_lock: function() {
            this.widget.lock();
            this.assertIsLocked();
        },

        test_unlock: function() {
            this.widget.unlock();
            this.assertIsUnlocked();
        },

        test_lock_unlock: function() {
            this.widget.lock();
            this.widget.unlock();
            this.assertIsUnlocked();
        },

        test_wire_click_add_comment_link: function() {
            var fired = false;
            var input = this.widget.get('srcNode').one('a.widget-hd');
            var that = this;
            var listener = function(e) {
                that.resume(function(){
                    fired = true;
                });
            };
            this.widget.on('slid_out', listener);
            input.simulate('click');
            this.wait();
        },

        test_wire_comment_added_calls_display_new_comment: function() {
            var fired = false;
            var comment_entry = new Comment();

            var display_new_comment = function(entry) {
                fired = true;
                Y.ObjectAssert.areEqual(comment_entry, entry);
            };
            this.widget.display_new_comment = display_new_comment;
            this.widget.fire('comment_added', comment_entry);

            Y.Assert.isTrue(fired);
         },

        test_wire_click_button_calls_add_comment_handler: function() {
            var input = this.widget.get('srcNode').one('button');
            var fired = false;
            var add_comment_handler = function() {
                fired = true;
            };
            this.widget.add_comment_handler = add_comment_handler;
            input.simulate('click');
            Y.Assert.isTrue(fired);
        },

        test_clean: function() {
            var that = this;
            var comment_text = 'Content';
            this.widget.get('srcNode').one('textarea').set('value', comment_text);
            var comment_entry = new Comment();
            var post_called = false;
            module.lp_client.named_post = function(url, method, config) {
                post_called = true;
                Y.Assert.areEqual('addComment', method);
                Y.Assert.areEqual(comment_text, config.parameters.comment);
                config.on.success(comment_entry);
            };
            // The event comment_added will be fired.
            var event_fired = false;
            event_handler = function(e) {
                event_fired = true;
                Y.ObjectAssert.areEqual(comment_entry, e.details[0]);
            };
            this.widget.on('comment_added', event_handler);
            this.widget.add_comment_handler();

            Y.Assert.areEqual('', this.widget.get('comment_text'));
            Y.Assert.isTrue(post_called);
            Y.Assert.isTrue(event_fired);
        },

        test_display_new_comment_success: function() {
            var that = this;
            var comment_html = '<span id="new_comment">Comment content.</span>';
            var comment_entry = new Comment();
            var get_called = false;
            module.lp_client.get = function(url, config) {
                get_called = true;
                config.on.success(comment_html);
            };
            // The method update_latest_comment will be called with the right
            // arguments.
            var update_latest_called = false;
            module.update_latest_comment = function(entry, node) {
                update_latest_called = true;
                Y.ObjectAssert.areEqual(comment_entry, entry);
                Y.Assert.areEqual(that.widget.latestCommentContainer, node);
            };
            this.widget.display_new_comment(comment_entry);

            // The new comment has been added to the list of comments.
            Y.Assert.areEqual(
                'Comment content.',
                this.widget.addCommentPlaceholder.previous().get('text'));
            Y.Assert.isTrue(get_called);
            Y.Assert.isTrue(update_latest_called);
        },

        test_display_new_comment_failure: function() {
            var comment_html = '<span id="new_comment">Comment content.</span>';
            var comment_entry = new Comment();
            var get_called = false;
            module.lp_client.get = function(url, config) {
                get_called = true;
                config.on.failure(comment_html);
            };
            // The method update_latest_comment won't.
            var update_latest_called = false;
            module.update_latest_comment = function(entry, node) {
                update_latest_called = true;
            };
            this.widget.display_new_comment(comment_entry);

            // The new comment has *not* been added to the list of comments.
            // The last existing comment is still displayed.
            Y.Assert.areEqual(
                'Mark S.',
                this.widget.addCommentPlaceholder.previous().one(
                    'a.person').get('text'));
            Y.Assert.isTrue(get_called);
            Y.Assert.isFalse(update_latest_called);
        },

        test_add_comment_handler_success: function() {
            var comment_text = 'Content';
            this.widget.get('srcNode').one('textarea').set('value', comment_text);
            var comment_entry = new Comment();
            var post_called = false;
            module.lp_client.named_post = function(url, method, config) {
                post_called = true;
                Y.Assert.areEqual('addComment', method);
                Y.Assert.areEqual(comment_text, config.parameters.comment);
                config.on.success(comment_entry);
            };
            // The event comment_added will be fired.
            var event_fired = false;
            event_handler = function(e) {
                event_fired = true;
                Y.ObjectAssert.areEqual(comment_entry, e.details[0]);
            };
            this.widget.on('comment_added', event_handler);

            this.widget.add_comment_handler();

            Y.Assert.areEqual('', this.widget.get('comment_text'));
            Y.Assert.isTrue(post_called);
            Y.Assert.isTrue(event_fired);
            this.assertIsUnlocked();
        },

        test_add_comment_handler_failure: function() {
            var comment_text = 'Content';
            this.widget.get('srcNode').one('textarea').set('value', comment_text);
            var post_called = false;
            module.lp_client.named_post = function(url, method, config) {
                post_called = true;
                config.on.failure();
            };
            this.widget.add_comment_handler();

            // The content has not been cleaned.
            Y.Assert.areEqual('Content', this.widget.get('comment_text'));
            Y.Assert.isTrue(post_called);
            this.assertIsUnlocked();
        },

        test_add_comment_handler_empty: function() {
            // An empty comment is treated as a mistake.
            var that = this;
            var comment_text = '';
            this.widget.get('srcNode').one('textarea').set('value', comment_text);
            var comment_entry = new Comment();
            var post_called = false;
            module.lp_client.named_post = function(url, method, config) {
                post_called = true;
            };
            this.widget.add_comment_handler();
            Y.Assert.isFalse(post_called);
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'test-add-comment-widget',

        setUp: function() {
            Y.one("#placeholder").append(Y.Node.create(whole_table));
            var first_poll = true;
            pending_voc = [
                {"token": "PENDING", "selected": true, "title": "Pending"},
                {"token": "COMPLETED", "title": "Completed"},
                {"token": "FAILED", "title": "Failed"}];
            completed_voc = [
                {"token": "PENDING", "title": "Pending"},
                {"token": "COMPLETED", "selected": true, "title": "Completed"},
                {"token": "FAILED", "title": "Failed"}];

            // Monkey patch request.
            module.lp_client.named_post = function(url, func, config) {
                config.on.success();};
            module.lp_client.named_get = function(url, func, config) {
                config.on.success();};
            module.lp_client.get = function(uri, config) {
                if (first_poll === true) {
                    first_poll = false;
                    config.on.success(pending_voc);
                }
                else {
                    config.on.success(completed_voc);
                }
            };
            module.poll_interval = 100;
        },

        tearDown: function () {
            Y.one('#placeholder').empty();
        },

        test_request_wrong_click: function() {
            // Click on the placeholder has no effect.
            // The listeners are on the link with class
            // '.package-diff-compute-request'.
            // bug=746277.
            var placeholder = Y.one('#placeholder');
            placeholder
                .one('#derived')
                    .removeClass('PENDING')
                        .addClass('FAILED');
            module.setup_packages_diff_states(
                placeholder.one('.diff-extra-container'), dsd_uri);
            var func_req;
            module.lp_client.named_post = function(url, func, config) {
                func_req = func;
                config.on.success();
            };
            var wrong_button = placeholder.one('.package-diff-placeholder');
            wrong_button.simulate('click');
            var package_diff = Y.one('#parent');

            // The request has not been triggered.
            Y.Assert.isTrue(package_diff.hasClass('request-derived-diff'));
        },

        test_request_package_diff_computation: function() {
            // A click on the button changes the package diff status and requests
            // the package diffs computation via post.
            var placeholder = Y.one('#placeholder');
            placeholder
                .one('#derived')
                .removeClass('PENDING')
                .addClass('FAILED');
            module.setup_packages_diff_states(
                placeholder.one('.diff-extra-container'), dsd_uri);
            var func_req;
            module.lp_client.named_post = function(url, func, config) {
                func_req = func;
                config.on.success();
            };
            var button = placeholder.one('.package-diff-compute-request');

            button.simulate('click');
            var package_diff = Y.one('#parent');

            Y.Assert.isTrue(package_diff.hasClass('PENDING'));
            Y.Assert.isFalse(package_diff.hasClass('request-derived-diff'));
            Y.Assert.areEqual('requestPackageDiffs', func_req);
            Y.Assert.isNotUndefined(package_diff.updater);

            // Let the polling happen.
            this.wait(function() {
                Y.Assert.isTrue(package_diff.hasClass('PENDING'));
                    this.wait(function() {
                        Y.Assert.isTrue(package_diff.hasClass('COMPLETED'));
                    }, module.poll_interval);
             }, module.poll_interval);
        },

        test_polling_for_pending_items: function() {
            // The polling has started on the pending package diff. The
            // status is being updated.
            var placeholder = Y.one('#placeholder');
            module.setup_packages_diff_states(
                placeholder.one('.diff-extra-container'), dsd_uri);
            var package_diff = Y.one('#derived');
            Y.Assert.isTrue(package_diff.hasClass('PENDING'));
            Y.Assert.isFalse(package_diff.hasClass('request-derived-diff'));
            this.wait(function() {
                Y.Assert.isTrue(package_diff.hasClass('PENDING'));
                    this.wait(function() {
                        Y.Assert.isTrue(package_diff.hasClass('COMPLETED'));
                    }, module.poll_interval);
            }, module.poll_interval);
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'form-parsing',
        tearDown: function () {
            Y.one('#placeholder').empty();
        },

        create_rows: function(missing_packages) {
            var placeholder = Y.one("#placeholder");
            rows_data = [
                ['evolution', '2.0.9-1', '2.0.8-4', missing_packages],
                ['package', '2.0', '1.0', missing_packages],
                ['package2', '4.0.4', '0.0.2', missing_packages],
                ['package3', '3.0.4', '0.8.2', missing_packages],
                ['package4', '2.0.4', '1.0.2', missing_packages],
                ['package5', '1.0.4', '0.2.2', missing_packages]
                ];

            var i;
            for (i=0; i<rows_data.length; i++) {
                var data = rows_data[i];
                var node = Y.Node.create(
                    create_row(data[0], data[1], data[2], data[3]));
                placeholder.append(node);
            }
        },

        checkPackage: function(package_name) {
            var placeholder = Y.one("#placeholder");
            var checkbox = placeholder.one('.' + package_name).one('input');
            checkbox.set('checked', true);
        },

        checkAllPackages: function() {
            var placeholder = Y.one("#placeholder");
            var checkboxes = placeholder.all('input');
            checkboxes.set('checked', true);
        },

        test_get_confirmation_header_number_of_packages_1: function() {
            this.create_rows(false);
            this.checkPackage('evolution');

            Y.Assert.areEqual(
                1,
                module.get_number_of_packages());
            Y.Assert.areEqual(
                "You're about to sync 1 package. Continue?",
                module.get_confirmation_header_number_of_packages().get(
                    'text'));
        },

        test_get_confirmation_header_number_of_packages_x: function() {
            this.create_rows(false);
            this.checkPackage('evolution');
            this.checkPackage('package');

            Y.Assert.areEqual(
                2,
                module.get_number_of_packages());
            Y.Assert.areEqual(
                "You're about to sync 2 packages. Continue?",
                module.get_confirmation_header_number_of_packages().get(
                    'text'));
        },

        test_get_packages_summary: function() {
            // get_packages_summary parses row from the +localpackagediffs
            // page to create a summary of the packages to be synced.
            this.create_rows(false);
            this.checkPackage('evolution');
            this.checkPackage('package2');

            Y.Assert.areEqual(
                ['<ul>',
                 '<li><b>evolution</b>: 2.0.9-1 ',
                 '→ 2.0.8-4</li>',
                 '<li><b>package2</b>: 4.0.4 → 0.0.2</li>',
                 '</ul>'
                ].join(''),
                module.get_packages_summary().get('innerHTML'));
        },

        test_get_packages_summary_croped: function() {
            // If more than MAX_PACKAGES are to be synced, the summary is
            // limited to MAX_PACKAGES and mentions 'and x more packages'.
            this.create_rows(false);
            this.checkAllPackages();
            module.MAX_PACKAGES = 1;

            Y.Assert.areEqual(
                ['<ul>',
                 '<li><b>evolution</b>: 2.0.9-1 ',
                 '→ 2.0.8-4</li>',
                 '</ul>',
                 '... and 5 more packages.'
                ].join(''),
                module.get_packages_summary().get('innerHTML'));
        },

        test_get_packages_summary_missingpackages: function() {
            // get_packages_summary can also parse the row from +missingpackages
            // with no derived_series version of the packages.
            this.create_rows(true);
            Y.one('#placeholder').all('input').set('checked', true);
            module.MAX_PACKAGES = 1;

            Y.Assert.areEqual(
                ['<ul>',
                 '<li><b>evolution</b>: 2.0.9-1</li>',
                 '</ul>',
                 '... and 5 more packages.'
                ].join(''),
                module.get_packages_summary().get('innerHTML'));
        }
    }));
}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'lp.testing.mockio', 'test-console',
        'lp.registry.distroseriesdifferences_details', 'node-event-simulate',
        'lp.soyuz.base', 'lp.anim', 'lp.ui.formoverlay', 'lp.ui.effects',
        'lp.soyuz.dynamic_dom_updater', 'event-simulate', 'io-base']
});
