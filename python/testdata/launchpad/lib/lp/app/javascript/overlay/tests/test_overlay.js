/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.overlay.test', function (Y) {

    var tests = Y.namespace('lp.overlay.test');
    tests.suite = new Y.Test.Suite('overlay Tests');

    // KeyCode for escape
    var ESCAPE = 27;

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
        if (!widget) {
            return;
        }
        if (widget.get('rendered')) {
            var bb = widget.get('boundingBox');
            bb.get('parentNode').removeChild(bb);
        }
        // Kill the widget itself.
        widget.destroy();
    }

    tests.suite.add(new Y.Test.Case({
        name: 'overlay_tests',

        setUp: function() {
            this.overlay = null;
        },

        tearDown: function() {
            cleanup_widget(this.overlay);
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.ui.PrettyOverlay,
                "Could not locate the lp.ui.overlay module");
        },

        hitEscape: function() {
            simulate(this.overlay.get('boundingBox'),
                     '.close .close-button',
                     'keydown', { keyCode: ESCAPE });
        },

        test_picker_can_be_instantiated: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay();
            Assert.isInstanceOf(
                Y.lp.ui.PrettyOverlay,
                this.overlay,
                "Overlay not instantiated.");
        },

        test_overlay_has_elements: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay();
            this.overlay.render();
            var bb = this.overlay.get('boundingBox');
            Assert.isNotNull(
                bb.one('.close'),
                "Missing close button div.");
            Assert.isNotNull(
                bb.one('.close .close-button'),
                "Missing close button.");
        },

        test_overlay_can_show_progressbar: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay({
                'headerContent': 'bu bu bu'
            });
            var bb = this.overlay.get('boundingBox');
            this.overlay.render();
            Assert.isNotNull(
                bb.one('.steps'),
                "Progress bar is not present.");
        },

        test_overlay_can_hide_progressbar: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay({progressbar: false});
            this.overlay.render();
            var bb = this.overlay.get('boundingBox');
            bb.set('headerContent', 'ALL HAIL DISCORDIA!');
            Assert.isNull(
                bb.one('.steps'),
                "Progress bar is present when it shouldn't be.");
        },

        test_overlay_can_show_steptitle: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay({
                'headerContent': 'Fnord',
                'steptitle': 'No wife, no horse and no moustache'});
            var bb = this.overlay.get('boundingBox');
            this.overlay.render();
            Assert.isNotNull(
                bb.one('.contains-steptitle h2'),
                "Step title is not present.");
        },

        test_overlay_can_hide_steptitle: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay({progressbar: false});
            this.overlay.render();
            var bb = this.overlay.get('boundingBox');
            bb.set('headerContent', 'ALL HAIL DISCORDIA!');
            Assert.isNull(
                bb.one('.contains-steptitle h2'),
                "Step title is present when it shouldn't be.");
        },

        test_click_cancel_hides_the_widget: function() {
            /* Test that clicking the cancel button hides the widget. */
            this.overlay = new Y.lp.ui.PrettyOverlay();
            this.overlay.render();

            simulate(this.overlay.get('boundingBox'),
                '.close .close-button', 'click');
            Assert.isFalse(this.overlay.get('visible'),
                "The widget wasn't hidden");
        },

        test_click_cancel_fires_cancel_event: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay();
            this.overlay.render();

            var event_was_fired = false;
            this.overlay.subscribe('cancel', function() {
                    event_was_fired = true;
            }, this);
            simulate(this.overlay.get('boundingBox'),
                '.close .close-button','click');
            Assert.isTrue(event_was_fired, "cancel event wasn't fired");
        },

        test_stroke_escape_hides_the_widget: function() {
            /* Test that stroking the escape button hides the widget. */
            this.overlay = new Y.lp.ui.PrettyOverlay();
            this.overlay.render();

            Assert.isTrue(this.overlay.get('visible'),
                "The widget wasn't visible");
            this.hitEscape();
            Assert.isFalse(this.overlay.get('visible'),
                "The widget wasn't hidden");
        },

        test_stroke_escape_fires_cancel_event: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay();
            this.overlay.render();

            var event_was_fired = false;
            this.overlay.subscribe('cancel', function() {
                event_was_fired = true;
            }, this);
            this.hitEscape();
            Assert.isTrue(event_was_fired, "cancel event wasn't fired");
        },

        test_show_again_re_hooks_events: function() {
            /* Test that hiding the overlay and showing it again
             * preserves the event handlers.
             */
            this.overlay = new Y.lp.ui.PrettyOverlay();
            this.overlay.render();

            this.hitEscape();
            Assert.isFalse(this.overlay.get('visible'),
                "The widget wasn't hidden");
            this.overlay.show();
            Assert.isTrue(this.overlay.get('visible'),
                "The widget wasn't shown again");
            this.hitEscape();
            Assert.isFalse(this.overlay.get('visible'),
                "The widget wasn't hidden");
        },

        test_pretty_overlay_without_header: function() {
            this.overlay = new Y.lp.ui.PrettyOverlay();
            function PrettyOverlaySubclass(config) {
                PrettyOverlaySubclass.superclass.constructor.apply(
                    this,
                    arguments
                );
            }
            PrettyOverlaySubclass.NAME = 'lp-ui-overlaysubclass';
            Y.extend(PrettyOverlaySubclass, Y.lp.ui.PrettyOverlay);

            var overlay = new PrettyOverlaySubclass({bodyContent: "Hi"});
            // This shouldn't raise an error if the header content is not
            // supplied and progressbar is set to `true`.
            overlay.render();
            cleanup_widget(overlay);
        },

        test_overlay_bodyContent_has_size_1: function() {
            this.overlay = new Y.Overlay({
                headerContent: 'Form for testing',
                bodyContent: '<input type="text" name="field1" />'
            });
            this.overlay.render();
            Assert.areEqual(
                1,
                this.overlay.get("bodyContent").size(),
                "The bodContent should contain only one node.");
        },

        test_set_progress: function() {
            // test that the progress bar is settable
            this.overlay = new Y.lp.ui.PrettyOverlay({
                'headerContent': 'Fnord',
                'steptitle': 'No wife, no horse and no moustache'});
            this.overlay.render();
            this.overlay.set('progress', 23);
            Assert.areEqual(
                '23%',
                this.overlay.get('boundingBox').
                    one('.steps .step-on').
                    getStyle('width')
            );
        },

        test_getTabNodes_types: function() {
            // Tabbable nodes include <a>, <button>, <input>, <select>.
            // Remember that the 0 button is the close button in the header.
            this.overlay = new Y.lp.ui.PrettyOverlay({
                headerContent: 'Fnord',
                bodyContent: [
                    '<div>',
                    '<b>ignored</b>',
                    '<input type="text" value="1"/>',
                    '<select><option>2</option></select>',
                    '<a href="#">3</a>',
                    '<button>4</button>',
                    '<textarea rows="2" cols="5">5</textarea>',
                    '</div>'].join(' ')
            });
            this.overlay.render();
            var tab_nodes = this.overlay._getTabNodes();
            Y.Assert.areEqual(6, tab_nodes.size());
        },

        test_getTabNodes_visibility: function() {
            // Hidden nodes are exluded because tab ignores them.
            // Remember that the 0 button is the close button in the header.
            this.overlay = new Y.lp.ui.PrettyOverlay({
                headerContent: 'Fnord',
                bodyContent: [
                    '<div>',
                    '<a href="#">1</a>',
                    '<input type="text" value="2"/>',
                    '<a style="display:none;">ignored</a>',
                    '<span style="display:none;"><button>nil</button></span>',
                    '<span style="visibility:hidden;">',
                    '  <button>nil</button>',
                    '</span>',
                    '</div>'].join(' ')
            });
            this.overlay.render();
            var tab_nodes = this.overlay._getTabNodes();
            Y.Assert.areEqual(3, tab_nodes.size());
        },

        test_handleTab_last_to_first: function() {
            // Tabbing from the last navigatable node moves focus to the first.
            // Remember that the 0 button is the close button in the header.
            this.overlay = new Y.lp.ui.PrettyOverlay({
                headerContent: 'Fnord',
                bodyContent: '<div><a href="#">1</a> <a href="#">2</a></div>'
            });
            this.overlay.render();
            var nodes = this.overlay.get('boundingBox').all('a');
            var focused = false;
            nodes.item(0).after('focus', function(e) {
                focused = true;});
            var halted = false;
            var fake_e = {
                keyCode: 9, shiftKey: false, currentTarget: nodes.item(2),
                halt: function() {halted = true;}};
            this.overlay._handleTab(fake_e);
            Y.Assert.isTrue(halted);
            Y.Assert.isTrue(focused);
        },

        test_handleTab_first_to_last: function() {
            // Shift+Tab from the first navigatable node moves focus
            // to the last.
            // Remember that the 0 button is the close button in the header.
            this.overlay = new Y.lp.ui.PrettyOverlay({
                headerContent: 'Fnord',
                bodyContent: '<div><a href="#">1</a> <a href="#">2</a></div>'
            });
            this.overlay.render();
            var nodes = this.overlay.get('boundingBox').all('a');
            var focused = false;
            nodes.item(2).after('focus', function(e) {
                focused = true;});
            var halted = false;
            var fake_e = {
                keyCode: 9, shiftKey: true, currentTarget: nodes.item(0),
                halt: function() {halted = true;}
            };
            this.overlay._handleTab(fake_e);
            Y.Assert.isTrue(halted);
            Y.Assert.isTrue(focused);
        },

        test_handleTab_within_tab_range: function() {
            // Tab from one element to another that is not beyond the
            // first or last element does nothing special.
            // Remember that the 0 button is the close button in the header.
            this.overlay = new Y.lp.ui.PrettyOverlay({
                headerContent: 'Fnord',
                bodyContent: '<div><a href="#">1</a> <a href="#">2</a></div>'
            });
            this.overlay.render();
            var nodes = this.overlay.get('boundingBox').all('a');
            var focused = false;
            nodes.after('focus', function(e) {focused = true;});
            var halted = false;
            var fake_e = {
                keyCode: 9, shiftKey: false, currentTarget: nodes.item(0),
                halt: function() {halted = true;}
            };
            this.overlay._handleTab(fake_e);
            Y.Assert.isFalse(halted);
            Y.Assert.isFalse(halted);
        }
    }));

}, '0.1', {
    'requires': ['test', 'test-console', 'lp.ui.overlay', 'node', 'event',
        'event-simulate', 'widget-stack']
});
