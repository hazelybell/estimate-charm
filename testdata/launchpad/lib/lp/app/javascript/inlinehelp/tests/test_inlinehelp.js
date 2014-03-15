/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.inlinehelp.test', function (Y) {

    var tests = Y.namespace('lp.app.inlinehelp.test');
    tests.suite = new Y.Test.Suite('InlineHelp Tests');
    var Assert = Y.Assert;
    tests.suite.add(new Y.Test.Case({
        name: 'inlinehelp.init_help',

        setUp: function () {
            var link_html = Y.Node.create(
                '<a href="/+help-bugs/bug-heat.html" target="help"/>');
            Y.one('body').appendChild(link_html);
        },

        tearDown: function () {
            Y.all('a[target="help"]').remove();
            Y.one('body').detach('click');
            Y.all('.pretty-overlay-window').remove();
        },

        test_adding_css_class: function () {
            // calling init help should add a help css class to all links with
            // target=help
            var called = false;
            Y.lp.app.inlinehelp.init_help();
            Y.all('a[target="help"]').each(function (node) {
                called = true;
                Y.Assert.isTrue(node.hasClass('help'),
                    'Each link should have the class "help"');
            });

            Y.Assert.isTrue(called, 'We should have called our class check');
        },

        test_binding_click_link: function () {
            // calling init help should a delegated click handler for the help
            // links

            // we need to mock out the inlinehelp.show_help function to add a
            // callable to run tests for us when clicked
            var orig_show_help = Y.lp.app.inlinehelp._show_help;
            var called = false;

            Y.lp.app.inlinehelp._show_help = function (e) {
                e.preventDefault();
                called = true;

                Y.Assert.areEqual(e.target.get('target'), 'help',
                    'The event target should be our <a> with target = help');
            };

            Y.lp.app.inlinehelp.init_help();

            Y.one('a[target="help"]').simulate('click');
            Y.Assert.isTrue(
                called,
                'We should have called our show_help function'
            );

            // restore the original show_help method for future tests
            Y.lp.app.inlinehelp._show_help = orig_show_help;
        },

        test_binding_click_only_once: function () {
            //verify that multiple calls to init_help only causes one click
            //event to fire
            var orig_show_help = Y.lp.app.inlinehelp._show_help;
            var called = 0;

            Y.lp.app.inlinehelp._show_help = function (e) {
                e.preventDefault();
                called = called + 1;
            };

            Y.lp.app.inlinehelp.init_help();
            Y.lp.app.inlinehelp.init_help();
            Y.lp.app.inlinehelp.init_help();
            Y.lp.app.inlinehelp.init_help();

            Y.one('a[target="help"]').simulate('click');
            Y.Assert.areEqual(
                called,
                1,
                'We should have called our show_help function only once'
            );
            // restore the original show_help method for future tests
            Y.lp.app.inlinehelp._show_help = orig_show_help;
        },

        test_click_gets_overlay: function () {
            // clicking on the link should get us an overlay
            Y.lp.app.inlinehelp.init_help();
            Y.one('a[target="help"]').simulate('click');
            Y.Assert.isObject(Y.one('.yui3-inlinehelp-overlay'),
                'Should find a node for the overlay');
        },

        test_click_get_content: function () {
            // if the contentUrl exists, we should get content. Fudge the ajax
            // response to return some known html.
            var orig_show_help = Y.lp.app.inlinehelp._show_help;
            var good_html =
                '<iframe src="file:///+help-bugs/bug-heat.html"></iframe>';

            Y.lp.app.inlinehelp._show_help = function (e) {
                e.preventDefault();
                var target_link = e.target;

                // init the overlay and show it
                overlay = new Y.lp.app.inlinehelp.InlineHelpOverlay({
                    'contentUrl': target_link.get('href')
                });
                overlay.render();
            };

            Y.lp.app.inlinehelp.init_help();
            Y.one('a[target="help"]').simulate('click');

            Y.Assert.areEqual(
                good_html,
                Y.one('.yui3-widget-bd').get('innerHTML'),
                'The body content should be an iframe with our link target'
            );

            Y.lp.app.inlinehelp._show_help = orig_show_help;
        }
    }));


}, '0.1', {
    'requires': ['node', 'test-console', 'test', 'lp.app.inlinehelp',
        'node-event-simulate'
    ]
});
