/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */
YUI.add('lp.structural_subscription.test', function (Y) {
    var tests = Y.namespace('lp.structural_subscription.test');

    tests.suite = new Y.Test.Suite("Structural subscription overlay tests");

    var context;
    var test_case;

    // Local aliases
    var Assert = Y.Assert,
        ArrayAssert = Y.ArrayAssert,
        module = Y.lp.registry.structural_subscription;

    // Expected content box.
    var content_box_name = 'ss-content-box';
    var content_box_id = '#' + content_box_name;

    var target_link_class = '.menu-link-subscribe_to_bug_mail';

    function array_compare(a,b) {
        if (a.length !== b.length) {
            return false;
        }
        a.sort();
        b.sort();
        var i;
        for (i=0; i<a.length; i++) {
            if (a[i] !== b[i]) {
                return false;
            }
        }
        return true;
    }

    function create_test_node() {
        var test_node = Y.Node.create('<div id="test-content">')
            .append(Y.Node.create('<div></div>')
                .set('id', content_box_name));
        test_node.append(Y.Node.create(
            '<a href="#" class="menu-link-subscribe_to_bug_mail">'+
            'A link, a link, my kingdom for a link</a>'));

        return test_node;
    }

    function remove_test_node() {
        Y.one('body').removeChild(Y.one('#test-content'));
        var error_overlay = Y.one('.yui3-lazr-formoverlay');
        if (Y.Lang.isValue(error_overlay)) {
            Y.one('body').removeChild(error_overlay);
        }
    }

    function test_checked(list, expected) {
        var item, i;
        var length = list.size();
        for (i=0; i < length; i++) {
            item = list.item(i);
            if (item.get('checked') !== expected) {
                return false;
            }
        }
        return true;
    }

    function monkeypatch_LP() {
          // Monkeypatch LP to avoid network traffic and to allow
          // insertion of test data.
          var original_lp = window.LP;
          window.LP = {
            links: {},
            cache: {}
          };

          LP.cache.context = {
            title: 'Test Project',
            self_link: 'https://launchpad.dev/api/test_project'
          };
          LP.cache.administratedTeams = [];
          LP.cache.importances = ['Unknown', 'Critical', 'High', 'Medium',
                                  'Low', 'Wishlist', 'Undecided'];
          LP.cache.statuses = ['New', 'Incomplete', 'Opinion',
                               'Invalid', 'Won\'t Fix', 'Expired',
                               'Confirmed', 'Triaged', 'In Progress',
                               'Fix Committed', 'Fix Released', 'Unknown'];
          LP.cache.information_types = ['Public', 'Public Security',
                                        'Private Security', 'Private',
                                        'Proprietary'];
          LP.links.me = 'https://launchpad.dev/api/~someone';
          return original_lp;
    }

    // DELETE uses Y.io directly as of this writing, so we cannot stub it
    // here.

    function make_lp_client_stub() {
        return new Y.lp.testing.helpers.LPClient();
    }

    test_case = new Y.Test.Case({
        name: 'structural_subscription_overlay',

        _should: {
            error: {
                test_setup_config_none: new Error(
                    'Missing config for structural_subscription.'),
                test_setup_config_no_content_box: new Error(
                    'Structural_subscription configuration has undefined '+
                    'properties.')
                }
        },

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to allow
            // insertion of test data.
            window.LP = {
                links: {},
                cache: {}
            };
            LP.cache.context = {
                title: 'Test Project',
                self_link: 'https://launchpad.dev/api/test_project'
            };
            LP.cache.administratedTeams = [];
            LP.cache.importances = [];
            LP.cache.statuses = [];
            LP.cache.information_types = [];

            this.configuration = {
                content_box: content_box_id
            };
            this.content_node = create_test_node();
            Y.one('body').appendChild(this.content_node);
        },

        tearDown: function() {
            //delete this.configuration;
            remove_test_node();
            delete this.content_node;
            delete this.configuration.lp_client;
            delete this.content_node;
        },

        test_setup_config_none: function() {
            // The config passed to setup may not be null.
            module.setup();
        },

        test_setup_config_no_content_box: function() {
            // The config passed to setup must contain a content_box.
            module.setup({});
        },

        test_anonymous: function() {
            // The link should not be shown to anonymous users so
            // 'setup' should not do anything in that case.  If it
            // were successful, the lp_client would be defined after
            // setup is called.
            LP.links.me = undefined;
            Assert.isUndefined(module.lp_client);
            module.setup(this.configuration);
            Assert.isUndefined(module.lp_client);
        },

        test_logged_in_user: function() {
            // If there is a logged-in user, setup is successful
            LP.links.me = 'https://launchpad.dev/api/~someone';
            Assert.isUndefined(module.lp_client);
            module.setup(this.configuration);
            Assert.isNotUndefined(module.lp_client);
        },

        test_list_contains: function() {
            // Validate that the list_contains function actually reports
            // whether or not an element is in a list.
            var list = ['a', 'b', 'c'];
            Assert.isTrue(module._list_contains(list, 'b'));
            Assert.isFalse(module._list_contains(list, 'd'));
            Assert.isFalse(module._list_contains([], 'a'));
            Assert.isTrue(module._list_contains(['a', 'a'], 'a'));
            Assert.isFalse(module._list_contains([], ''));
            Assert.isFalse(module._list_contains([], null));
            Assert.isFalse(module._list_contains(['a'], null));
            Assert.isFalse(module._list_contains([]));
        },

        test_make_selector_controls: function() {
            // Verify the creation of select all/none controls.
            var selectors = module.make_selector_controls('sharona');
            Assert.areEqual(
                'Select all', selectors.all_link.get('text'));
            Assert.areEqual(
                'Select none', selectors.none_link.get('text'));
            Assert.areEqual(
                'sharona-selectors', selectors.node.get('id'));
        }
    });
    tests.suite.add(test_case);

    test_case = new Y.Test.Case({
        name: 'Structural Subscription Overlay save_subscription',

        _should: {
            error: {}
        },

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
                    context.url = url;
                    context.func = func;
                    context.config = config;
                    // No need to call the on.success handler.
                };
            LP.cache.context = {
                title: 'Test Project',
                self_link: 'https://launchpad.dev/api/test_project'
            };
            LP.links.me = 'https://launchpad.dev/api/~someone';
            LP.cache.administratedTeams = [];
            LP.cache.importances = [];
            LP.cache.statuses = [];
            LP.cache.information_types = [];

            this.configuration = {
                content_box: content_box_id
            };
            this.content_node = create_test_node();
            Y.one('body').appendChild(this.content_node);

            this.bug_filter = {
                uri:
                    '/api/devel/firefox/+subscription/mark/+filter/28'
            };
            this.form_data = {
                recipient: ['user']
            };
            context = {};

            // Get the save subscription handler with empty success handler.
            this.save_subscription = module._make_add_subscription_handler(
                function() {});
        },

        tearDown: function() {
            delete this.configuration;
            remove_test_node();
            delete this.content_node;
        },

        test_user_recipient: function() {
            // When the user selects themselves as the recipient, the current
            // user's URI is used as the recipient value.
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            this.form_data.recipient = ['user'];
            this.save_subscription(this.form_data);
            Assert.areEqual(
                LP.links.me,
                context.config.parameters.subscriber);
        },

        test_team_recipient: function() {
            // When the user selects a team as the recipient, the selected
            // team's URI is used as the recipient value.
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            this.form_data.recipient = ['team'];
            this.form_data.team = ['https://launchpad.dev/api/~super-team'];
            this.save_subscription(this.form_data);
            Assert.areEqual(
                this.form_data.team[0],
                context.config.parameters.subscriber);
        }
    });
    tests.suite.add(test_case);

    test_case = new Y.Test.Case({
        name: 'Structural Subscription validation tests',

        _should: {
            error: {
                }
        },

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to allow
            // insertion of test data.
            window.LP = {
                links: {},
                cache: {}
            };

        },

        test_get_error_for_tags_list_valid: function() {
            // Valid tags list is a space-separated list of tags
            // consisting of all lowercase and digits and potentially
            // '+', '-', '.' in non-initial characters.
            var tags = 'tag1 tag+2  tag.3 tag-4 5tag';
            Assert.isNull(module._get_error_for_tags_list(tags));
        },

        assertHasErrorInTagsList: function(tags) {
            var error_text = module._get_error_for_tags_list(tags);
            Assert.isNotNull(error_text);
            Assert.areEqual(
                'Tags can only contain lowercase ASCII letters, ' +
                    'digits 0-9 and symbols "+", "-" or ".", and they ' +
                    'must start with a lowercase letter or a digit.',
                error_text);
        },


        test_get_error_for_tags_list_uppercase: function() {
            // Uppercase is not allowed in tags.
            this.assertHasErrorInTagsList('Tag');
        },

        test_get_error_for_tags_list_invalid_characters: function() {
            // Anything other than lowercase, digits or '+', '-' and '.'
            // is invalid in tags.
            this.assertHasErrorInTagsList('tag#!');
        },

        test_get_error_for_tags_list_special_characters: function() {
            // Even if '+', '-' or '.' are allowed in tags,
            // they must not be at the beginning of a tag.
            this.assertHasErrorInTagsList('tag1 +tag2 -tag3 .tag4');
        }
    });
    tests.suite.add(test_case);

    tests.suite.add(new Y.Test.Case({
        name: 'Dialog title ellipsis',

        _should: {error: {}},

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to allow
            // insertion of test data.
            window.LP = {
                links: {},
                cache: {}
            };

            this.project_title = 'A very long name for the current project';
            LP.cache.context = {
                title: this.project_title,
                self_link: 'https://launchpad.dev/api/test_project'
            };
            LP.cache.administratedTeams = [];
            LP.cache.importances = [];
            LP.cache.statuses = [];
            LP.cache.information_types = [];
            LP.links.me = 'https://launchpad.dev/api/~someone';

            var lp_client = function() {};
            this.configuration = {
                content_box: content_box_id,
                lp_client: lp_client
            };

            this.content_node = create_test_node();
            Y.one('body').appendChild(this.content_node);
            this.using_ellipsis_hack = module.using_ellipsis_hack;
            module.using_ellipsis_hack = true;
        },

        tearDown: function() {
            remove_test_node();
            delete this.content_node;
            module.using_ellipsis_hack = this.using_ellipsis_hack;
        },

        test_title_ellipsisification: function() {
            // Long titles are cut down.
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            overlay = Y.one('#accordion-overlay');
            // This is the title we would expect if there were no shortening.
            var header = Y.one(content_box_id).one('h2').get('text');
            // The actual title is a prefix of the unabridged title.
            var full_title = (
                'Add a mail subscription for ' + this.project_title);
            Assert.areEqual(0, full_title.search(header));
        }

    }));

    test_case = new Y.Test.Case({
        name: 'Structural Subscription interaction tests',

        _should: {
            error: {
                test_setup_overlay_missing_content_box: new Error(
                    'Node not found: #sir-not-appearing-in-this-test')
                }
        },

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to allow
            // insertion of test data.
            window.LP = {
                links: {},
                cache: {}
            };

            LP.cache.context = {
                title: 'Test',
                self_link: 'https://launchpad.dev/api/test_project'
            };
            LP.cache.administratedTeams = [];
            LP.cache.importances = [];
            LP.cache.statuses = [];
            LP.cache.information_types = [];
            LP.links.me = 'https://launchpad.dev/api/~someone';

            var lp_client = function() {};
            this.configuration = {
                content_box: content_box_id,
                lp_client: lp_client
            };

            this.content_node = create_test_node();
            Y.one('body').appendChild(this.content_node);

            // Monkey patch effects duration to make effects instant.
            // This keeps wait times to a minimum.
            this.original_defaults = Y.lp.ui.effects.slide_effect_defaults;
            Y.lp.ui.effects.slide_effect_defaults.duration = 0;
        },

        tearDown: function() {
            Y.lp.ui.effects.slide_effect_defaults = this.original_defaults;
            remove_test_node();
            delete this.content_node;
        },

        test_setup_overlay: function() {
            // At the outset there should be no overlay.
            var overlay = Y.one('#accordion-overlay');
            Assert.isNull(overlay);
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            // After the setup the overlay should be in the DOM.
            overlay = Y.one('#accordion-overlay');
            Assert.isNotNull(overlay);
            var header = Y.one(content_box_id).one('h2');
            Assert.areEqual(
                'Add a mail subscription for Test bugs',
                header.get('text'));
            var bug_tags_node = Y.one(".bug-tag-complete");
            Assert.isInstanceOf(Y.Node, bug_tags_node);
        },

        test_clean_up_overlay: function() {
            // When the overlay is hidden, resources are cleaned up..
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            var cancel_button = Y.one('[name="field.actions.cancel"]');
            var called = false;
            module.bug_tag_completer.after('destroy', function() {
                called = true;
            });
            cancel_button.simulate('click');
            Assert.isTrue(called);
        },

        test_focused_form_child: function() {
            // When the overlay is shown, the first form child is focused.
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            var first_input = Y.Node.create('<input type="text" name="t" />');
            var focused = false;
            first_input.on('focus', function(e) {
                focused = true;
            });
            module._add_subscription_overlay.form_node.insert(first_input, 0);
            module._add_subscription_overlay.hide();
            first_input.blur();
            module._add_subscription_overlay.show();
            Assert.isTrue(focused, "The first input was not focused.");
        },

        test_setup_overlay_missing_content_box: function() {
            // Pass in a content_box with a missing id to trigger an error.
            this.configuration.content_box =
                '#sir-not-appearing-in-this-test';
            module.setup(this.configuration);
            module._setup_overlay(this.configuration.content_box);
        },

        test_initial_state: function() {
            // When initialized the <div> elements for the filter
            // wrapper and the accordion wrapper should be collapsed.
            module.setup(this.configuration);
            // Simulate a click on the link to open the overlay.
            var link = Y.one('.menu-link-subscribe_to_bug_mail');
            link.simulate('click');
            var filter_wrapper = Y.one('#filter-wrapper');
            var accordion_wrapper = Y.one('#accordion-wrapper');
            Assert.isTrue(filter_wrapper.hasClass('lazr-closed'));
            Assert.isTrue(accordion_wrapper.hasClass('lazr-closed'));
            var close_link = Y.one('a.close-button');
            Y.Assert.isTrue(close_link.get('region').height > 0);
            Y.Assert.isTrue(
                close_link.getComputedStyle('visibility') === 'visible');
        },

        test_added_or_changed_toggles: function() {
            // Test that the filter wrapper opens and closes in
            // response to the added_or_changed radio button.
            module.setup(this.configuration);
            // Simulate a click on the link to open the overlay.
            var link = Y.one('.menu-link-subscribe_to_bug_mail');
            link.simulate('click');
            var added_changed = Y.one('#added-or-changed');
            Assert.isFalse(added_changed.get('checked'));
            var filter_wrapper = Y.one('#filter-wrapper');
            // Initially closed.
            Assert.isTrue(filter_wrapper.hasClass('lazr-closed'));
            // Opens when selected.
            added_changed.simulate('click');
            this.wait(function() {
                Assert.isTrue(filter_wrapper.hasClass('lazr-opened'));
            }, 10);
            // Closes when deselected.
            Y.one('#added-or-closed').simulate('click');
            this.wait(function() {
                Assert.isTrue(filter_wrapper.hasClass('lazr-closed'));
            }, 10);
        },

        test_advanced_filter_toggles: function() {
            // Test that the accordion wrapper opens and closes in
            // response to the advanced filter check box.
            module.setup(this.configuration);
            // Simulate a click on the link to open the overlay.
            var link = Y.one('.menu-link-subscribe_to_bug_mail');
            link.simulate('click');
            var added_changed = Y.one('#added-or-changed');
            added_changed.set('checked', true);

            // Initially closed.
            var advanced_filter = Y.one('#advanced-filter');
            Assert.isFalse(advanced_filter.get('checked'));
            var accordion_wrapper = Y.one('#accordion-wrapper');
            this.wait(function() {
                Assert.isTrue(accordion_wrapper.hasClass('lazr-closed'));
            }, 10);
            // Opens when selected.
            advanced_filter.set('checked', true);
            this.wait(function() {
                Assert.isTrue(accordion_wrapper.hasClass('lazr-opened'));
            }, 10);
            // Closes when deselected.
            advanced_filter.set('checked', false);
            this.wait(function() {
                Assert.isTrue(accordion_wrapper.hasClass('lazr-closed'));
            }, 10);
        },

        test_importances_select_all_none: function() {
            // Test the select all/none functionality for the importances
            // accordion pane.
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            var checkboxes = Y.all('input[name="importances"]');
            var select_all = Y.one('#importances-selectors > a.select-all');
            var select_none = Y.one('#importances-selectors > a.select-none');
            Assert.isTrue(test_checked(checkboxes, true));
            // Simulate a click on the select_none control.
            select_none.simulate('click');
            Assert.isTrue(test_checked(checkboxes, false));
            // Simulate a click on the select_all control.
            select_all.simulate('click');
            Assert.isTrue(test_checked(checkboxes, true));
        },

        test_statuses_select_all_none: function() {
            // Test the select all/none functionality for the statuses
            // accordion pane.
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            var checkboxes = Y.all('input[name="statuses"]');
            var select_all = Y.one('#statuses-selectors > a.select-all');
            var select_none = Y.one('#statuses-selectors > a.select-none');
            Assert.isTrue(test_checked(checkboxes, true));
            // Simulate a click on the select_none control.
            select_none.simulate('click');
            Assert.isTrue(test_checked(checkboxes, false));
            // Simulate a click on the select_all control.
            select_all.simulate('click');
            Assert.isTrue(test_checked(checkboxes, true));
        }

    });
    tests.suite.add(test_case);

    test_case = new Y.Test.Case({
        // Test the setup method.
        name: 'Structural Subscription error handling',

        _should: {
            error: {
                }
        },

        setUp: function() {
          // Monkeypatch LP to avoid network traffic and to allow
          // insertion of test data.
          this.original_lp = monkeypatch_LP();

          this.configuration = {
              content_box: content_box_id,
              lp_client: make_lp_client_stub()
          };

          this.content_node = create_test_node();
          Y.one('body').appendChild(this.content_node);
        },

        tearDown: function() {
            window.LP = this.original_lp;
            remove_test_node();
            delete this.content_node;
        },

        test_overlay_error_handling_adding: function() {
            // Verify that errors generated during adding of a filter are
            // displayed to the user.
            this.configuration.lp_client.named_post.fail = true;
            this.configuration.lp_client.named_post.args = [true, true];
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            // After the setup the overlay should be in the DOM.
            overlay = Y.one('#accordion-overlay');
            Assert.isNotNull(overlay);
            submit_button = Y.one('.yui3-lazr-formoverlay-actions button');
            submit_button.simulate('click');

            var error_box = Y.one('.yui3-lazr-formoverlay-errors');
            Assert.areEqual(
                'The following errors were encountered:',
                error_box.get('text').trim());
        },

        test_spinner_removed_on_error: function() {
            // The spinner is removed from the submit button after a failure.
            this.configuration.lp_client.named_post.fail = true;
            this.configuration.lp_client.named_post.halt = true;
            this.configuration.lp_client.named_post.args = [true, true];
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            // After the setup the overlay should be in the DOM.
            overlay = Y.one('#accordion-overlay');
            Assert.isNotNull(overlay);
            submit_button = Y.one('.yui3-lazr-formoverlay-actions button');
            submit_button.simulate('click');
            // We are now looking at the state after the named post has been
            // called, but before it has returned with a failure.
            // The overlay should still be visible.
            Assert.isTrue(module._add_subscription_overlay.get('visible'));
            // The spinner should be spinning.
            Assert.isTrue(submit_button.hasClass('spinner'));
            Assert.isFalse(submit_button.hasClass('lazr-pos'));
            // Now we resume the call to trigger the failure.
            this.configuration.lp_client.named_post.resume();
            // The spinner is gone.
            Assert.isTrue(submit_button.hasClass('lazr-pos'));
            Assert.isFalse(submit_button.hasClass('spinner'));
        },

        test_overlay_error_handling_patching: function() {
            // Verify that errors generated during patching of a filter are
            // displayed to the user.
            var original_delete_filter = module._delete_filter;
            module._delete_filter = function() {};
            this.configuration.lp_client.patch.fail = true;
            this.configuration.lp_client.patch.args = [true, true];
            this.configuration.lp_client.named_post.args = [
                {'getAttrs': function() { return {}; }}];
            module.setup(this.configuration);
            module._show_add_overlay(this.configuration);
            // After the setup the overlay should be in the DOM.
            overlay = Y.one('#accordion-overlay');
            Assert.isNotNull(overlay);
            submit_button = Y.one('.yui3-lazr-formoverlay-actions button');
            submit_button.simulate('click');

            // Put this stubbed function back.
            module._delete_filter = original_delete_filter;

            var error_box = Y.one('.yui3-lazr-formoverlay-errors');
            Assert.areEqual(
                'The following errors were encountered:',
                error_box.get('text').trim());
        }

    });
    tests.suite.add(test_case);

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription team contact',

        _should: {error: {}},

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to allow
            // insertion of test data.
            this.original_lp = monkeypatch_LP();

            LP.cache.subscription_info = [{
                target_url: 'http://example.com',
                target_title:'Example project',
                filters: [{
                    filter: {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: true,
                    is_muted: false,
                    team_has_contact_address: true,
                    user_is_team_admin: false,
                    subscriber_is_team: true,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick'
                }]
            }];
            this.configuration = {
                content_box: content_box_id,
                lp_client: make_lp_client_stub()
            };

            this.content_node = create_test_node();
            Y.one('body').appendChild(this.content_node);
        },

        tearDown: function() {
            window.LP = this.original_lp;
            remove_test_node();
            Y.one('#request-notifications').empty();
            delete this.content_node;
        },

        test_administrative_change_link: function() {
            var filter_info = {
                    filter: {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: true,
                    is_muted: false,
                    team_has_contact_address: true,
                    user_is_team_admin: false,
                    user_is_on_team_mailing_list: true,
                    subscriber_is_team: true,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick'
            };
            var node = module._create_filter_node(
                'ID', filter_info, filter_info.filter);
            var content = node.getContent();
            // If a subscription is via a team and the user isn't a team
            // admin and the team has a contact address, the user gets a link
            // to request the administrators change the subscription or drop
            // the contact address.
            Assert.areNotEqual(
                -1,
                content.search(/Request team administrators change/));
            // If the team's contact address is to a (launchpad-managed)
            // mailing list, then the pre-filled in email message is phrased
            // accordingly.
            Assert.areNotEqual(
                -1,
                content.search(/subscribe%20to%20the%20team/));
        },

        test_administrative_change_link_no_mailing_list: function() {
            var filter_info = {
                    filter: {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: true,
                    is_muted: false,
                    team_has_contact_address: true,
                    user_is_team_admin: false,
                    user_is_on_team_mailing_list: false,
                    subscriber_is_team: true,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick'
            };
            var node = module._create_filter_node(
                'ID', filter_info, filter_info.filter);
            var content = node.getContent();
            // If a subscription is via a team and the user isn't a team
            // admin and the team has a contact address, the user gets a link
            // to request the administrators change the subscription or drop
            // the contact address.
            Assert.areNotEqual(
                -1,
                content.search(/Request team administrators change/));
            // If the team's contact address is not a (launchpad-managed)
            // mailing list, then the pre-filled in email message is phrased
            // accordingly.
            Assert.areNotEqual(
                -1,
                content.search(/be%20a%20part%20of%20the%20team/));
        },

        test_mute_not_shown_when_ineffectual: function() {
            // If muting the subscription in question won't have an effect,
            // then the mute link isn't shown.
            var filter_info = {
                    filter: {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: false,
                    is_muted: false,
                    team_has_contact_address: true,
                    user_is_team_admin: false,
                    user_is_on_team_mailing_list: true,
                    subscriber_is_team: true,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick'
            };
            var node = module._create_filter_node(
                'ID', filter_info, filter_info.filter);
            var content = node.getContent();
            Assert.areEqual(
                -1,
                content.search(/Stop my emails/));
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription: deleting failed filters',

        _should: {error: {}},

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to allow
            // insertion of test data.
            this.original_lp = window.LP;
            window.LP = {
                links: {},
                cache: {}
            };
            LP.cache.context = {
                self_link: 'https://launchpad.dev/api/test_project'
            };
            LP.links.me = 'https://launchpad.dev/api/~someone';
            LP.cache.administratedTeams = [];
        },

        tearDown: function() {
            window.LP = this.original_lp;
        },

        test_delete_on_patch_failure: function() {
            // Creating a filter is a two step process.  First it is created
            // and then patched.  If the PATCH fails, then we should DELETE
            // the undifferentiated filter.

            // First we inject our own delete_filter implementation that just
            // tells us that it was called.
            var original_delete_filter = module._delete_filter;
            var delete_called = false;
            module._delete_filter = function() {
                delete_called = true;
            };
            var patch_failed = false;

            var TestBugFilter = function() {};
            TestBugFilter.prototype = {
                'getAttrs': function () {
                    return {};
                }
            };

            // Now we need an lp_client that will appear to succesfully create
            // the filter but then fail to patch it.
            var TestClient = function() {};
            TestClient.prototype = {
                'named_post': function (uri, operation_name, config) {
                    if (operation_name === 'addBugSubscriptionFilter') {
                        config.on.success(new TestBugFilter());
                    } else {
                        throw new Error('unexpected operation');
                    }
                },
                'patch': function(uri, representation, config, headers) {
                    config.on.failure(true, {'status':400});
                    patch_failed = true;
                }
            };
            module.lp_client = new TestClient();

            // OK, we're ready to add the bug filter and let the various
            // handlers be called.
            module._add_bug_filter(LP.links.me, 'this is a test');
            // Put some functions back.
            module._delete_filter = original_delete_filter;

            // Delete should have been called and the patch has failed.
            Assert.isTrue(delete_called);
            Assert.isTrue(patch_failed);
        }

    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription validate_config',

        _should: {
            error: {
                test_setup_config_none: new Error(
                    'Missing config for structural_subscription.'),
                test_setup_config_no_content_box: new Error(
                    'Structural_subscription configuration has undefined '+
                    'properties.')
                }
        },

        // Included in _should/error above.
        test_setup_config_none: function() {
            // The config passed to setup may not be null.
            module._validate_config();
        },

        // Included in _should/error above.
        test_setup_config_no_content_box: function() {
            // The config passed to setup must contain a content_box.
            module._validate_config({});
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription extract_form_data',

        // Verify that all the different values of the structural subscription
        // add/edit form are correctly extracted by the extract_form_data
        // function.

        _should: {
            error: {
                }
            },

        test_extract_description: function() {
            var form_data = {
                name: ['filter description'],
                events: [],
                filters: []
            };
            var patch_data = module._extract_form_data(form_data);
            Assert.areEqual(patch_data.description, form_data.name[0]);
        },

        test_extract_description_trim: function() {
            // Any leading or trailing whitespace is stripped from the
            // description.
            var form_data = {
                name: ['  filter description  '],
                events: [],
                filters: []
            };
            var patch_data = module._extract_form_data(form_data);
            Assert.areEqual('filter description', patch_data.description);
        },

        test_extract_chattiness_lifecycle: function() {
            var form_data = {
                name: [],
                events: ['added-or-closed'],
                filters: []
            };
            var patch_data = module._extract_form_data(form_data);
            Assert.areEqual(
                patch_data.bug_notification_level, 'Lifecycle');
        },

        test_extract_chattiness_discussion: function() {
            var form_data = {
                name: [],
                events: [],
                filters: []
            };
            var patch_data = module._extract_form_data(form_data);
            Assert.areEqual(
                patch_data.bug_notification_level, 'Details');
        },

        test_extract_chattiness_details: function() {
            var form_data = {
                name: [],
                events: [],
                filters: ['include-comments']
            };
            var patch_data = module._extract_form_data(form_data);
            Assert.areEqual(
                patch_data.bug_notification_level, 'Discussion');
        },

        test_extract_tags: function() {
            var form_data = {
                name: [],
                events: [],
                filters: ['advanced-filter'],
                tags: [' one two THREE '],
                tag_match: [''],
                importances: [],
                statuses: [],
                information_types: []
            };
            var patch_data = module._extract_form_data(form_data);
            // Note that the tags are converted to lower case
            // and outer white-space is stripped.
            ArrayAssert.itemsAreEqual(
                patch_data.tags, ['one', 'two', 'three']);
        },

        test_extract_find_all_tags_true: function() {
            var form_data = {
                name: [],
                events: [],
                filters: ['advanced-filter'],
                tags: ['tag'],
                tag_match: ['match-all'],
                importances: [],
                statuses: [],
                information_types: []
            };
            var patch_data = module._extract_form_data(form_data);
            Assert.isTrue(patch_data.find_all_tags);
        },

        test_extract_find_all_tags_false: function() {
            var form_data = {
                name: [],
                events: [],
                filters: ['advanced-filter'],
                tags: ['tag'],
                tag_match: [],
                importances: [],
                statuses: [],
                information_types: []
            };
            var patch_data = module._extract_form_data(form_data);
            Assert.isFalse(patch_data.find_all_tags);
        },

        test_all_values_set: function() {
            // We need all the values to be set (even if empty) because
            // PATCH expects a set of changes to make and any unspecified
            // attributes will retain the previous value.
            var form_data = {
                name: [],
                events: [],
                filters: [],
                tags: ['tag'],
                tag_match: ['match-all'],
                importances: ['importance1'],
                statuses: ['status1'],
                information_types: ['informationtype1']
            };
            var patch_data = module._extract_form_data(form_data);
            // Since advanced-filter isn't set, all the advanced values should
            // be empty/false despite the form values.
            Assert.isFalse(patch_data.find_all_tags);
            ArrayAssert.isEmpty(patch_data.tags);
            ArrayAssert.isEmpty(patch_data.importances);
            ArrayAssert.isEmpty(patch_data.statuses);
            ArrayAssert.isEmpty(patch_data.information_types);
        }

    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription: add subcription workflow',

        _should: {error: {}},

        setUp: function() {
            var TestBugFilter = function() {};
            TestBugFilter.prototype = {
                get: function (name) {
                    return 'DESCRIPTION';
                },
                getAttrs: function () {
                    return {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion'
                    };
                }
            };
            // We need an lp_client that will appear to succesfully create the
            // bug filter.
            var TestClient = function() {};
            TestClient.prototype = {
                named_post: function (uri, operation_name, config) {
                    config.on.success(new TestBugFilter());
                    this.post_called = true;
                },
                patch: function(uri, representation, config, headers) {
                    config.on.success(new TestBugFilter());
                    this.patch_called = true;
                },
                post_called: false,
                patch_called: false
            };

            this.original_lp = monkeypatch_LP();

            this.configuration = {
                content_box: content_box_id,
                lp_client: new TestClient()
            };
            this.content_node = create_test_node();
            Y.one('body').appendChild(this.content_node);
        },

        tearDown: function() {
            window.LP = this.original_lp;
            remove_test_node();
            Y.one('#request-notifications').empty();
            delete this.content_node;
        },

        test_simple_add_workflow: function() {
            // Clicking on the "Subscribe to bug mail" link and then clicking
            // on the overlay form's "OK" button results in a filter being
            // created and PATCHed.
            module.setup(this.configuration);
            Y.one('a.menu-link-subscribe_to_bug_mail').simulate('click');
            Assert.isFalse(module.lp_client.post_called);
            Assert.isFalse(module.lp_client.patch_called);
            var button = Y.one('.yui3-lazr-formoverlay-actions button');
            Assert.areEqual('Create', button.get('text'));
            button.simulate('click');
            Assert.isTrue(module.lp_client.post_called);
            Assert.isTrue(module.lp_client.patch_called);
        },

        test_simple_add_workflow_canceled: function() {
            // Clicking on the "Subscribe to bug mail" link and then clicking
            // on the overlay form's cancel button results in no filter being
            // created or PATCHed.
            module.setup(this.configuration);
            Y.one('a.menu-link-subscribe_to_bug_mail').simulate('click');
            Assert.isFalse(module.lp_client.post_called);
            Assert.isFalse(module.lp_client.patch_called);
            var button = Y.one(
                '.yui3-lazr-formoverlay-actions button+button');
            Assert.areEqual(button.get('text'), 'Cancel');
            button.simulate('click');
            Assert.isFalse(module.lp_client.post_called);
            Assert.isFalse(module.lp_client.patch_called);
        }

    }));

    tests.suite.add(new Y.Test.Case({
        // The make_add_subscription_success_handler function constructs a
        // function that gives a visual feedback after adding a subscription.

        name:
            'Structural Subscription: make_add_subscription_success_handler',

        _should: {error: {}},

        setUp: function() {
            this.TestBugFilter = function() {};
            this.TestBugFilter.prototype = {
                get: function (name) {
                    return 'DESCRIPTION';
                },
                getAttrs: function () {
                    return {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion'
                    };
                }
            };
        },

        tearDown: function() {
            window.LP = this.original_lp;
            remove_test_node();
            Y.one('#request-notifications').empty();
            delete this.content_node;
        },

        test_description_is_added: function() {
            // If we add a subscription on a page that doesn't display
            // subcription details then we need to add an "informational
            // message" describing the just-added subscription.
            var handler;
            var config = {add_filter_description: false};
            handler = module._make_add_subscription_success_handler(config);
            var form_data = {};
            handler(form_data, new this.TestBugFilter());
            var text = Y.one('#request-notifications').get('text');
            Assert.isTrue(text.indexOf('DESCRIPTION') !== -1);
        }

    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription: edit subcription workflow',

        _should: {error: {}},

        setUp: function() {
            var TestBugFilter = function(data) {
                if (data !== undefined) {
                    this._data = data;
                } else {
                    this._data = {};
                }
            };
            TestBugFilter.prototype = {
                'getAttrs': function () {
                    return this._data;
                }
            };
            // We need an lp_client that will appear to succesfully create the
            // bug filter.
            var TestClient = function() {
                this.post_called = false;
                this.patch_called = false;
            };
            TestClient.prototype = {
                named_post: function (uri, operation_name, config) {
                    config.on.success(new TestBugFilter());
                    this.post_called = true;
                },
                patch: function(uri, representation, config, headers) {
                    config.on.success(new TestBugFilter(representation));
                    this.patch_called = true;
                }
            };

            this.original_lp = monkeypatch_LP();

            LP.cache.subscription_info = [{
                target_url: 'http://example.com',
                target_title:'Example project',
                filters: [{
                    filter: {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: true,
                    is_muted: false,
                    subscriber_is_team: false,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick',
                    user_is_team_admin: false
                }]
            }];


            this.configuration = {
                content_box: content_box_id,
                lp_client: new TestClient()
            };
            this.content_node = create_test_node();
            Y.one('body').appendChild(this.content_node);
        },

        tearDown: function() {
            window.LP = this.original_lp;
            remove_test_node();
            Y.one('#request-notifications').empty();
            delete this.content_node;
        },

        test_simple_edit_workflow: function() {
            module.setup_bug_subscriptions(this.configuration);

            // Editing a value via the edit link and dialog causes the
            // subscription list to reflect the new value.
            var label = Y.one('.filter-name span').get('text');
            Assert.isTrue(label.indexOf('DESCRIPTION') !== -1);

            // No PATCHing has happened yet.
            Assert.isFalse(module.lp_client.patch_called);

            // Click the edit link.
            Y.one('a.edit-subscription').simulate('click');

            // Set a new name (description) and click OK.
            Y.one('input[name="name"]').set('value', 'NEW VALUE');
            var button = Y.one('.yui3-lazr-formoverlay-actions button');
            Assert.areEqual('Save', button.get('text'));
            button.simulate('click');

            // Clicking OK resulted in the bug filter being PATCHed.
            Assert.isTrue(module.lp_client.patch_called);
            // And the new value is reflected in the subscription listing.
            label = Y.one('.filter-name span').get('text');
            Assert.isTrue(label.indexOf('NEW VALUE') !== -1);
        },

        test_title: function() {
            // Make sure that the overlay title is set correctly for editing.
            module.setup_bug_subscriptions(this.configuration);
            // Click the edit link.
            Y.one('a.edit-subscription').simulate('click');
            var overlays = Y.all('.yui3-lazr-formoverlay');
            // There is only one overlay in the DOM.
            Assert.areEqual(overlays.size(), 1);
            // The title is what we expect.
            var title = overlays.item(0).one('#subscription-overlay-title');
            Assert.areEqual(
                title.get('text'),
                'Edit subscription for Example project bugs');
            // Now we cancel, so we can try rendering again.
            Y.one('button[name="field.actions.cancel"]').simulate('click');
            // If we do it again, everything is the same (see bug 771232).
            Y.one('a.edit-subscription').simulate('click');
            overlays = Y.all('.yui3-lazr-formoverlay');
            // There is still only one overlay in the DOM.
            Assert.areEqual(overlays.size(), 1);
            // The title is still what we expect.
            title = overlays.item(0).one('#subscription-overlay-title');
            Assert.areEqual(
                title.get('text'),
                'Edit subscription for Example project bugs');
        }

    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription: unsubscribing',

        _should: {error: {}},

        setUp: function() {
            var TestClient = function() {};
            this.original_lp = monkeypatch_LP();

            LP.cache.subscription_info = [{
                target_url: 'http://example.com',
                target_title:'Example project',
                filters: [{
                    filter: {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: true,
                    is_muted: false,
                    subscriber_is_team: false,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick',
                    user_is_team_admin: false
                }]
            }];

            this.configuration = {
                content_box: content_box_id,
                lp_client: new TestClient()
            };
            this.content_node = create_test_node();
            Y.one('body').appendChild(this.content_node);
        },

        tearDown: function() {
            window.LP = this.original_lp;
            remove_test_node();
            Y.one('#request-notifications').empty();
            delete this.content_node;
        },

        test_simple_unsubscribe: function() {
            // Clicking on the unsubscribe link will result in a DELETE being
            // sent and the filter description being removed.

            var DELETE_performed = false;
            // Fake a DELETE that succeeds.
            module._Y_io_hook = function (link, config) {
                DELETE_performed = true;
                config.on.success();
            };

            module.setup_bug_subscriptions(this.configuration);
            Y.one('a.delete-subscription').simulate('click');
            Assert.isTrue(DELETE_performed);
        },

        test_unsubscribe_spinner: function () {
            // The delete link shows a spinner while a deletion is requested.
            // if the deletion fails, the spinner is removed.
            var resume;
            module._Y_io_hook = function (link, config) {
                resume = function () {
                    config.on.failure(true, true);
                };
            };

            module.setup_bug_subscriptions(this.configuration);
            var delete_link = Y.one('a.delete-subscription');
            delete_link.simulate('click');
            Assert.isTrue(delete_link.hasClass('spinner'));
            Assert.isFalse(delete_link.hasClass('remove'));
            resume();
            Assert.isTrue(delete_link.hasClass('remove'));
            Assert.isFalse(delete_link.hasClass('spinner'));
        }

    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Add a subscription from +subscriptions page',

        setUp: function() {
            this.config = {
                content_box: content_box_id
            };
            this.content_box = create_test_node();
            Y.one('body').appendChild(this.content_box);
            this.original_lp = monkeypatch_LP();
        },

        tearDown: function() {
            window.LP = this.original_lp;
            remove_test_node();
            Y.one('#request-notifications').empty();
            delete this.content_box;
        },

        // Setting up a subscription link with no link in the DOM should fail.
        test_setup_subscription_link_none: function() {
            var logged_missing_link = false;
            Y.on('yui:log', function(e){
                if (e.msg === "No structural subscription link found."){
                    logged_missing_link = true;
                }
            });
            module.setup_subscription_link(this.config, "#link");
            Y.Assert.isTrue(
                logged_missing_link, "Missing link not reported.");
        },

        // Setting up a subscription link should unset the 'hidden',
        // and set 'visible' and 'js-action' CSS classes on the node.
        test_setup_subscription_link_classes: function() {
            var link = this.content_box.appendChild(
                Y.Node.create('<a>Link</a>'));
            link.set('id', 'link');
            link.addClass('hidden');
            module.setup_subscription_link(this.config, "#link");
            Assert.isFalse(link.hasClass('hidden'));
            Assert.isTrue(link.hasClass('visible'));
            Assert.isTrue(link.hasClass('js-action'));
        },

        // Setting up a subscription link creates an on-click handler
        // that calls up show_add_overlay with the passed in configuration.
        test_setup_subscription_link_behaviour: function() {
            var link = this.content_box.appendChild(
                Y.Node.create('<a>Link</a>'));
            link.set('id', 'link');

            // Track if the method was called.
            var called_method = false;

            // Keep the old module's _show_add_overlay, so we can override.
            old_show_add_overlay = module._show_add_overlay;
            var test = this;
            module._show_add_overlay = function(config) {
                module._show_add_overlay = old_show_add_overlay;
                Assert.areEqual(test.config, config);
                called_method = true;
            };
            module.setup_subscription_link(this.config, "#link");
            link.simulate('click');

            this.wait(function() {
                Assert.isTrue(called_method);
            }, 10);
        },

        // Success handler for adding a subscription creates
        // a subscription listing if there's none and adds a filter to it.
        test_make_add_subscription_success_handler_empty_list: function() {
            this.config.add_filter_description = true;
            var success_handler =
                module._make_add_subscription_success_handler(this.config);
            var subs_list = this.content_box.appendChild(
                Y.Node.create('<div id="structural-subscriptions"></div>'));

            var form_data = {
                recipient: ["user"]
            };
            var target_info = {
                title: "MY TARGET",
                url: "http://target/" };
            window.LP.cache.target_info = target_info;
            var filter = {
                get: function (name) {
                    return 'DESCRIPTION';
                },
                getAttrs: function() {
                    return {
                        importances: [],
                        statuses: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        description: 'Filter name'
                    };
                }};

            success_handler(form_data, filter);
            // No sub-nodes have been created in the subs_list node.
            Assert.areEqual(
                1, subs_list.all('div.subscription-filter').size());
            var target_node = subs_list.one('#subscription-0>span>span');
            Assert.areEqual(
                'Subscriptions to MY TARGET',
                subs_list.one('#subscription-0>span>span').get('text'));
            var filter_node = subs_list.one('#subscription-filter-0');
            Assert.areEqual(
                'Your subscription: "Filter name"',
                filter_node.one('.filter-name').get('text'));
            this.config.add_filter_description = false;
            delete window.LP.cache.target_info;
        },

        // Success handler for adding a subscription adds a filter
        // to the subscription listing which already has filters listed.
        test_make_add_subscription_success_handler_with_filters: function() {
            this.config.add_filter_description = true;
            var success_handler =
                module._make_add_subscription_success_handler(this.config);
            var subs_list = this.content_box.appendChild(
                Y.Node.create('<div id="structural-subscriptions"></div>'));
            subs_list.appendChild('<div id="subscription-0"></div>')
                .appendChild('<div id="subscription-filter-0"'+
                             '     class="subscription-filter"></div>');
            var form_data = {
                recipient: ["user"]
            };
            var target_info = {
                title: "Subscription target",
                url: "http://target/" };
            window.LP.cache.subscription_info = [{
                target_url: 'http://example.com',
                target_title:'Example project',
                filters: [{
                    filter: {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: true,
                    is_muted: false,
                    subscriber_is_team: false,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick',
                    user_is_team_admin: false
                }]
            }];
            window.LP.cache.target_info = target_info;
            var filter = {
                getAttrs: function() {
                    return {
                        importances: [],
                        statuses: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        description: 'Filter name'
                    };
                }};

            success_handler(form_data, filter);
            // No sub-nodes have been created in the subs_list node.
            Assert.areEqual(
                2, subs_list.all('div.subscription-filter').size());
            this.config.add_filter_description = false;
            delete window.LP.cache.target_info;
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription mute team subscriptions',

        // Verify that the mute controls and labels on the edit block
        // render and interact properly

        _should: {
            error: {
                }
            },

        setUp: function() {
            // Monkeypatch LP to avoid network traffic and to allow
            // insertion of test data.
            this.original_lp = monkeypatch_LP();
            this.test_node = create_test_node(true);
            Y.one('body').appendChild(this.test_node);
            this.lp_client = make_lp_client_stub();
            LP.cache.subscription_info = [
                {target_url: 'http://example.com',
                 target_title:'Example project',
                 filters: [
                    {filter: {
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: true,
                    is_muted: false,
                    subscriber_is_team: true,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick',
                    user_is_team_admin: false
                    }
                    ]
                }
                ];
        },

        tearDown: function() {
            remove_test_node();
            window.LP = this.original_lp;
        },

        test_not_muted_rendering: function() {
            // Verify that an unmuted subscription is rendered correctly.
            module.setup_bug_subscriptions(
                {content_box: content_box_id,
                 lp_client: this.lp_client});
            var filter_node = Y.one('#subscription-filter-0');
            Assert.isNotNull(filter_node);
            var mute_label_node = filter_node.one('.mute-label');
            Assert.isNotNull(mute_label_node);
            Assert.areEqual(mute_label_node.getStyle('display'), 'none');
            var mute_link = filter_node.one('a.mute-subscription');
            Assert.isNotNull(mute_link);
            Assert.isTrue(mute_link.hasClass('mute'));
        },

        test_muted_rendering: function() {
            // Verify that a muted subscription is rendered correctly.
            LP.cache.subscription_info[0].filters[0].is_muted = true;
            module.setup_bug_subscriptions(
                {content_box: content_box_id,
                 lp_client: this.lp_client});
            var filter_node = Y.one('#subscription-filter-0');
            Assert.isNotNull(filter_node);
            var mute_label_node = filter_node.one('.mute-label');
            Assert.isNotNull(mute_label_node);
            Assert.areEqual(mute_label_node.getStyle('display'), 'inline');
            var mute_link = filter_node.one('a.mute-subscription');
            Assert.isNotNull(mute_link);
            Assert.isTrue(mute_link.hasClass('unmute'));
        },

        test_not_muted_toggle_muted: function() {
            // Verify that an unmuted subscription can be muted.
            module.setup_bug_subscriptions(
                {content_box: content_box_id,
                 lp_client: this.lp_client});
            var filter_node = Y.one('#subscription-filter-0');
            var mute_label_node = filter_node.one('.mute-label');
            var mute_link = filter_node.one('a.mute-subscription');
            this.lp_client.named_post.args = [];
            mute_link.simulate('click');
            Assert.areEqual(this.lp_client.received[0][0], 'named_post');
            Assert.areEqual(
                this.lp_client.received[0][1][0],
                'http://example.com/a_filter');
            Assert.areEqual(
                this.lp_client.received[0][1][1], 'mute');
            Assert.areEqual(mute_label_node.getStyle('display'), 'inline');
            Assert.isTrue(mute_link.hasClass('unmute'));
        },

        test_muted_toggle_not_muted: function() {
            // Verify that an muted subscription can be unmuted.
            LP.cache.subscription_info[0].filters[0].is_muted = true;
            module.setup_bug_subscriptions(
                {content_box: content_box_id,
                 lp_client: this.lp_client});
            var filter_node = Y.one('#subscription-filter-0');
            var mute_label_node = filter_node.one('.mute-label');
            var mute_link = filter_node.one('a.mute-subscription');
            this.lp_client.named_post.args = [];
            mute_link.simulate('click');
            Assert.areEqual(this.lp_client.received[0][0], 'named_post');
            Assert.areEqual(
                this.lp_client.received[0][1][0],
                'http://example.com/a_filter');
            Assert.areEqual(
                this.lp_client.received[0][1][1], 'unmute');
            Assert.areEqual(mute_label_node.getStyle('display'), 'none');
            Assert.isTrue(mute_link.hasClass('mute'));
        },

        test_mute_spinner: function () {
            // The mute link shows a spinner while a mute is requested.
            // When the mute succeeds, the spinner is removed.
            module.setup_bug_subscriptions(
                {content_box: content_box_id,
                 lp_client: this.lp_client});
            var filter_node = Y.one('#subscription-filter-0');
            var mute_link = filter_node.one('a.mute-subscription');
            this.lp_client.named_post.args = [];
            this.lp_client.named_post.halt = true;
            mute_link.simulate('click');
            Assert.isTrue(mute_link.hasClass('spinner'));
            Assert.isFalse(mute_link.hasClass('mute'));
            this.lp_client.named_post.resume();
            Assert.isTrue(mute_link.hasClass('unmute'));
            Assert.isFalse(mute_link.hasClass('spinner'));
        },

        test_mute_spinner_fail: function () {
            // The mute link shows a spinner while a mute is requested.
            // If the mute fails, the spinner is removed.
            module.setup_bug_subscriptions(
                {content_box: content_box_id,
                 lp_client: this.lp_client});
            var filter_node = Y.one('#subscription-filter-0');
            var mute_link = filter_node.one('a.mute-subscription');
            this.lp_client.named_post.fail = true;
            this.lp_client.named_post.args = [true, true];
            this.lp_client.named_post.halt = true;
            mute_link.simulate('click');
            Assert.isTrue(mute_link.hasClass('spinner'));
            Assert.isFalse(mute_link.hasClass('mute'));
            this.lp_client.named_post.resume();
            Assert.isTrue(mute_link.hasClass('mute'));
            Assert.isFalse(mute_link.hasClass('spinner'));
        }

    }));

    tests.suite.add(new Y.Test.Case({
        name: 'Structural Subscription: enable/disable help link',

        _should: {error: {}},

        setUp: function() {
            this.original_lp = monkeypatch_LP();

            LP.cache.subscription_info = [{
                target_url: 'http://example.com',
                target_title:'Example project',
                filters: [{
                    filter: {
                        description: 'DESCRIPTION',
                        statuses: [],
                        importances: [],
                        information_types: [],
                        tags: [],
                        find_all_tags: true,
                        bug_notification_level: 'Discussion',
                        self_link: 'http://example.com/a_filter'
                        },
                    can_mute: true,
                    is_muted: false,
                    subscriber_is_team: true,
                    subscriber_url: 'http://example.com/subscriber',
                    subscriber_title: 'Thidwick',
                    user_is_team_admin: false
                }]
            }];


            this.configuration = {
                content_box: content_box_id,
                lp_client: make_lp_client_stub()
            };
            this.content_node = create_test_node(true);
            Y.one('body').appendChild(this.content_node);
        },

        tearDown: function() {
            window.LP = this.original_lp;
            remove_test_node();
            Y.one('#request-notifications').empty();
            delete this.content_node;
        },

        test_help_link_hover: function() {
            module.setup_bug_subscriptions(this.configuration);

            // Initially the help link is not visible.
            var help = Y.one('a.mute-help');
            Assert.isFalse(help.getStyle('visibility') === 'visible');

            // If we hover over the enable/disable (mute) link the help link
            // becomes visible.
            Y.one('a.mute-subscription').simulate('mouseover');
            Assert.areEqual('visible', help.getStyle('visibility'));
        }

    }));

}, '0.1', {
    requires: ['lp.testing.runner', 'lp.testing.helpers', 'test',
               'test-console', 'node', 'node-event-simulate', 'lp.ui.effects',
               'lp.client', 'lp.registry.structural_subscription']
});
