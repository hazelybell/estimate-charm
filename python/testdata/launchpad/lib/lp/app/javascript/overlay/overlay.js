/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.ui.overlay', function(Y) {

/**
 * LP overlay implementation.
 *
 * @module lp.ui.overlay
 */

var ns = Y.namespace('lp.ui');

var ESCAPE = 27,
    TAB = 9,
    CANCEL = 'cancel',
    BOUNDING_BOX = 'boundingBox',
    CONTENT_BOX = 'contentBox',
    BINDUI = "bindUI",
    TABBABLE_SELECTOR = 'a, button, input, select, textarea';


   /**
    * An Overlay subclass which draws a rounded-corner, drop-shadow
    * border around the content.
    * TODO PrettyOverlay implements an in-page modal dialog box.
    * The background is blocked using a layer, in order to prevent
    * clicks on other elements on the page. Pressing Escape or clicking
    * the close button at the top-right corner dismisses the box.
    *
    * Note: Classes extending PrettyOverlay must have a corresponding
    * yui3-widget-name-hidden CSS class in order to allow hiding.
    * Also, all extending classes must explicitly calls PrettyOverlay's
    * bindUI method in order to get the event handlers attached.
    *
    * @class PrettyOverlay
    */
    var PrettyOverlay;
    PrettyOverlay = function(cfg) {
        // Check whether the callsite has set a zIndex... if not, set it
        // to 1000, as the YUI.overlay default is zero.
        if (cfg && arguments[0].zIndex === undefined){
            arguments[0].zIndex = 1000;
        }
        PrettyOverlay.superclass.constructor.apply(this, arguments);
        Y.after(this._bindUIPrettyOverlay, this, BINDUI);

    };

    PrettyOverlay.NAME = 'pretty-overlay';

    PrettyOverlay.ATTRS = {
       /**
        * The value, in percentage, of the progress bar.
        *
        * @attribute progress
        * @type Float
        * @default 100
        */
        progress: {
            value: 100
        },

       /**
        * Should the progress bar be shown?
        * (note that if set to true, headerContent must be supplied).
        *
        * @attribute progressbar
        * @type Boolean
        * @default true
        */
        progressbar: {
            value: true
        },

       /**
        * Title for this step, displayed below the progressbar.
        * (you must have a progressbar to have a steptitle)
        *
        * @attribute steptitle
        * @type Boolean
        * @default null
        */
        steptitle: {
          value: null
        }
    };

    Y.extend(PrettyOverlay, Y.Overlay, {
        /**
         * The div element shown behind the modal dialog.
         *
         * @private
         * @property _blocking_div
         * @type Node
         */
        _blocking_div: null,

        /**
         * The key press handler..
         *
         * @private
         * @property _doc_kp_handler
         * @type EventHandle
         */
        _doc_kp_handler: null,

        /**
         * The div displaying the prograss bar.
         *
         * @private
         * @property _green_bar
         * @type Node
         */
        _green_bar: null,

       /**
        * Create the DOM elements needed by the widget.
        *
        * @protected
        * @method initializer
        */
        initializer: function() {
            // The 20% width style is here to force
            // legacy browsers to include an accessible
            // style attribute.
            this._green_bar = Y.Node.create([
              '<div class="steps">',
              '<div class="step-on" style="width:20%;">',
              '</div></div>'].join(""));

            this._blocking_div = Y.Node.create(
                '<div class="blocking-div"></div>');

            this.after("renderedChange", function() {
                var bounding_box = this.get(BOUNDING_BOX);
                var content_box = this.get(CONTENT_BOX);
                var content_box_container = bounding_box.one(
                    ".content_box_container");
                if (content_box_container) {
                    content_box_container.appendChild(content_box);
                }
                this._setupCloseFacilities();
            });

            this.after('visibleChange', function(e) {
                this._setupCloseFacilities();
            });

           /**
            * Fires when the user presses the 'Cancel' button.
            *
            * @event cancel
            * @preventable _defCancel
            */
            this.publish(CANCEL, {
                defaultFn: this._defaultCancel
            });
        },

        /**
         * Event handler to update HTML when steptitle is set.
         *
         * @private
         * @param e {Event.Facade}
         * @method _afterSteptitleChange
         */
        _afterSteptitleChange: function(e) {
            // It's only possible to  have a step title
            // if you also have a progress bar.
            var progress_bar = this.get(BOUNDING_BOX).one(".steps");
            if (!progress_bar) {
                return;
            }
            var h2 = progress_bar.one("h2");
            if (!h2) {
              h2 = Y.Node.create("<h2></h2>");
              progress_bar.appendChild(h2);
              progress_bar.addClass("contains-steptitle");
            }
            // We can't just set innerHTML here because Firefox gets it wrong
            // so remove all existing nodes and add the steptitle as a textnode
            while (h2.hasChildNodes()) {
              h2.removeChild(h2.get("firstChild"));
            }
            h2.appendChild(document.createTextNode(this.get("steptitle")));
        },

        /**
         * Handle the progress change event, adjusting the display
         * of the progress bar.
         *
         * @private
         * @param e {Event.Facade}
         * @method _afterProgressChange
         */
        _afterProgressChange: function(e) {
            var width = parseInt(this.get("progress"), 10);
            if (width < 0) {
                width = 0;
            }
            if (width > 100) {
                width = 100;
            }
            if (this.get("progressbar") &&
                this.get(CONTENT_BOX).one(".steps")) {
                // The prograss bar is only being created if
                // you both ask for it and supply header content
                var progress_steps = this.get(CONTENT_BOX).one(".step-on");
                progress_steps.setStyle("width", width + "%");
            }
        },

        /**
         * Hook the events for the escape key press and include
         * the blocking div.
         *
         * @protected
         * @method _setupCloseFacilities
         */
        _setupCloseFacilities: function() {
            var self = this;
            var visible = this.get('visible');
            if (visible) {
                Y.one('body').appendChild(this._blocking_div);
                // Handle Escape (code 27) on keydown.
                this._doc_kp_handler = Y.on('key', function() {
                        self.fire(CANCEL);
                    }, document, 'down:27');
            } else {
                this._removeBlockingDiv();
            }
        },

        /**
         * Remove the HTML for the blocking DIV.
         *
         * @method _removeBlockingDiv
         */
        _removeBlockingDiv: function() {
            if (this._blocking_div) {
                var blocking_div = Y.one(this._blocking_div);
                if (blocking_div) {
                    var parent = blocking_div.get('parentNode');
                    if (parent) {
                        parent.removeChild(this._blocking_div);
                    }
                }
            }
        },

        /**
         * Destroy the widget (remove its HTML from the page).
         *
         * @method destructor
         */
        destructor: function() {
            this._removeBlockingDiv();
            if (this._doc_kp_handler) {
                this._doc_kp_handler.detach();
            }
        },

        /**
         * Bind UI events.
         * <p>
         * This method is invoked after bindUI is invoked for the Widget class
         * using YUI's aop infrastructure.
         * </p>
         *
         * @method _bindUIPrettyOverlay
         * @protected
         */
        _bindUIPrettyOverlay: function() {
            var self = this;
            var close_button = this.get(BOUNDING_BOX).one('.close a');
            close_button.on('click', function(e) {
                e.halt();
                self.fire(CANCEL);
            });
            this._blocking_div.on('click', function(e) {
                e.halt();
                self.fire(CANCEL);
            });
            // Ensure that when the overlay is clicked, it doesn't stay
            // focused (with the ugly gray border).
            var bounding_box = this.get(BOUNDING_BOX);
            bounding_box.on('click', function(e) {
                bounding_box.blur();
            });
            bounding_box.delegate(
                "keydown", this._handleTab, TABBABLE_SELECTOR, this);
            this.after('steptitleChange', this._afterSteptitleChange);
            this.after('progressChange', this._afterProgressChange);
        },

        /**
         * Event handler for cancel event; hides the widget.
         *
         * @private
         * @method _defaultCancel
         */
        _defaultCancel: function(e) {
            this.hide();
            this._doc_kp_handler.detach();
        },

        /**
         * Return a NodeList of elements that the user can navigate
         * to using the Tab key. Browser allow users to tab to:
         * a, button, input, select, and textarea. The NodeList only
         * contains the elements the user can see and interact with.
         *
         * @private
         * @method _getTabNodes
         */
         _getTabNodes: function() {
            var bounding_box = this.get(BOUNDING_BOX);
            var all_tab_nodes = bounding_box.all(TABBABLE_SELECTOR);
            var tab_nodes = new Y.NodeList([]);
            all_tab_nodes.each(function(item, index, node_list) {
                var displayed = item.get('region').height > 0;
                var visible = item.getComputedStyle(
                    'visibility') === 'visible';
                if (displayed && visible) {
                    // The node takes up space and can be seen on the page.
                    // This rule will skip empty links that cannot be focused.
                    tab_nodes.push(item);
                }
            });
            return tab_nodes;
        },

        /**
         * An event handler to ensure the Tab key cycles through
         * The visible elements that the user can interact with.
         * The user cannot tab out of the modal overlay.
         *
         * @private
         * @method _handleTab
         */
        _handleTab: function(e) {
            if (e.keyCode === TAB) {
                var tab_nodes = this._getTabNodes();
                var max_index = tab_nodes.size() - 1;
                var next = (e.shiftKey) ? -1 : 1;
                var next_index = tab_nodes.indexOf(e.currentTarget) + next;
                if (next_index > max_index) {
                    tab_nodes.item(0).focus();
                    e.halt();
                } else if (next_index < 0) {
                    tab_nodes.item(max_index).focus();
                    e.halt();
                }
            }
        },

        /**
         * Overrides the method from WidgetStdMod which creates the separate
         * sections in the contentBox to also add the progressbar widget
         * after headerContent.
         *
         * @private
         * @method _insertStdModSection
         */
        _insertStdModSection: function(content_box, section, section_node) {
            PrettyOverlay.superclass._insertStdModSection.apply(
                this, arguments);
            if (section === Y.WidgetStdMod.HEADER &&
                this.get("progressbar"))
            {
                var nxt = section_node.next();
                if (nxt) {
                  content_box.insertBefore(this._green_bar, nxt);
                } else {
                  content_box.appendChild(this._green_bar);
                }
            }
            this._afterProgressChange();
            if (this.get('steptitle')) {
                this._afterSteptitleChange();
            }
        }
    });

   /**
    * The HTML for drawing the border.
    *
    * The border is implemented using a table. The content area is
    * marked with the `content_box_container` class so that the widget
    * can find it and insert the content box into it.
    *
    * @property BOUNDING_TEMPLATE
    */
    PrettyOverlay.prototype.BOUNDING_TEMPLATE = [
        '<div class="pretty-overlay-window">',
        '<div class="content_box_container" id="yui3-pretty-overlay-modal">',
        '<div class="close">',
        '<a href="#" title="Close" class="close-button">(x)</a>',
        '</div>',
        '</div>',
        '</div>'].join('');

    ns.PrettyOverlay = PrettyOverlay;

}, "0.1", {"skinnable": true, "requires": [
    "oop", "overlay", "event", "widget", "widget-stack", "widget-position"]});
