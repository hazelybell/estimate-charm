/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.picker.test', function (Y) {
    var tests = Y.namespace('lp.picker.test');
    tests.suite = new Y.Test.Suite('picker Tests');

    // Local aliases
    var Assert = Y.Assert,
        ArrayAssert = Y.ArrayAssert;

    /*
     * A wrapper for the Y.Event.simulate() function.  The wrapper accepts
     * CSS selectors and Node instances instead of raw nodes.
     */
    function simulate(widget, selector, evtype, options) {
        var rawnode = Y.Node.getDOMNode(widget.one(selector));
        Y.Event.simulate(rawnode, evtype, options);
    }

    /* Helper function to clean up a dynamically added widget instance. */
    function cleanup_widget(widget) {
        // Nuke the boundingBox, but only if we've touched the DOM.
        if (widget.get('rendered')) {
            var bb = widget.get('boundingBox');
            bb.get('parentNode').removeChild(bb);
        }
        // Kill the widget itself.
        widget.destroy();
    }

    tests.suite.add(new Y.Test.Case({
        name: 'picker_tests',

        setUp: function() {
            this.picker = new Y.lp.ui.picker.Picker({
                "selected_value": 'foo',
                "selected_value_metadata": 'foobar'
            });
        },

        tearDown: function() {
            cleanup_widget(this.picker);
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.ui.picker,
                "Could not locate the lp.ui.picker-base module");
        },

        test_picker_can_be_instantiated: function() {
            Assert.isInstanceOf(
                Y.lp.ui.picker.Picker, this.picker,
                "Picker failed to be instantiated");
        },

        test_picker_initialisation: function() {
            Assert.areEqual('foo', this.picker.get('selected_value'));
            Assert.areEqual('foobar',
                this.picker.get('selected_value_metadata'));
        },

        test_picker_is_stackable: function() {
            // We should probably define an Assert.hasExtension.
            Assert.areSame(
                Y.WidgetStack.prototype.sizeShim, this.picker.sizeShim,
                "Picker should be stackable.");
            Assert.areSame(
                Y.WidgetPositionAlign.prototype.align, this.picker.align,
                "Picker should be positionable.");
        },

        test_picker_has_elements: function () {
            /**
             * Test that renderUI() adds search box, an error container and a
             * results container to the widget.
             * */
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            Assert.isNotNull(
                bb.one('.yui3-picker-search'),
                "Missing search box.");
            Assert.isNotNull(
                bb.one('.lazr-search.lazr-btn'),
                "Missing search button.");
            Assert.isNotNull(
                bb.one('.yui3-picker-results'),
                "Missing search results.");
            Assert.isNotNull(
                bb.one('.yui3-picker-error'), "Missing error box.");
        },

        test_set_results_updates_display: function () {
            this.picker.render();
            var image_url = '../../ui/assets/skins/sam/search.png';
            this.picker.set('results', [
                {
                    image: image_url,
                    css: 'yui3-blah-blue',
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com'
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var li = bb.one('.yui3-picker-results li');
            Assert.isNotNull(li, "Results not found");
            Assert.isTrue(li.hasClass('yui3-blah-blue'), "Missing class name.");
            Assert.isNotNull(li.one('img'), "Missing image.");
            Assert.areEqual(
                image_url, li.one('img').getAttribute('src'),
                "Unexpected image url");
            var title_el = li.one('.yui3-picker-result-title');
            Assert.isNotNull(title_el, "Missing title element");
            Assert.areEqual(
                'Joe Schmo', title_el.get('text'), 'Unexpected title value.');
            var description_el = li.one('.yui3-picker-result-description');
            Assert.isNotNull(description_el, "Missing description element.");
            Assert.areEqual(
                'joe@example.com', description_el.get('text'),
                'Unexpected description value.');
        },

        test_alternate_title_text: function () {
            this.picker.render();
            this.picker.set('results', [
                {
                    css: 'yui3-blah-blue',
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com',
                    alt_title: 'Another Joe'
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var li = bb.one('.yui3-picker-results li');
            var title_el = li.one('.yui3-picker-result-title');
            Assert.isNotNull(title_el, "Missing title element");
            Assert.areEqual('A', title_el.get('tagName'), 'Tab key is broken.');
            Assert.isTrue(title_el.hasClass('js-action'));
            Assert.areEqual(
                'Joe Schmo\u00a0(Another Joe)', title_el.get('text'),
                'Unexpected title value.');
        },

        test_title_links: function () {
            this.picker.render();
            this.picker.set('results', [
                {
                    css: 'yui3-blah-blue',
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com',
                    alt_title: 'Joe Again <foo></foo>',
                    title_link: 'http://somewhere.com',
                    alt_title_link: 'http://somewhereelse.com',
                    link_css: 'cool-style',
                    details: ['Member since 2007']
                }
            ]);

            function check_link(picker, link_selector, title, href) {
                var bb = picker.get('boundingBox');
                var link_clicked = false;
                var link_node = bb.one(link_selector);

                Assert.areEqual(title, link_node.get('text'));
                Assert.areEqual(href, link_node.get('href'));

                Y.on('click', function(e) {
                    link_clicked = true;
                }, link_node);
                simulate(bb, link_selector, 'click');
                Assert.isTrue(link_clicked,
                    link_selector + ' link was not clicked');
            }
            check_link(
                this.picker, 'a.cool-style:nth-child(1)', 'Joe Schmo',
                'http://somewhere.com/');
            check_link(
                this.picker, 'a.cool-style:last-child', 'View details',
                'http://somewhereelse.com/');
            var alt_text_node = this.picker.get('boundingBox')
                .one('.yui3-picker-result-title span');
            Assert.areEqual('Joe Again <foo></foo>', alt_text_node.get('text'));
        },

        test_details: function () {
            // The details of the li is the content node of the expander.
            this.picker.render();
            this.picker.set('results', [
                {
                    css: 'yui3-blah-blue',
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com',
                    details: ['joe on irc.freenode.net', 'Member since 2007'],
                    alt_title_link: '/~jschmo'
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var li = bb.one('.yui3-picker-results li');
            var expander_action = li.expander.icon_node.get('firstChild');
            Assert.areEqual(
                'A', expander_action.get('tagName'), 'Tab key is broken.');
            var details = li.expander.content_node;
            Assert.areEqual(
                'joe on irc.freenode.net<br>Member since 2007',
                details.one('div').getContent());
            Assert.areEqual(
                'Select Joe Schmo',
                details.one('ul li:first-child').get('text'));
            Assert.areEqual(
                'View details', details.one('ul li:last-child').get('text'));
        },

        test_details_escaping: function () {
            // The content of details is escaped.
            this.picker.render();
            this.picker.set('results', [
                {
                    css: 'yui3-blah-blue',
                    value: 'jschmo',
                    title: 'Joe <Schmo>',
                    description: 'joe@example.com',
                    details: ['<joe> on irc.freenode.net',
                        'f<nor>d maintainer'],
                    alt_title_link: '/~jschmo'
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var li = bb.one('.yui3-picker-results li');
            var details = li.expander.content_node;
            Assert.areEqual(
                '&lt;joe&gt; on irc.freenode.net<br>f&lt;nor&gt;d maintainer',
                details.one('div').getContent());
            Assert.areEqual(
                'Select Joe &lt;Schmo&gt;',
                details.one('ul li:first-child a').getContent('text'));
        },

        test_expander_only_one_open: function() {
            // Only one expanded details entry should be open at any time.
            this.picker.render();
            this.picker.set('results', [
                {
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    details: ['detail 1', 'detail 2']
                },
                {
                    value: 'jsmith',
                    title: 'Joe Smith',
                    details: ['detail 1', 'detail 2']
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var first_entry = bb.one('.yui3-picker-results li');
            var first_expander = first_entry.expander;
            var second_entry = bb.one('.yui3-picker-results li.yui3-lazr-odd');
            var second_expander = second_entry.expander;
            first_expander.icon_node.simulate('click');
            Y.Assert.isTrue(first_expander.isExpanded());
            Y.Assert.isFalse(second_expander.isExpanded());

            // Open the other expander and check that the first one has closed.
            second_expander.icon_node.simulate('click');
            Y.Assert.isFalse(first_expander.isExpanded());
            Y.Assert.isTrue(second_expander.isExpanded());
        },

        test_expander_multiple_pickers: function() {
            // Expanders for one picker should not interfere with those for
            // another picker. ie if Picker A expander is opened, any open
            // expanders on Picker B should remain open.
            var results = [
                {
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    details: ['detail 1', 'detail 2']
                },
                {
                    value: 'jsmith',
                    title: 'Joe Smith',
                    details: ['detail 1', 'detail 2']
                }
            ];
            this.picker.render();
            this.picker.set('results', results);

            var another_picker = new Y.lp.ui.picker.Picker();
            another_picker.render();
            another_picker.set('results', results);

            var bb = this.picker.get('boundingBox');
            var picker_entry = bb.one('.yui3-picker-results li');
            var picker_expander = picker_entry.expander;
            picker_expander.icon_node.simulate('click');

            bb = another_picker.get('boundingBox');
            var another_picker_entry = bb.one('.yui3-picker-results li');
            var another_picker_expander = another_picker_entry.expander;
            another_picker_expander.icon_node.simulate('click');

            Y.Assert.isTrue(picker_expander.isExpanded());
            Y.Assert.isTrue(another_picker_expander.isExpanded());
            cleanup_widget(another_picker);
        },

        test_details_save_link: function () {
            // The select link the li's details saves the selection.
            this.picker.render();
            this.picker.set('results', [
                {
                    css: 'yui3-blah-blue',
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com',
                    alt_title_link: 'http://somewhereelse.com',
                    link_css: 'cool-style',
                    details: ['Member since 2007']
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var link_node = bb.one('a.save');
            Assert.areEqual('Select Joe Schmo', link_node.get('text'));
            Assert.isTrue(link_node.get('href').indexOf(window.location) === 0);
            var selected_value = null;
            this.picker.subscribe('save', function(e) {
                selected_value = e.details[0].value;
            }, this);
            simulate(bb, 'a.save', 'click');
            Assert.areEqual('jschmo', selected_value);
        },

        test_title_badges: function () {
            this.picker.render();
            var badge_info = [
                {
                    url: '../../ui/assets/skins/sam/search.png',
                    label: 'product 1',
                    role: 'driver'},
                {   url: '../../ui/assets/skins/sam/spinner.png',
                    label: 'product 2',
                    role: 'maintainer'},
                {   url: '../../ui/assets/skins/sam/spinner.png',
                    label: 'product 2',
                    role: 'driver'
                }];
            this.picker.set('results', [
                {
                    badges: badge_info,
                    css: 'yui3-blah-blue',
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com'
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var li = bb.one('.yui3-picker-results li');
            var i;
            for (i=0; i<badge_info.length; i++) {
                var img_node = li.one(
                    'div.badge img.badge:nth-child(' + (i + 1) + ')');
                // Check that duplicate badge urls are not displayed.
                if (i===2) {
                    Assert.isNull(img_node);
                    break;
                }
                Assert.areEqual(
                    badge_info[i].url, img_node.getAttribute('src'),
                    'Unexpected badge url');
                var badge_text = badge_info[i].label + ' ' + badge_info[i].role;
                Assert.areEqual(
                    badge_text, img_node.get('alt'),
                    'Unexpected badge alt text');
            }
        },

        test_details_badges: function () {
            // The affiliation details are rendered correctly in the content
            // node of the expander.
            this.picker.render();
            var badge_info = [
                {
                    url: '../../ui/assets/skins/sam/spinner.png',
                    label: 'product 1',
                    role: 'maintainer'},
                {
                    url: '../../ui/assets/skins/sam/search.png',
                    label: 'product 2',
                    role: 'driver'}];
            this.picker.set('results', [
                {
                    badges: badge_info,
                    css: 'yui3-blah-blue',
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com'
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var li = bb.one('.yui3-picker-results li');
            var details = li.expander.content_node;
            var affiliation_header =
                details.one('div.affiliation:nth-child(1)');
            Assert.areEqual('Affiliation', affiliation_header.get('text'));
            var badge_img = affiliation_header.one('img');
            Assert.areEqual('product 1 maintainer', badge_img.get('alt'));
            Assert.areEqual(
                '../../ui/assets/skins/sam/spinner.png',
                badge_img.getAttribute('src'));
            affiliation_header = details.one('div.affiliation:nth-child(3)');
            badge_img = affiliation_header.one('img');
            Assert.areEqual('product 2 driver', badge_img.get('alt'));
            Assert.areEqual(
                '../../ui/assets/skins/sam/search.png',
                badge_img.getAttribute('src'));
            var affiliation_text = details.one(
                'div.affiliation-text:nth-child(2)');
            Assert.areEqual(
                'product 1 maintainer', affiliation_text.get('innerHTML'));
            affiliation_text = details.one('div.affiliation-text:nth-child(4)');
            Assert.areEqual(
                'product 2 driver', affiliation_text.get('innerHTML'));
        },

        test_results_display_escaped: function () {
            this.picker.render();
            this.picker.set('results', [
                {
                    image: '<script>throw "back";</script>',
                    css: 'yui3-blah-blue',
                    value: '<script>throw "wobbly";</script>',
                    title: '<script>throw "toys out of pram";</script>',
                    description: '<script>throw "up";</script>'
                }
            ]);
            var bb = this.picker.get('boundingBox');
            var li = bb.one('.yui3-picker-results li');
            var image_el = li.one('img');
            Assert.areEqual(
                '<script>throw "back";</script>', image_el.getAttribute('src'),
                "Unexpected image url");
            var title_el = li.one('.yui3-picker-result-title');
            Assert.areEqual(
                '&lt;script&gt;throw "toys out of pram";&lt;/script&gt;',
                title_el.get('innerHTML'), 'Unexpected title value.');
            var description_el = li.one('.yui3-picker-result-description');
            Assert.areEqual(
                '&lt;script&gt;throw "up";&lt;/script&gt;',
                description_el.get('innerHTML'),
                'Unexpected description value.');
        },

        test_results_updates_display_with_missing_data: function () {
            this.picker.render();
            var image_url = '../../ui/assets/skins/sam/search.png';
            this.picker.set('results', [
                { value: 'jschmo', title: 'Joe Schmo' }
            ]);
            var bb = this.picker.get('boundingBox');
            var li = bb.one('.yui3-picker-results li');
            Assert.isNotNull(li, "Results not found.");
            Assert.areEqual(Y.lp.ui.CSS_EVEN, li.getAttribute('class'));
            Assert.isNull(li.one('img'), "Unexpected image.");
            var description_el = li.one('.yui3-picker-result-description.');
            Assert.isNull(description_el, "Unexpected description element.");
        },

        test_render_displays_initial_results: function () {
            this.picker.set('results', [
                    {'title': 'Title 1'},
                    {'title': 'Title 2'}
                ]);
            this.picker.render();
            var bb = this.picker.get('boundingBox');
            var results = bb.all('.yui3-picker-results li');
            Assert.isNotNull(results, "Results not found.");
            Assert.areEqual(2, results.size());
        },

        test_resetting_results_removes_previous_results: function () {
            this.picker.render();
            var bb = this.picker.get('boundingBox');

            // First time setting the results.
            this.picker.set('results', [
                    {'title': 'Title 1'},
                    {'title': 'Title 2'}
                ]);
            var results = bb.all('.yui3-picker-results li');
            Assert.isNotNull(results, "Results not found.");
            Assert.areEqual(2, results.size());

            // Second time setting the results.
            this.picker.set('results', [
                    {'title': 'Title 1'}
                ]);
            results = bb.all('.yui3-picker-results li');
            Assert.isNotNull(results, "Results not found");
            Assert.areEqual(1, results.size());
        },

        test_updateResultsDisplay_adds_even_odd_class: function () {
            this.picker.set('results', [
                    {'title': 'Title 1'},
                    {'title': 'Title 2'},
                    {'title': 'Title 1'},
                    {'title': 'Title 2'}
                ]);
            this.picker.render();
            var bb = this.picker.get('boundingBox');
            var results = bb.all('.yui3-picker-results li');
            Assert.isNotNull(results, "Results not found.");
            ArrayAssert.itemsAreEqual(
                [true, false, true, false],
                results.hasClass(Y.lp.ui.CSS_EVEN));
            ArrayAssert.itemsAreEqual(
                [false, true, false, true],
                results.hasClass(Y.lp.ui.CSS_ODD));
        },

        test_clicking_search_button_fires_search_event: function () {
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            var input = bb.one('.yui3-picker-search');
            input.set('value', 'a search');
            var event_has_fired = false;
            this.picker.subscribe('search', function(e) {
                    event_has_fired = true;
                    Assert.areEqual(
                        'a search', e.details[0],
                        'Search event is missing the search string.');
            }, this);
            simulate(
                this.picker.get('boundingBox'),
                '.lazr-search.lazr-btn',
                'click');
            Assert.isTrue(event_has_fired, "search event wasn't fired");
        },

        test_set_search_mode_disables_search_button: function () {
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            this.picker.set('search_mode', true);
            Assert.isTrue(
                bb.one('.lazr-search.lazr-btn').get('disabled'),
                "Search button wasn't disabled.");
            this.picker.set('search_mode', false);
            Assert.isFalse(
                bb.one('.lazr-search.lazr-btn').get('disabled'),
                "Search button wasn't re-enabled.");
        },

        test_hitting_enter_in_search_input_fires_search_event: function () {
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            var input = bb.one('.yui3-picker-search');
            input.set('value', 'a search');
            var event_has_fired = false;
            this.picker.subscribe('search', function() {
                event_has_fired = true;
            }, this);
            simulate(
                this.picker.get('boundingBox'),
                '.yui3-picker-search',
                'keydown',
                {keyCode: 13});
            Assert.isTrue(event_has_fired, "search event wasn't fired");
        },

        test_search_event_sets_the_in_search_mode: function () {
            this.picker.render();

            Assert.isFalse(
                this.picker.get('search_mode'),
                "Widget shouldn't be in search mode.");
            this.picker.fire('search');
            Assert.isTrue(
                this.picker.get('search_mode'),
                "Widget should be in search mode.");
        },

        test_search_event_resets_the_current_batch: function () {
            this.picker.render();
            this.picker.set('batches', [
                {value: 'batch1', name: 'Batch 1'},
                {value: 'batch2', name: 'Batch 2'}
                ]);
            this.picker.set('selected_batch', 1);
            Assert.areEqual(1, this.picker.get('selected_batch'));
            this.picker._search_input.set('value', 'bar');
            simulate(
                this.picker.get('boundingBox'),
                '.lazr-search.lazr-btn',
                'click');

            // An initial search resets the batch.
            Assert.areEqual(0, this.picker.get('selected_batch'));

            // Batch is reset if search term has changed.
            this.picker.set('search_mode', false);
            this.picker.set('selected_batch', 1);
            this.picker._search_input.set('value', 'foo');
            simulate(
                this.picker.get('boundingBox'),
                '.lazr-search.lazr-btn',
                'click');
            Assert.areEqual(0, this.picker.get('selected_batch'));

            // Batch is not reset if search term hasn't changed.
            this.picker.set('search_mode', false);
            this.picker.set('selected_batch', 1);
            simulate(
                this.picker.get('boundingBox'),
                '.lazr-search.lazr-btn',
                'click');
            Assert.areEqual(1, this.picker.get('selected_batch'));
        },

        test_setting_search_mode: function () {
            // Setting search_mode adds a CSS class and disables the search box.

            this.picker.render();

            this.picker.set('search_mode', true);
            var bb = this.picker.get('boundingBox');
            Assert.isTrue(
                bb.one('.yui3-picker-search').get('disabled'),
                "Search box should be disabled.");
            Assert.isTrue(
                bb.hasClass('yui3-picker-search-mode'),
                'Missing CSS class on widget.');
        },

        test_unsetting_search_mode: function () {

            this.picker.render();

            this.picker.set('search_mode', true);
            this.picker.set('search_mode', false);
            var bb = this.picker.get('boundingBox');
            Assert.isFalse(
                bb.one('.yui3-picker-search').get('disabled'),
                "Search input should be enabled.");
            Assert.isFalse(
                bb.hasClass('yui3-picker-search-mode'),
                'CSS class should be removed from the widget.');
        },

        test_set_results_remove_search_mode: function () {
            this.picker.render();

            this.picker.set('search_mode', true);
            this.picker.set('results', []);

            Assert.isFalse(
                this.picker.get('search_mode'),
                "Widget should be out of search_mode.");
        },

        test_set_error: function () {
            // Setting the error property displays the string in the
            // error box and puts an in-error CSS class on the widget.
            this.picker.render();

            var error_msg = 'Sorry an <error> occured.';
            this.picker.set('error', error_msg);

            var bb = this.picker.get('boundingBox');
            Assert.areEqual(
                error_msg, bb.one('.yui3-picker-error').get('text'),
                "Error message wasn't displayed.");
            Assert.isTrue(
                bb.hasClass('yui3-picker-error-mode'),
                "Missing error-mode class.");
        },

        test_set_error_null_clears_ui: function () {
            this.picker.render();

            this.picker.set('error', 'Sorry an error occured.');
            this.picker.set('error', null);
            var bb = this.picker.get('boundingBox');
            Assert.areEqual('', bb.one('.yui3-picker-error').get('text'),
                "Error message wasn't cleared.");
            Assert.isFalse(
                bb.hasClass('yui3-picker-error-mode'),
                "error-mode class should be removed.");
        },

        test_small_search_sets_error: function () {
            this.picker.render();
            this.picker.set('min_search_chars', 4);
            var bb = this.picker.get('boundingBox');
            var input = bb.one('.yui3-picker-search');
            input.set('value', ' 1 3 '); // 3 characters after trim.
            simulate(
                this.picker.get('boundingBox'),
                '.lazr-search.lazr-btn',
                'click');
            Assert.areEqual(
                "Please enter at least 4 characters.",
                this.picker.get('error'),
                "Error message wasn't displayed.");
        },

        test_click_on_result_fire_save_event: function () {
            this.picker.set('results', [
                {'title': 'Object 1', value: 'first'},
                {'title': 'Object 2', value: 'second'}
            ]);

            this.picker.render();

            var event_has_fired = false;
            this.picker.subscribe('save', function(e) {
                event_has_fired = true;
                Assert.areEqual(
                    'first', e.details[0].value,
                    "The event value of the clicked li is wrong.");
                Assert.areEqual(
                    'Object 1', e.details[0].title,
                    "The event title of the clicked li is wrong.");
            }, this);
            simulate(
                this.picker.get('boundingBox'),
                    '.yui3-picker-results li', 'click');
            Assert.isTrue(event_has_fired, "save event wasn't fired.");
        },

        test_cancel_event_hides_widget: function () {
            this.picker.render();

            this.picker.fire('cancel', 'bogus');
            Assert.isFalse(
                this.picker.get('visible'), "The widget should be hidden.");
        },

        test_cancel_event_resets_search_mode: function () {
            this.picker.render();
            this.picker.set('search_mode', true);
            Assert.isTrue(this.picker.get('search_mode'));
            this.picker.fire('cancel', 'bogus');
            Assert.isFalse(this.picker.get('search_mode'));
        },

        test_save_event_hides_widget: function () {
            this.picker.render();

            this.picker.fire('save', 'bogus');
            Assert.isFalse(
                this.picker.get('visible'), "The widget should be hidden.");
        },

        test_save_event_clears_widget_by_default: function () {
            this.picker.render();

            this.picker._search_input.set('value', 'foo');
            this.picker.fire('save', 'bogus');
            Assert.areEqual(
                '', this.picker._search_input.get('value'),
                "The widget hasn't been cleared");
        },

        test_save_does_not_clear_widget_when_clear_on_save_is_false: function () {
            picker = new Y.lp.ui.picker.Picker({clear_on_save: false});
            picker.render();

            picker._search_input.set('value', 'foo');
            picker.fire('save', 'bogus');
            Assert.areEqual(
                'foo', picker._search_input.get('value'),
                "The widget has been cleared but it should not");
        },

        test_cancel_event_does_not_clear_widget_by_default: function () {
            this.picker.render();

            this.picker._search_input.set('value', 'foo');
            this.picker.fire('cancel', 'bogus');
            Assert.areEqual(
                'foo', this.picker._search_input.get('value'),
                "The widget has been cleared but it should not");
        },

        test_cancel_event_clears_widget_when_clear_on_cancel_true: function () {
            picker = new Y.lp.ui.picker.Picker({clear_on_cancel: true});
            picker.render();

            picker._search_input.set('value', 'foo');
            picker.fire('cancel', 'bogus');
            Assert.areEqual(
                '', picker._search_input.get('value'),
                "The widget hasn't been cleared");
        },

        test_search_clears_any_eror: function () {
            this.picker.render();
            this.picker.set('error', "An error");

            this.picker.fire('search');

            Assert.isNull(
                this.picker.get('error'), 'Error should be cleared.');

        },

        test_no_search_result_msg: function () {
            this.picker.render();

            this.picker.set(
                'no_results_search_message', "Your query '{query}' sucked.");
            var bb = this.picker.get('boundingBox');
            bb.one('.yui3-picker-search').set('value', 'my <search> string');
            this.picker.set('results', []);

            var search_results = bb.one('.yui3-picker-results');
            Assert.areEqual(
                "Your query 'my <search> string' sucked.",
                search_results.get('text'),
                "Empty results message wasn't displayed.");
            Assert.isTrue(
                search_results.hasClass('yui3-picker-no-results'),
                "Missing no-results CSS class.");
        },

        test_search_results_clear_no_results_css: function () {
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            bb.one('.yui3-picker-search').set('value', 'my search string');
            this.picker.set('results', []);

            this.picker.set('results',
                [{title: 'Title 1'},
                {title: 'Title 2'}]);
            Assert.isFalse(
                bb.one('.yui3-picker-results').
                    hasClass('yui3-picker-no-results'),
                "The no-results CSS class should have been removed.");
        },

        test_setting_search_slot_updates_ui: function () {
            this.picker.render();
            var filler = '<span>hello</span>';
            this.picker.set('search_slot', Y.Node.create(filler));
            var bb = this.picker.get('boundingBox');
            var div = bb.one('.yui3-picker-search-slot');

            Assert.isNotNull(div, 'Container for form extras not found.');
            Assert.areEqual(filler, div.get('innerHTML'));
        },

        test_setting_footer_slot_updates_ui: function () {
            this.picker.render();
            var filler = '<span>foobar</span>';
            this.picker.set('footer_slot', Y.Node.create(filler));
            var bb = this.picker.get('boundingBox');
            var div = bb.one('.yui3-picker-footer-slot');

            Assert.isNotNull(div, 'Container for form extras not found.');
            Assert.areEqual(filler, div.get('innerHTML'));
        },

        test_setting_batches_updates_ui: function () {
            this.picker.render();
            this.picker.set('batches', [
                {value: 'new', name: 'New'},
                {value: 'assigned', name: 'Assigned'}
                ]);
            var bb = this.picker.get('boundingBox');
            Assert.isNotNull(
                bb.one('.yui3-picker-batches span'),
                "Container for batches not found.");
            var batches = bb.all('.yui3-picker-batches span');
            Assert.isNotNull(batches, "Batches not found");
            Assert.areEqual(2, batches.size());
            ArrayAssert.itemsAreEqual(
                ['New', 'Assigned'],
                batches.get('text'),
                "Batches don't contain batch names.");
            ArrayAssert.itemsAreEqual(
                [true, false],
                batches.hasClass('yui3-picker-selected-batch'),
                "Selected batches missing CSS class.");

            Assert.isNotNull(
                bb.one('.yui3-picker-batches .lazr-prev'),
                "There should be a previous button.");
            Assert.isNotNull(
                bb.one('.yui3-picker-batches .lazr-next'),
                "There should be a next button.");
        },

        test_simplified_batching_interface: function () {
            this.picker.render();
            this.picker.set('batch_count', 4);
            this.picker.set('results', [
                { value: 'aardvark', title: 'Aardvarks' },
                { value: 'bats', title: 'Bats' },
                { value: 'cats', title: 'Cats' },
                { value: 'dogs', title: 'Dogs' },
                { value: 'emus', title: 'Emus' },
                { value: 'frogs', title: 'Frogs' },
                { value: 'gerbils', title: 'Gerbils' }
            ]);
            var bb = this.picker.get('boundingBox');
            Assert.isNotNull(
                bb.one('.yui3-picker-batches span'),
                "Container for batches not found.");
            var batches = bb.all('.yui3-picker-batches span');
            Assert.isNotNull(batches, "Batches not found");
            Assert.areEqual(4, batches.size());
            ArrayAssert.itemsAreEqual(
                ['1', '2', '3', '4'],
                batches.get('text'),
                "Batches don't contain batch names.");
            ArrayAssert.itemsAreEqual(
                [true, false, false, false],
                batches.hasClass('yui3-picker-selected-batch'),
                "Selected batches missing CSS class.");

            Assert.isNotNull(
                bb.one('.yui3-picker-batches .lazr-prev'),
                "There should be a previous button.");
            Assert.isNotNull(
                bb.one('.yui3-picker-batches .lazr-next'),
                "There should be a next button.");
        },

        test_clicking_a_batch_item_fires_search_event: function () {
            this.picker.set('current_search_string', 'search');
            this.picker.set('batches', [
                {value: 'item1', name: 'Item 1'},
                {value: 'item2', name: 'Item 2'}
                ]);
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            var event_has_fired = false;
            this.picker.subscribe('search', function(e) {
                event_has_fired = true;
                ArrayAssert.itemsAreEqual(
                    ['search', 'item1'], e.details,
                    "Search event details should contain search" +
                    "string and selected batch");
            }, this);
            simulate(
                this.picker.get('boundingBox'),
                '.yui3-picker-batches span', 'click');
            Assert.isTrue(event_has_fired, "search event wasn't fired.");
        },

        test_clicking_a_batch_item_sets_selected_batch: function () {
            this.picker.set('current_search_string', 'search');
            this.picker.set('batches', [
                {value: 'item1', name: 'Item 1'},
                {value: 'item2', name: 'Item 2'}
                ]);
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            Assert.areEqual(
                0, this.picker.get('selected_batch'),
                "First batch should be selected.");
            simulate(
                this.picker.get('boundingBox'),
                '.yui3-picker-batches span:nth-last-child(2)', 'click');
            Assert.areEqual(
                1, this.picker.get('selected_batch'),
                "selected_batch should have been updated.");
        },

        test_set_selected_batch_updates_css: function () {
            this.picker.render();
            this.picker.set('batches', [
                {value: 'item1', name: '1'},
                {value: 'item2', name: '2'}
                ]);
            Assert.areEqual(
                0, this.picker.get('selected_batch'),
                "Expected first batch to be selected by default.");
            this.picker.set('selected_batch', 1);

            var bb = this.picker.get('boundingBox');
            var batches = bb.all('.yui3-picker-batches span');
            ArrayAssert.itemsAreEqual(
                [false, true],
                batches.hasClass('yui3-picker-selected-batch'),
                "Selected batch missing CSS class.");
        },

        test_set_selected_batch_validator: function () {
            this.picker.render();
            this.picker.set('batches', [
                {value: 'item1', name: '1'},
                {value: 'item2', name: '2'}
                ]);

            this.picker.set('selected_batch', -1);
            Assert.areEqual(
                0, this.picker.get('selected_batch'),
                "Negative index shouldn't update selected_batch.");

            this.picker.set('selected_batch', 3);
            Assert.areEqual(
                0, this.picker.get('selected_batch'),
                "Index greather than last batch item shouldn't " +
                "update selected_batch.");

            this.picker.set('selected_batch', 'one');
            Assert.areEqual(
                0, this.picker.get('selected_batch'),
                "Non-integere shouldn't update selected_batch.");
        },

        test_prev_button_is_disabled_only_on_first_batch: function () {
            this.picker.set('batches', [
                {value: 'item1', name: '1'},
                {value: 'item2', name: '2'}
                ]);
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            Assert.isTrue(
                bb.one('.lazr-prev').get('disabled'),
                "Previous button should be disabled on first batch.");

            this.picker.set('selected_batch', 1);
            Assert.isFalse(
                bb.one('.lazr-prev').get('disabled'),
                "Previous button shouldn't be disabled on last batch.");
        },

        test_next_button_is_disabled_only_on_last_batch: function () {
            this.picker.set('batches', [
                {value: 'item1', name: '1'},
                {value: 'item2', name: '2'}
                ]);
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            Assert.isFalse(
                bb.one('.lazr-next').get('disabled'),
                "Next button shouldn't be disabled on first batch.");

            this.picker.set('selected_batch', 1);
            Assert.isTrue(
                bb.one('.lazr-next').get('disabled'),
                "Previous button should be disabled on last batch.");
        },

        test_click_on_next_button_selects_next_batch: function () {
            this.picker.set('batches', [
                {value: 'item1', name: '1'},
                {value: 'item2', name: '2'},
                {value: 'item3', name: '3'}
                ]);
            this.picker.set('selected_batch', 1);
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            simulate(
                this.picker.get('boundingBox'), '.lazr-next.lazr-btn', 'click');
            Assert.areEqual(
                2, this.picker.get('selected_batch'),
                "Next batch should have been selected.");
        },

        test_click_on_next_button_fires_search_event: function () {
            this.picker.set('current_search_string', 'search');
            this.picker.set('batches', [
                {value: 'item1', name: 'Item 1'},
                {value: 'item2', name: 'Item 2'}
                ]);
            this.picker.render();

            var event_has_fired = false;
            this.picker.subscribe('search', function(e) {
                event_has_fired = true;
                ArrayAssert.itemsAreEqual(
                    ['search', 'item2'], e.details,
                    "Search event details should contain search" +
                    "string and selected batch");
            }, this);
            simulate(
                this.picker.get('boundingBox'),
                '.yui3-picker-batches .lazr-next', 'click');
            Assert.isTrue(event_has_fired, "search event wasn't fired.");
        },

        test_click_on_prev_button_selects_prev_batch: function () {
            this.picker.set('batches', [
                {value: 'item1', name: '1'},
                {value: 'item2', name: '2'},
                {value: 'item3', name: '3'}
                ]);
            this.picker.set('selected_batch', 1);
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            simulate(
                this.picker.get('boundingBox'), '.lazr-prev.lazr-btn', 'click');
            Assert.areEqual(
                0, this.picker.get('selected_batch'),
                "Previous batch should have been selected.");
        },

        test_click_on_prev_button_fires_search_event: function () {
            this.picker.set('current_search_string', 'search');
            this.picker.set('batches', [
                {value: 'item1', name: 'Item 1'},
                {value: 'item2', name: 'Item 2'}
                ]);
            this.picker.set('selected_batch', 1);
            this.picker.render();

            var event_has_fired = false;
            this.picker.subscribe('search', function(e) {
                event_has_fired = true;
                ArrayAssert.itemsAreEqual(
                    ['search', 'item1'], e.details,
                    "Search event details should contain search" +
                    "string and selected batch");
            }, this);
            simulate(
                this.picker.get('boundingBox'),
                '.yui3-picker-batches .lazr-prev', 'click');
            Assert.isTrue(event_has_fired, "search event wasn't fired.");
        },

        test_buttons_are_displayed_only_if_there_are_batches: function () {
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            Assert.isNull(
                bb.one('.yui3-picker-batches .lazr-prev'),
                "There should be no previous button.");
            Assert.isNull(
                bb.one('.yui3-picker-batches .lazr-next'),
                "There should be no next button.");
        },

        test_text_input_on_footer_can_be_focused: function () {
            this.picker.render();
            this.picker.set('footer_slot', Y.Node.create(
                '<input class="extra-input" name="extra_input" type="text" />'));
            var extra_input =
                this.picker.get('boundingBox').one('.extra-input');
            var got_focus = false;
            extra_input.on('focus', function(e) {
                got_focus = true;
            });
            extra_input.focus();
            Assert.isTrue(got_focus, "focus didn't go to the extra input.");
        },

        test_overlay_progress_value: function () {
            // Setting the progress attribute controls the overlay's
            // green progress bar.
            this.picker.render();
            Assert.areEqual(
                50,
                this.picker.get('progress'),
                "The picker should start out with progress at 50%.");

            this.picker.set('results', [
                {
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com'
                }
            ]);
            Assert.areEqual(
                100,
                this.picker.get('progress'),
                "The picker progress should be 100% with results.");

            this.picker.set('results', []);
            Assert.areEqual(
                50,
                this.picker.get('progress'),
                "The picker progress should be 50% without results.");
        },

        test_exiting_search_mode_focus_search_box: function () {
            this.picker.render();
            this.picker.set('search_mode', true);

            var bb = this.picker.get('boundingBox');
            var search_input = bb.one('.yui3-picker-search');
            var got_focus = false;
            search_input.on('focus', function(e) {
                got_focus = true;
            });
            this.picker.set('search_mode', false);
            Assert.isTrue(got_focus, "focus didn't go to the search input.");
        }
    }));

    tests.suite.add(new Y.Test.Case({

        name: 'picker_with_filter',

        setUp: function() {
            this.picker = new Y.lp.ui.picker.Picker({
                "selected_value": 'foo',
                "selected_value_metadata": 'foobar',
                "filter_options": [
                    {'name': 'ALL',
                     'title': 'All',
                     'description': 'Display all'},
                    {'name': 'PROJECT',
                     'title': 'Product',
                     'description': 'Display products'}
                ]
            });
        },

        tearDown: function() {
            cleanup_widget(this.picker);
        },

        test_picker_has_elements: function () {
             // Test renderUI() adds filter container container to the widget.
            this.picker.render();

            var bb = this.picker.get('boundingBox');
            Assert.isNotNull(
                bb.one('.yui3-picker-filter'),
                "Missing filter box.");
        },

        _check_filter: function (filter_data) {
            // Check the expected filter links are rendered with the correct
            // data.
            var filter_div = this.picker.get('boundingBox')
                .one('.yui3-picker-filter');
            var i;
            for (i=0; i<filter_data.length; i++) {
            var link = filter_div.one('a:nth-child(' + (i + 1) + ')');
                Assert.isTrue(link.hasClass(filter_data[i].css));
                Assert.areEqual(link.get('text'), filter_data[i].title);
                Assert.areEqual(link.get('title'), filter_data[i].description);
            }
        },

        test_no_results_does_not_render_filter: function () {
            // Rendering empty results doesn't render the filter and clears it
            // if it is already visible.
            this.picker.render();
            this.picker._search_input.set('value', 'Joe');
            var filter_div = this.picker.get('boundingBox')
                .one('.yui3-picker-filter');
            // Make the filter visible by rendering some results.
            this.picker.set('results', [
                {
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com'
                }
            ]);
            Assert.areNotEqual('', filter_div.get('innerHTML'));
            // Reset and render empty results.
            this.picker.set('current_filter_value', null);
            this.picker.set('results', []);
            Assert.areEqual('', filter_div.get('innerHTML'));
        },

        test_set_results_renders_filter: function () {
            // Rendering results also renders the filter elements.
            this.picker.render();
            this.picker._search_input.set('value', 'Joe');
            this.picker.set('results', [
                {
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com'
                }
            ]);
            var filter_div = this.picker.get('boundingBox')
                .one('.yui3-picker-filter');
            Assert.isNotNull(filter_div, "Filter not found");
            Assert.areEqual('Showing All matches for "Joe".' +
                            'Filter by:\u00A0All,\u00A0or\u00A0Product',
                filter_div.get('textContent'));
            this._check_filter([
                {css: 'invalid-link', title: 'All', description: 'Display all'},
                {css: 'js-action', title: 'Product',
                    description: 'Display products'}
            ]);
        },

        test_filter_search: function () {
            // When a filter link is clicked a new search is performed and the
            // filter is updated.
            this.picker.render();
            this.picker._search_input.set('value', 'Joe');
            this.picker.set('results', [
                {
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com'
                }
            ]);
            var search_ok = false;
            var picker = this.picker;
            this.picker.subscribe('search', function(e) {
                var search_string = e.details[0];
                var filter_name = e.details[3];
                Assert.areEqual('Joe', search_string);
                Assert.areEqual('PROJECT', filter_name);
                Assert.areEqual('Product', picker.get('current_filter_value'));
                search_ok = true;
                picker.set('results', [
                    {
                        value: 'jschmo',
                        title: 'Joe Schmo',
                        description: 'joe@example.com'
                    }
                ]);
            });
            var filter_div = this.picker.get('boundingBox')
                .one('.yui3-picker-filter');
            var filter_link = filter_div.one('a:nth-child(2)');
            filter_link.simulate('click');
            Assert.isTrue(search_ok);
            this._check_filter([
                {css: 'js-action', title: 'All', description: 'Display all'},
                {css: 'invalid-link', title: 'Product',
                    description: 'Display products'}
            ]);
        },

        test_filter_search_no_results: function () {
            // When a filter link is clicked and no results are returned, the
            // filter is still visible.
            this.picker.render();
            this.picker._search_input.set('value', 'Joe');
            this.picker.set('results', [
                {
                    value: 'jschmo',
                    title: 'Joe Schmo',
                    description: 'joe@example.com'
                }
            ]);
            var search_ok = false;
            var picker = this.picker;
            this.picker.subscribe('search', function(e) {
                var search_string = e.details[0];
                var filter_name = e.details[3];
                Assert.areEqual('Joe', search_string);
                Assert.areEqual('PROJECT', filter_name);
                Assert.areEqual('Product', picker.get('current_filter_value'));
                search_ok = true;
                picker.set('results', []);
            });
            var filter_div = this.picker.get('boundingBox')
                .one('.yui3-picker-filter');
            var filter_link = filter_div.one('a:nth-child(2)');
            filter_link.simulate('click');
            Assert.isTrue(search_ok);
            this._check_filter([
                {css: 'js-action', title: 'All', description: 'Display all'},
                {css: 'invalid-link', title: 'Product',
                    description: 'Display products'}
            ]);
        },

        test_search_resets_filter: function () {
            // When a new search is performed the current filter is reset.
            this.picker.render();
            var picker = this.picker;
            var search_ok = false;
            this.picker.set('current_filter_value', 'Product');
            this.picker._search_input.set('value', 'Joe');
            this.picker.subscribe('search', function(e) {
                var search_string = e.details[0];
                var filter_name = e.details[3];
                Assert.areEqual('Joe', search_string);
                Assert.isFalse(Y.Lang.isValue(filter_name));
                Assert.isFalse(
                    Y.Lang.isValue(picker.get('current_filter_value')));
                search_ok = true;
            });
            this.picker._search_button.simulate('click');
            Assert.isTrue(search_ok);
        }
    }));

    tests.suite.add(new Y.Test.Case({

        name: 'picker_text_field_plugin',

        setUp: function() {
            this.search_input = Y.Node.create(
                    '<input id="field.initval" value="foo"/>');
            Y.one(document.body).appendChild(this.search_input);
            this.picker = new Y.lp.ui.picker.Picker({
                associated_field_id: 'field.initval'
            });
        },

        tearDown: function() {
            cleanup_widget(this.picker);
            this.search_input.remove();
        },

        test_TextFieldPickerPlugin_initial_value: function () {
            this.picker.render();
            this.picker.show();
            Assert.areEqual('foo', this.picker._search_input.get('value'));
        },

        test_TextFieldPickerPlugin_selected_item_is_saved: function () {
            this.picker.set('results', [{
                title: 'Object 1',
                value: 'first',
                metadata: 'new_metadata'}]
            );
            this.picker.render();
            var got_focus = false;
            this.search_input.on('focus', function(e) {
                got_focus = true;
            });
            simulate(
                this.picker.get('boundingBox'),
                    '.yui3-picker-results li', 'click');
            Assert.areEqual(
                'first', Y.one('[id="field.initval"]').get("value"));
            Assert.areEqual(
                'new_metadata', this.picker.get('selected_value_metadata'));
            Assert.areEqual(
                'first', this.picker.get('selected_value'));
            Assert.isTrue(got_focus, "focus didn't go to the search input.");
        }

    }));

}, '0.1', {
    'requires': ['test', 'test-console', 'lp.ui.picker-base', 'event',
        'node-event-simulate', 'dump']
});
