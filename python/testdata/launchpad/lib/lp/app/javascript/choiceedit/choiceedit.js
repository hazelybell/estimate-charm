/* Copyright 2008 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.ui.choiceedit', function(Y) {

/**
 * This class provides the ability to allow a specific field to be
 *  chosen from an enum, similar to a dropdown.
 *
 * This can be thought of as a rather pretty Ajax-enhanced dropdown menu.
 *
 * @module lp.ui.choiceedit
 */

var CHOICESOURCE       = 'ichoicesource',
    CHOICELIST         = 'ichoicelist',
    NULLCHOICESOURCE   = 'inullchoicesource',
    C_EDITICON         = 'editicon',
    C_VALUELOCATION    = 'value',
    C_NULLTEXTLOCATION = 'nulltext',
    C_ADDICON          = 'addicon',
    SAVE               = 'save',
    LEFT_MOUSE_BUTTON  = 1,
    RENDERUI           = "renderUI",
    BINDUI             = "bindUI",
    SYNCUI             = "syncUI",
    NOTHING            = {};

/**
 * This class provides the ability to allow a specific field to be
 * chosen from an enum, similar to a dropdown.
 *
 * @class ChoiceSource
 * @extends Widget
 * @constructor
 */

var ChoiceSource;
ChoiceSource = function() {
    ChoiceSource.superclass.constructor.apply(this, arguments);
    Y.after(this._bindUIChoiceSource, this, BINDUI);
    Y.after(this._syncUIChoiceSource, this, SYNCUI);
};

ChoiceSource.NAME = CHOICESOURCE;

/**
 * Dictionary of selectors to define subparts of the widget that we care
 * about.
 *
 * YUI calls ATTRS.set(foo) for each foo defined here.
 *
 * @property InlineEditor.HTML_PARSER
 * @type Object
 * @static
 */
ChoiceSource.HTML_PARSER = {
    value_location: '.' + C_VALUELOCATION,
    editicon: '.' + C_EDITICON
};

ChoiceSource.ATTRS = {
    /**
     * Possible values of the enum that the user chooses from.
     *
     * @attribute items
     * @type Array
     */
    items: {
        value: []
    },

    /**
     * Current value of enum
     *
     * @attribute value
     * @type String
     * @default null
     */
    value: {
        value: null
    },

    /**
     * List header displayed in the popup
     *
     * @attribute title
     * @type String
     * @default ""
     */
    title: {
        value: ""
    },

    /**
     * Y.Node displaying the current value of the field. Should be
     * automatically calculated by HTML_PARSER.
     * Setter function returns Y.one(parameter) so that you can pass
     * either a Node (as expected) or a selector.
     *
     * @attribute value_location
     * @type Node
     */
    value_location: {
      value: null,
      setter: function(v) {
        return Y.one(v);
      }
    },

    /**
     * Y.Node (img) displaying the editicon, which is exchanged for a spinner
     * while saving happens. Should be automatically calculated by
     * HTML_PARSER.
     *
     * Setter function returns Y.one(parameter) so that you can pass
     * either a Node (as expected) or a selector.
     *
     * @attribute value_location
     * @type Node
     */
    editicon: {
      value: null,
      setter: function(v) {
        return Y.one(v);
      }
    },

    /**
     * Y.Node display the action icon. The default implementation just returns
     * the edit icon, but it can be customized to return other elements in
     * subclasses.
     * @attribute actionicon
     * @type Node
     */
    actionicon: {
      getter: function() {
        return this.get('editicon');
      }
    },

    elementToFlash: {
      value: null,
      setter: function(v) {
        return Y.one(v);
      }
    },

    flashEnabled: {
        value: true
    },

    backgroundColor: {
      value: null
    },

    clickable_content: {
      value: true
    },

    zIndex: {
      value: 1000
    }
};

Y.extend(ChoiceSource, Y.Widget, {
    initializer: function(cfg) {
        /**
         * Fires when the user selects an item
         *
         * @event save
         * @preventable _saveData
         */
        this.publish(SAVE);
    },

    /**
     * Set up the click handler to activate the popup.
     *
     * @method _setupClickableContent
     * @protected
     */
    _setupClickableContent: function() {
        var content = this.get('contentBox');
        content.detachAll();
        var edit_icon = this.get('editicon');
        if (Y.Lang.isValue(edit_icon)) {
            edit_icon.detachAll();
        }
        var value = this.get('clickable_content');
        var clickable_element;
        if (value) {
            clickable_element = content;
        } else {
            content.addClass('no-click');
            clickable_element = edit_icon;
        }
        clickable_element.on("click", this.onClick, this);
    },

    /**
     * bind UI events
     * <p>
     * This method is invoked after bindUI is invoked for the Widget class
     * using YUI's aop infrastructure.
     * </p>
     *
     * @method _bindUIChoiceSource
     * @protected
     */
    _bindUIChoiceSource: function() {
        this._setupClickableContent();
        var that = this;
        this.after("clickable_contentChange", function(e) {
            that._setupClickableContent();
        });
        this.after("valueChange", function(e) {
            that.syncUI();
            if (that.get('flashEnabled')) {
                that._showSucceeded();
            }
        });
    },

    /**
     * Update in-page HTML with current value of the field
     * <p>
     * This method is invoked after syncUI is invoked for the Widget class
     * using YUI's aop infrastructure.
     * </p>
     *
     * @method _syncUIChoiceSource
     * @protected
     */
    _syncUIChoiceSource: function() {
        var items = this.get("items");
        var value = this.get("value");
        var node = this.get("value_location");
        var i;
        for (i = 0; i < items.length; i++) {
            if (items[i].value === value) {
                node.set("innerHTML", items[i].source_name || items[i].name);
            }
        }
    },

    _chosen_value: NOTHING,

    /**
     * Get the currently chosen value.
     *
     * Compatible with the Launchpad PATCH plugin.
     *
     * @method getInput
     */
    getInput: function() {
        if (this._chosen_value !== NOTHING) {
          return this._chosen_value;
        } else {
          return this.get("value");
        }
    },

    /**
     * Handle click and create the ChoiceList to allow user to
     * select an item
     *
     * @method onClick
     * @private
     */
    onClick: function(e) {
        this._choice_list = new Y.ChoiceList({
            value:          this.get("value"),
            title:          this.get("title"),
            items:          this.get("items"),
            value_location: this.get("value_location"),
            progressbar:    false,
            zIndex:         this.get("zIndex")
        });

        var that = this;
        this._choice_list.on("valueChosen", function(e) {
            that._chosen_value = e.details[0];
            that._saveData(e.details[0]);
        });

        // Stuff the mouse coordinates into the list object,
        // by the time we'll need them, they won't be available.
        this._choice_list._mouseX = e.clientX + window.pageXOffset;
        this._choice_list._mouseY = e.clientY + window.pageYOffset;

        this._choice_list.render();

        e.halt();
    },

    /**
     * bind UI events
     *
     * @private
     * @method _saveData
     */
    _saveData: function(newvalue) {
        this.set("value", newvalue);
        this.fire(SAVE);
    },

    /**
     * Called when save has succeeded to flash the in-page HTML green.
     *
     * @private
     * @method _showSucceeded
     */
    _showSucceeded: function() {
        this._uiAnimateFlash(Y.lp.anim.green_flash);
    },

    /**
     * Called when save has failed to flash the in-page HTML red.
     *
     * @private
     * @method _showFailed
     */
    _showFailed: function() {
        this._uiAnimateFlash(Y.lp.anim.red_flash);
    },

    /**
     * Run a flash-in animation on the editable text node.
     *
     * @method _uiAnimateFlash
     * @param flash_fn {Function} A lp.anim flash-in function.
     * @protected
     */
    _uiAnimateFlash: function(flash_fn) {
        var node = this.get('elementToFlash');
        if (node === null) {
          node = this.get('contentBox');
        }
        var cfg = { node: node };
        if (this.get('backgroundColor') !== null) {
          cfg.to = {backgroundColor: this.get('backgroundColor')};
        }
        var anim = flash_fn(cfg);
        anim.run();
    },

    /**
     * Set the 'waiting' user-interface state.  Be sure to call
     * _uiClearWaiting() when you are done.
     *
     * @method _uiSetWaiting
     * @protected
     */
    _uiSetWaiting: function() {
        var actionicon = this.get("actionicon");
        actionicon.original_src = actionicon.get("src");
        actionicon.set("src", "https://launchpad.net/@@/spinner");
    },

    /**
     * Clear the 'waiting' user-interface state.
     *
     * @method _uiClearWaiting
     * @protected
     */
    _uiClearWaiting: function() {
        var actionicon = this.get("actionicon");
        actionicon.set("src", actionicon.original_src);
    }

});


Y.ChoiceSource = ChoiceSource;

var ChoiceList;
ChoiceList = function() {
    ChoiceList.superclass.constructor.apply(this, arguments);
};

ChoiceList.NAME = CHOICELIST;

ChoiceList.ATTRS = {
    /**
     * Possible values of the enum that the user chooses from.
     *
     * @attribute items
     * @type Array
     */
    items: {
        value: []
    },

    /**
     * Current value of enum
     *
     * @attribute value
     * @type String
     * @default null
     */
    value: {
        value: null
    },

    /**
     * List header displayed in the popup
     *
     * @attribute title
     * @type String
     * @default ""
     */
    title: {
        value: ""
    },

    /**
     * Node currently containing the value, around which we need to
     * position ourselves
     *
     * @attribute value_location
     * @type Node
     */
     value_location: {
       value: null
     },

    /**
     * List of clickable enum values
     *
     * @attribute display_items_list
     * @type Node
     */
     display_items_list: {
       value: null
     }

};




Y.extend(ChoiceList, Y.lp.ui.PrettyOverlay, {
    initializer: function(cfg) {
        /**
         * Fires when the user selects an item
         *
         * @event valueChosen
         */
        this.publish("valueChosen");
        this.after("renderedChange", this._positionCorrectly);
        Y.after(this._renderUIChoiceList, this, RENDERUI);
        Y.after(this._bindUIChoiceList, this, BINDUI);
    },

    /**
     * Render the popup menu
     * <p>
     * This method is invoked after renderUI is invoked for the Widget class
     * using YUI's aop infrastructure.
     * </p>
     *
     * @method _renderUIChoiceList
     * @protected
     */
    _renderUIChoiceList: function() {
        this.set("align", {
          node: this.get("value_location"),
          points:[Y.WidgetPositionAlign.TL, Y.WidgetPositionAlign.TL]
        });
        this.set(
            'headerContent',
            Y.Node.create("<h2></h2>").set('text', this.get("title")));
        this.set("display_items_list", Y.Node.create("<ul>"));
        var display_items_list = this.get("display_items_list");
        var items = this.get("items");
        var value = this.get("value");
        var li;
        var i;
        for (i = 0; i < items.length; i++) {
            var desc_node = null;
            if (Y.Lang.isString(items[i].description)
                    && items[i].description !== '') {
                desc_node = Y.Node.create('<span></span>')
                    .setContent(items[i].description);
                var desc_css_class = items[i].description_css_class;
                if (Y.Lang.isValue(desc_css_class)) {
                    desc_node.addClass(desc_css_class);
                }
            }
            if (items[i].disabled) {
                li = Y.Node.create('<li><span class="disabled">' +
                    items[i].name + '</span></li>');
                if (desc_node !== null) {
                    li.one('span').appendChild(desc_node);
                }
            } else if (items[i].value === value) {
                li = Y.Node.create('<li><span class="current">' +
                    items[i].name + '</span></li>');
                if (desc_node !== null) {
                    li.one('span').appendChild(desc_node);
                }
            } else {
                li = Y.Node.create('<li><a href="#' + items[i].value + '">' +
                    '<span class="choice-link">' + items[i].name +
                    '</span></a></li>');
                li.one('a')._value = items[i].value;
                if (desc_node !== null) {
                    li.one('a').appendChild(desc_node);
                }
            }
            if (items[i].css_class !== undefined) {
                li.addClass(items[i].css_class);
            } else {
                li.addClass('unstyled');
            }
            display_items_list.appendChild(li);
        }

        this.setStdModContent(
            Y.WidgetStdMod.BODY, display_items_list, Y.WidgetStdMod.REPLACE);
        this.move(-10000, 0);
    },

    /**
     * Bind UI events
     * <p>
     * This method is invoked after bindUI is invoked for the Widget class
     * using YUI's aop infrastructure.
     * </p>
     *
     * @method _bindUIChoiceList
     * @protected
     */
    _bindUIChoiceList: function() {
        var display_items_list = this.get("display_items_list");
        var that = this;
        Y.delegate("click", function(e) {
            var target = e.currentTarget;
            var value = target._value;
            var items = that.get("items");
            var i;
            for (i = 0; i < items.length; i++) {
                if (items[i].value === value) {
                    that.fire("valueChosen", items[i].value);
                    that.destroy();
                    e.halt();
                    break;
                }
            }
        }, display_items_list, "li a");
    },

    /**
     * Destroy the widget (remove its HTML from the page)
     *
     * @method destructor
     */
    destructor: function() {
        var bb = this.get("boundingBox");
        var parent = bb.get("parentNode");
        if (parent) {
            parent.removeChild(bb);
        }
    },

    /**
     * Calculate correct position for popup and move it there.
     *
     * This is needed so that we have the correct height of the overlay,
     * with the content, when we position it. This solution is not very
     * elegant - in the future we'd like to be able to use YUI's positioning,
     * thought it doesn't seem to work correctly right now.
     *
     * @private
     * @method _positionCorrectly
     */
    _positionCorrectly: function(e) {
        var boundingBox = this.get('boundingBox');
        var client_width = document.body.clientWidth;
        var offset_width = boundingBox.get('offsetWidth');
        var selectedListItem = boundingBox.one('span.current');
        valueX = this._mouseX - (boundingBox.get('offsetWidth') / 2);
        var valueY;
        if (Y.Lang.isValue(selectedListItem)) {
            valueY = (this._mouseY -
                      this.get("headerContent").get('offsetHeight') -
                      selectedListItem.get('offsetTop') -
                      (selectedListItem.get('offsetHeight') / 2));
        } else {
             valueY = this._mouseY - (boundingBox.get('offsetHeight') / 2);
        }
        if (valueX > client_width - offset_width) {
            valueX = client_width - offset_width;
        }
        if (valueX < 0) {
            valueX = 0;
        }
        if (valueY < 0) {
            valueY = 0;
        }

        this.move(valueX, valueY);
        this.get('boundingBox').one('.close-button').focus();
    },

    /**
     * Return the absolute position of any node.
     *
     * @private
     * @method _findPosition
     */
    _findPosition: function(obj) {
        var curleft = 0,
        curtop = 0;
        if (obj.get("offsetParent")) {
            do {
                curleft += obj.get("offsetLeft");
                curtop += obj.get("offsetTop");
                obj = obj.get("offsetParent");
            } while (Y.Lang.isValue(obj));
        }
        return [curleft,curtop];
    }

});


Y.augment(ChoiceList, Y.Event.Target);
Y.ChoiceList = ChoiceList;


/**
 * This class provides a specialised implementation of ChoiceSource
 * displaying a custom UI for null items.
 *
 * @class NullChoiceSource
 * @extends ChoiceSource
 * @constructor
 */
var NullChoiceSource;
NullChoiceSource = function() {
    NullChoiceSource.superclass.constructor.apply(this, arguments);
};

NullChoiceSource.NAME = NULLCHOICESOURCE;

NullChoiceSource.HTML_PARSER = {
    value_location: '.' + C_VALUELOCATION,
    editicon: '.' + C_EDITICON,
    null_text_location: '.' + C_NULLTEXTLOCATION,
    addicon: '.' + C_ADDICON
};

NullChoiceSource.ATTRS = {
    null_text_location: {},
    addicon: {},
    /**
     * Action icon returns either the add icon or the edit icon, depending
     * on whether the currently selected value is null.
     *
     * @attribute actionicon
     */
    actionicon: {
        getter: function() {
            if (Y.Lang.isValue(this.get('value'))) {
                return this.get('editicon');
            } else {
                return this.get('addicon');
            }
          }
    },
    /**
     * The specialised version of the items attribute is cloned and the name
     * of the null value is modified to add a remove icon next to it. If the
     * currently selected value is null, the null item is not displayed.
     *
     * @attribute items
     */
    items: {
        value: [],
        getter: function(v) {
            if (!Y.Lang.isValue(this.get("value"))) {
                v = Y.Array.filter(v, function(item) {
                    return (Y.Lang.isValue(item.value));
                });
            }
            var i;
            for (i = 0; i < v.length; i++) {
                if (!Y.Lang.isValue(v[i].value) &&
                    v[i].name.indexOf('<img') === -1) {
                    // Only append the icon if the value for this item is
                    // null, and the img tag is not already found.
                    v[i].name = [
                        '<img src="https://launchpad.net/@@/remove" ',
                        '     style="margin-right: 0.5em; border: none; ',
                        '            vertical-align: middle" />',
                        '<span style="text-decoration: underline; ',
                        '             display: inline;',
                        '             color: green;">',
                        v[i].name,
                        '</span>'].join('');
                }
            }
            return v;
        },
        clone : "deep"
    }
};

Y.extend(NullChoiceSource, ChoiceSource, {
    initializer: function(cfg) {
        var addicon = this.get('addicon');
        addicon.original_src = addicon.get("src");
        var old_uiClearWaiting = this._uiClearWaiting;
        this._uiClearWaiting = function() {
            old_uiClearWaiting.call(this);
            if (Y.Lang.isValue(this.get('value'))) {
                this.get('null_text_location').setStyle('display', 'none');
                this.get('addicon').setStyle('display', 'none');
                this.get('value_location').setStyle('display', 'inline');
                this.get('editicon').setStyle('display', 'inline');
            } else {
                this.get('null_text_location').setStyle('display', 'inline');
                this.get('addicon').setStyle('display', 'inline');
                this.get('value_location').setStyle('display', 'none');
                this.get('editicon').setStyle('display', 'none');
            }
        };
    }
});

Y.NullChoiceSource = NullChoiceSource;

},"0.2", {
    "skinnable": true,
    "requires": [
        "oop", "event", "event-delegate", "node", "widget", "widget-position",
        "widget-stdmod", "overlay", "lp.ui.overlay", "lp.anim"]
});

