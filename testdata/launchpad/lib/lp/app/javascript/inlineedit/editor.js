/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.ui.editor', function(Y) {

/**
 * Edit any on-screen text in-place.
 *
 * @module lp.ui.editor
 */

/**
 * This class provides the ability to turn a static HTML text field into
 * a form and text input on-demand.
 *
 * @class InlineEditor
 * @extends Widget
 * @constructor
 */

var EDITOR = 'ieditor',
    BOUNDING_BOX = 'boundingBox',
    CONTENT_BOX = 'contentBox',

    INPUT_EL = 'input_field',
    ERROR_MSG = 'error_message',

    HIDDEN = 'hidden',
    VALUE = 'value',
    INITIAL_VALUE_OVERRIDE = 'initial_value_override',
    SIZE = 'size',
    IN_ERROR = 'in_error',
    RENDERED = 'rendered',
    CLICK = 'click',
    ACCEPT_EMPTY = 'accept_empty',
    MULTILINE = 'multiline',
    MULTILINE_MIN_SIZE = 60,
    TRUNCATE_LINES = 'truncate_lines',
    ORIGINAL_ELLIPSIS_TEXT = 'ellipsis-original-text',

    TOP_BUTTONS = 'top_buttons',
    BOTTOM_BUTTONS = 'bottom_buttons',
    SUBMIT_BUTTON = 'submit_button',
    CANCEL_BUTTON = 'cancel_button',
    BUTTONS = 'buttons',
    B_TOP = 'top',
    B_BOTTOM = 'bottom',
    B_BOTH = 'both',
    LOADING = 'loading',

    createNode = Y.Node.create,
    getCN = Y.ClassNameManager.getClassName,

    C_INPUT = getCN(EDITOR, 'input'),
    C_SUBMIT = getCN(EDITOR, 'submit_button'),
    C_CANCEL = getCN(EDITOR, 'cancel_button'),
    C_BTNBOX = getCN(EDITOR, 'btns'),
    C_MULTILINE = getCN(EDITOR, 'multiline'),
    C_SINGLELINE = getCN(EDITOR, 'singleline'),
    C_WAITING = getCN(EDITOR, 'waiting'),
    C_ERROR = getCN(EDITOR, 'errors'),
    C_IN_ERROR = getCN(EDITOR, 'in-error'),
    C_ERROR_HIDDEN = getCN(EDITOR, 'errors', HIDDEN),

    SAVE = 'save',
    CANCEL = 'cancel',
    SHRINK = 'shrink';

// To strip the 'px' unit suffix off widget sizes.
var strip_px = /px$/;

var InlineEditor = function() {
    InlineEditor.superclass.constructor.apply(this, arguments);
};

InlineEditor.NAME = EDITOR;

/**
 * Static object hash used to capture existing markup for progressive
 * enhancement.
 *
 * @property InlineEditor.HTML_PARSER
 * @type Object
 * @static
 */
InlineEditor.HTML_PARSER = {
    error_message: '.' + C_ERROR
};

/**
 * Static html template to use for creating the 'Submit' button.
 *
 * @property InlineEditor.SUBMIT_TEMPLATE
 * @type string
 * @static
 */
InlineEditor.SUBMIT_TEMPLATE = Y.lp.ui.OK_BUTTON;

/**
 * Static html template to use for creating the 'Cancel' button.
 *
 * @property InlineEditor.CANCEL_TEMPLATE
 * @type string
 * @static
 */
InlineEditor.CANCEL_TEMPLATE = Y.lp.ui.CANCEL_BUTTON;

/**
 * Static html template to use for creating the editor's <input> field.
 *
 * @property InlineEditor.INPUT_TEMPLATE
 * @type string
 * @static
 */
InlineEditor.INPUT_TEMPLATE = '<textarea></textarea>';


InlineEditor.ATTRS = {
    /**
     * Determines if the editor will accept the empty string as a
     * valid value.
     *
     * @attribute accept_empty
     * @type boolean
     */
    accept_empty: {
        value: false
    },

    /**
     * Determines whether the editor will accept multiple lines of input.
     * Besides layout, this will affect what the enter key does: in
     * single-line mode it submits, in multi-line mode it inserts a
     * newline.
     *
     * @attribute multiline
     * @type boolean
     * @default false
     */
    multiline: {
        value: false
    },

    /**
     * Node that will serve as the user's input.
     *
     * @attribute input_field
     * @type Node
     * @default null
     */
    input_field: {
        value: null
    },

    /**
     * Y.Node representing the 'Submit' button.
     *
     * @attribute submit_button
     * @type Node
     * @default null
     */
    submit_button: {
        value: null,
        setter: function(v) {
            return this._setNode(v);
        }
    },

    /**
     * Y.Node that will be drawn as the 'Cancel' button.
     *
     * @attribute cancel_button
     * @type Node
     * @default null
     */
    cancel_button: {
        value: null,
        setter: function(v) { return this._setNode(v); }
    },

    /**
     * Y.Node for the bar holding the top buttons.
     *
     * @attribute top_buttons
     * @type Node
     * @default null
     */
    top_buttons: {
        value: null,
        setter: function(v) { return this._setNode(v); }
    },

    /**
     * Y.Node for the bar holding the bottom buttons.
     *
     * @attribute bottom_buttons
     * @type Node
     * @default null
     */
    bottom_buttons: {
        value: null,
        setter: function(v) { return this._setNode(v); }
    },

    /**
     * A node that will display any widget errors.
     *
     * @attribute error_message
     * @type Node
     */
    error_message: {
        value: null,
        setter: function(v) { return this._setNode(v); }
    },

    /**
     * The value of the widget's text input, and its value after saving.
     *
     * @attribute value
     * @type String
     * @default The empty string
     */
    value: {
        value: '',
        validator: function(v) {
            return v !== null;
        },
        getter: function(val) {
            return Y.Lang.trim(val);
        }
    },

    /**
     * When not null, this overrides the initial value for the <input>
     * field.  Otherwise, the initial value is taken from the widget's
     * <span> element.  The caller must provide this because when
     * accept_empty is true, the editor widget has no way to distinguish
     * whether a value of '' means that no value was given, or whether the
     * empty string is a valid user supplied value.
     */
    initial_value_override: {
        value: null
    },

    /**
     * Is the control currently displaying an error?
     *
     * @attribute in_error
     * @type Boolean
     * @default false
     */
    in_error: {
        value: false
    },

    /**
     * The editor's input field's width.  Accepts positive numbers for
     * approximate width in characters, or an HTML size specification
     * such as "120px."  The default value, null, will use the browser's
     * default size.
     *
     * CSS is generally a better way to set this, since it makes it
     * easier to line up the button boxes correctly.  But doing it this
     * way happens to be useful for testing.
     *
     * If you are creating a multi-line editor then using 'size' will lead
     * to some strange layout results.  You are better off specifying the
     * widget "width" attribute for such widgets.
     *
     * @attribute size
     * @default null
     */
    size: {
        value: null,
        validator: function(v) {
            return this._validateSize(v);
        }
    },

    /**
     * Determines which sets of buttons should be shown in multi-line
     * mode: "top", "bottom", or "both".
     *
     * @attribute buttons
     * @default "both"
     */
    buttons: {
        value: B_BOTH,
        validator: function(v) {
            return (v === B_TOP || v === B_BOTTOM || v === B_BOTH);
        }
    }
};

Y.extend(InlineEditor, Y.Widget, {

    /**
     * A convenience method for retrieving a Node value from a Node
     * instance, an HTMLElement, or a CSS string selector.
     *
     * @method _setNode
     * @param v {Node|String|HTMLElement} The node element or selector
     * @return {Node} The Node, if found.  null otherwise.
     */
    _setNode: function(v) {
        return v ? Y.one(v) : null;
    },

    /**
     * Validates a string, and displays any errors if there are problems
     * with it.
     *
     * @method validate
     * @param val {String} the input to validate
     * @return {Boolean} true if the input is ok.
     */
    validate: function(val) {
        if (!this.get(ACCEPT_EMPTY) && val === '') {
            this.showError("Empty input is unacceptable!");
            return false;
        }
        if (this.get(ACCEPT_EMPTY) && val === '') {
            return true;
        }
        return !!val;
    },

    /**
     * Save the editor's current input.  Validates the input, and, if it
     * is valid, clears any errors before calling _saveData().
     *
     * @method save
     */
    save: function() {
        // We don't want to save any whitespace characters.
        var input = Y.Lang.trim(this.getInput());

        if (this.validate(input)) {
            this.clearErrors();
            this._saveData(input);
        }
    },

    /**
     * The default save() operation.  Writes the input field's value to
     * the editor's 'value' attribute.  Fires the 'save' event after
     * everything is complete.
     *
     * This method will only be called if the editor's input has been
     * validated.
     *
     * @method _saveData
     * @param data {ANY} The data to be saved.
     * @protected
     */
    _saveData: function(data) {
        this.set(VALUE, data);
        this.fire(SAVE);
    },

    /**
     * Cancel an in-progress edit and reset the input's value by firing
     * the 'cancel' event.
     *
     * @method cancel
     */
    cancel: function() {
        this.fire(CANCEL);
    },


    /**
     * The default cancel() operation.  Resets the current input field.
     *
     * @method _defaultCancel
     * @param e {Event.Facade} An Event Facade object.
     * @protected
     */
    _defaultCancel: function(e) {
        this.reset();
    },

    /**
     * Reset the widget's current input to the control's
     * intial value.
     *
     * @method reset
     */
    reset: function() {
        this.setInput(this.get(VALUE));
        this.clearErrors();
    },

    /**
     * Focus the editor's INPUT field.
     *
     * @method focus
     */
    focus: function() {
        this.get(INPUT_EL).focus();
    },

    /**
     * Display an error message.
     *
     * @method showError
     * @param msg A string or HTMLElement to be displayed.
     */
    showError: function(msg) {
        this.hideLoadingSpinner();
        if (this.get(MULTILINE)) {
            Y.lp.app.errors.display_error(this.get(BOUNDING_BOX), msg);
        } else {
            this.get(ERROR_MSG).set('innerHTML', msg);
        }
        this.set(IN_ERROR, true);
        this.get(INPUT_EL).focus();
    },

    /**
     * Clear the currently displayed error message.
     *
     * @method clearErrors
     */
    clearErrors: function() {
        this.set(IN_ERROR, false);
    },

    /**
     * Is the widget currently displaying an error?
     *
     * @method hasErrors
     * @return Boolean
     */
    hasErrors: function() {
        return this.get(IN_ERROR);
    },

    /**
     * Constructor logic.
     *
     * @method initializer
     * @protected
     */
    initializer: function(cfg) {
        /**
         * Fires when the user presses the 'Submit' button.
         *
         * @event saveEdit
         */
        this.publish(SAVE);

        /**
         * Fires when the user presses the 'Cancel' button.
         *
         * @event cancelEdit
         * @preventable _defaultCancel
         */
        this.publish(CANCEL, { defaultFn: this._defaultCancel });

        /**
         * Store the cfg so we can pass things to composed elements like
         * the ResizingTextarea. In this way we can change settings of
         * that plugin while creating and dealing with this widget
         */
        this.cfg = Y.Lang.isUndefined(cfg) ? {} : cfg;
    },

    _removeElement: function(content_box, element) {
        if (element) {
            content_box.removeChild(element);
        }
    },

    /**
     * Clean up object references and event listeners.
     *
     * @method destructor
     * @private
     */
    destructor: function() {
        var box = this.get(CONTENT_BOX);
        this._removeElement(box, this.get(ERROR_MSG));
        this._removeElement(box, this.get(TOP_BUTTONS));
        this._removeElement(box, this.get(BOTTOM_BUTTONS));
    },

    /**
     * Create a box to hold the OK and Cancel buttons in single-line edit
     * mode.
     *
     * @method _renderSingleLineButtons
     * @protected
     * @param parent {Node} The parent node that will hold the buttons.
     */
    _renderSingleLineButtons: function(parent) {
        var button_box = createNode('<span></span>')
            .addClass(C_BTNBOX);
        this._renderOKCancel(button_box);
        parent.appendChild(button_box);
        this.set(BOTTOM_BUTTONS, button_box);
    },

    /**
     * Create a box to hold the OK and Cancel buttons around the top of a
     * multi-line editor.
     *
     * @method _renderTopButtons
     * @protected
     * @param parent {Node} The parent node that will hold the buttons.
     */
    _renderTopButtons: function(parent) {
        var button_bar = createNode('<div></div>')
            .addClass(C_BTNBOX);

        // Firefox needs a text node in order to calculate the line-height
        // and thus vertically center the buttons in the div.
        // Apparently it can't use the button elements themselves to
        // do this.
        var label = button_bar.appendChild(
            createNode('<div class="bg-top-label">&nbsp;</div>')
        );

        this._renderOKCancel(label);
        parent.appendChild(button_bar);
        this.set(TOP_BUTTONS, button_bar);
    },

    /**
     * Create a box to hold the OK and Cancel buttons around the bottom of
     * a multi-line editor.
     *
     * @method _renderBottomButtons
     * @protected
     * @param parent {Node} The parent node that will hold the buttons.
     */
    _renderBottomButtons: function(parent) {
        var button_bar = createNode('<div></div>')
            .addClass(C_BTNBOX);

        // Firefox needs a text node in order to calculate the line-height
        // and thus vertically center the buttons in the div.
        // Apparently it can't use the button elements themselves to
        // do this.
        var label = button_bar.appendChild(
            createNode('<div class="bg-bottom-label">&nbsp</div>')
        );

        this._renderOKCancel(label);
        parent.appendChild(button_bar);
        this.set(BOTTOM_BUTTONS,  button_bar);
    },

    /**
     * Render the OK and Cancel button pair.
     *
     * @method _renderOKCancel
     * @protected
     * @param parent {Node} The parent node that the buttons should be
     * appended to.
     */
    _renderOKCancel: function(parent) {
        var ok = createNode(InlineEditor.SUBMIT_TEMPLATE)
                .addClass(C_SUBMIT);
        var cancel = createNode(InlineEditor.CANCEL_TEMPLATE)
                .addClass(C_CANCEL);
        parent.appendChild(cancel);
        parent.appendChild(ok);
        this.set(SUBMIT_BUTTON, ok);
        this.set(CANCEL_BUTTON, cancel);
    },

    /**
     * Create the widget's HTML components.
     *
     * @method render
     * @protected
     */
    renderUI: function() {
        var bounding_box = this.get(BOUNDING_BOX);
        var content = this.get(CONTENT_BOX);
        var multiline = this.get(MULTILINE);
        var buttons;
        if (multiline) {
            buttons = this.get(BUTTONS);
        }

        if (multiline) {
            if (buttons === B_TOP || buttons === B_BOTH) {
                this._renderTopButtons(content);
            }
        }

        this._initInput();

        if (multiline) {
            if (buttons === B_BOTTOM || buttons === B_BOTH) {
                this._renderBottomButtons(content);
            }

            bounding_box.addClass(C_MULTILINE);
        } else {
            this._renderSingleLineButtons(content);
            bounding_box.addClass(C_SINGLELINE);
        }

        this._initErrorMsg();
    },

    _makeInputBox: function() {
        var box = createNode(InlineEditor.INPUT_TEMPLATE),
            size = this.get(SIZE);

        if (size) {
            if (Y.Lang.isNumber(size)) {
                size = size + 'px';
            }
            box.setStyle('width', size);
        }
        box.setStyle('overflow', HIDDEN);

        if (this.get(MULTILINE)) {
            // add the box inside of a container we'll use to limit the width
            // of the textarea contained within
            var limit_width_div = createNode('<div/>');
            limit_width_div.appendChild(box);
            limit_width_div.addClass(C_INPUT);

            this.get(CONTENT_BOX).appendChild(limit_width_div);
            // we also want an event so that whenever anyone clicks on our
            // div, we give focus to the textarea inside of us
            limit_width_div.on('click', function (e) {
                box.focus();
            });
        } else {
            this.get(CONTENT_BOX).appendChild(box);
        }
        return box;
    },

    /**
     * Create the editor's <input> field if necessary, assign classes
     * to it, and append it to the editor's contentBox.
     *
     * @method _initInput
     * @protected
     */
    _initInput: function() {
        if (!this.get(INPUT_EL)) {
            this.set(INPUT_EL, this._makeInputBox());
        }
    },

    /**
     * Create the error message field if it was not discovered by the
     * HTML_PARSER.
     *
     * @method _initErrorMsg
     * @protected
     */
    _initErrorMsg: function() {
        var cb = this.get(CONTENT_BOX),
            msg = this.get(ERROR_MSG);

        if (!msg) {
            msg = cb.appendChild(createNode('<div/>'));
            this.set(ERROR_MSG, msg);
        } else if (!cb.contains(msg)) {
            cb.appendChild(msg);
        }
        msg.addClass(C_ERROR);
        msg.addClass(C_ERROR_HIDDEN);
    },

    showLoadingSpinner: function(e) {
        // The multi-line editor submit icon should change to a spinner.
        if (this.get(MULTILINE)) {
            this.get(TOP_BUTTONS).one('.' + C_SUBMIT).setStyle(
                'display', 'none'
            );
            this.get(TOP_BUTTONS).one('.' + C_CANCEL).setStyle(
                'display', 'none'
            );
            var span = Y.Node.create('<span></span>');
            span.addClass(LOADING);
            e.target.get('parentNode').appendChild(span);
        }
    },

    hideLoadingSpinner: function() {
        // Remove the spinner from the multi-line editor.
        if (this.get(MULTILINE)) {
            var spinner = this.get(TOP_BUTTONS).one('.' + LOADING);
            if (spinner) {
                var parent = spinner.get('parentNode');
                parent.removeChild(spinner);
                this.get(TOP_BUTTONS).one('.' + C_SUBMIT).setStyle(
                    'display', 'inline');
                this.get(TOP_BUTTONS).one('.' + C_CANCEL).setStyle(
                    'display', 'inline');
            }
        }
    },

    /**
     * Bind the widget's DOM elements to their event handlers.
     *
     * @method bindUI
     * @protected
     */
    bindUI: function() {
        this.after('in_errorChange', this._afterInErrorChange);

        this._bindButtons(C_SUBMIT, function(e) {
            e.preventDefault();
            this.showLoadingSpinner(e);
            this.save();
        });
        this._bindButtons(C_CANCEL, function(e) {
            e.preventDefault();
            this.cancel();
        });

        // hook up the resizing textarea to handle those changes
        var cfg = this.cfg;
        var input = this.get(INPUT_EL);
        var that = this;

        if (!this.get(MULTILINE)) {
            // if this is not a multi-line, make sure it starts out as a
            // nice single row textarea then
            cfg.single_line = true;

            // 'down:13' is the decimal value of the Firefox DOM_VK_RETURN
            // symbol or U+000D.
            // https://developer.mozilla.org/en/DOM/Event/UIEvent/KeyEvent
            Y.on('key', this.save, this.get(INPUT_EL), 'down:13', this);
        } else {
            cfg.min_height = MULTILINE_MIN_SIZE;
            // we really really don't want scroll bars. So we'll try to avoid
            // them as much as possible. After 2000 lines, we see how it
            // appears in practice.
            cfg.max_height = 2000;
        }

        this.get(INPUT_EL).plug(
            Y.lp.app.formwidgets.ResizingTextarea,
            cfg
        );

        // we also need to make sure we update the ResizingTextarea as we
        // show/hide so bind to the show event (changes to the visible ATTR)
        this.after('visibleChange', function (e) {
            var input_node = e.target.get(INPUT_EL);

            if (that.get(MULTILINE)) {
                // The multi-line editor has to dynamically resize,
                // in case the widget is fluid to fit the container which is
                // relative positioned - pixels
                var box_width = that.get(BOUNDING_BOX).get('offsetWidth');
                var new_width = box_width - 29;
                var limit_width_div = input_node.get('parentNode');
                limit_width_div.setStyle('width', new_width + 'px');
            }

            input_node.resizing_textarea.resize();
        });

        // 'down:27' is the decimal value of the Firefox DOM_VK_ESCAPE
        // symbol or U+001B.
        Y.on('key', this.cancel, this.get(INPUT_EL), 'down:27', this);
    },

    _bindButtons: function(button_class, method) {
        var box = this.get(CONTENT_BOX);
        box.all('.' + button_class).on(CLICK, Y.bind(method, this));
    },

    /**
     * Render the control's value to the INPUT control.  Normally, this is
     * taken from the `value` attribute, which gets initialized from the
     * read-only element, but this can be overridden by providing
     * `initial_value_override` when constructing the widget.  To sync the
     * value to the HTML DOM, call {syncHTML}.
     *
     * @method syncUI
     * @protected
     */
    syncUI: function() {
        var value = this.get(INITIAL_VALUE_OVERRIDE);
        if (value === null || value === undefined) {
            value = this.get(VALUE);
        }
        if (value !== null && value !== undefined) {
            this.setInput(value);
        }
    },

    /**
     * A convenience method to fetch the control's input Element.
     */
    getInput: function() {
        return this.get(INPUT_EL).get(VALUE);
    },

    /**
     * Override current input area contents.  Will also update size, but
     * not animate.
     *
     * @method setInput
     * @param value New text to set as input box contents.
     */
    setInput: function(value) {
        this.get(INPUT_EL).set(VALUE, value);

        // we don't handle size updates, but the ResizingTextarea does.
        // Normally, an event is caught on the change of the input, but if
        // we programatically set the input, it won't always catch
        this.get(INPUT_EL).resizing_textarea._run_change(value);
    },

    /**
     * Hook to run after the 'in_error' attribute has changed.  Calls
     * hooks to hide or show the UI's error message using
     * _uiShowErrorMsg().
     *
     * @method _afterInErrorChange
     * @param e {Event.Facade} An attribute change event instance.
     * @protected
     */
    _afterInErrorChange: function(e) {
        this._uiShowErrorMsg(e.newVal);
    },

    /**
     * Show or hide the error message element.
     *
     * @method _uiShowErrorMsg
     * @param show {Boolean} whether the error message should be shown
     * or hidden.
     * @protected
     */
    _uiShowErrorMsg: function(show) {
        var emsg = this.get(ERROR_MSG),
            cb   = this.get(CONTENT_BOX);

        if (show) {
            emsg.removeClass(C_ERROR_HIDDEN);
            cb.addClass(C_IN_ERROR);
        } else {
            emsg.addClass(C_ERROR_HIDDEN);
            cb.removeClass(C_IN_ERROR);
        }
    },

    /**
     * Set the 'waiting' user-interface state.  Be sure to call
     * _uiClearWaiting() when you are done.
     *
     * @method _uiSetWaiting
     * @protected
     */
    _uiSetWaiting: function() {
        this.get(INPUT_EL).set('disabled', true);
        this.get(BOUNDING_BOX).addClass(C_WAITING);

    },

    /**
     * Clear the 'waiting' user-interface state.
     *
     * @method _uiClearWaiting
     * @protected
     */
    _uiClearWaiting: function() {
        this.get(INPUT_EL).set('disabled', false);
        this.get(BOUNDING_BOX).removeClass(C_WAITING);
    },

    /**
     * Validate the 'size' attribute.  Can be a positive number, or null.
     *
     * @method _validateSize
     * @param val {ANY} the value to validate
     * @protected
     */
    _validateSize: function(val) {
        if (Y.Lang.isNumber(val)) {
            return (val >= 0);
        }
        return (val === null);
    }

});

Y.lp.ui.disableTabIndex(InlineEditor);

Y.InlineEditor = InlineEditor;


var ETEXT         = 'editable_text',
    TEXT          = 'text',
    TRIGGER       = 'trigger',

    C_TEXT        = getCN(ETEXT, TEXT),
    C_TRIGGER     = getCN(ETEXT, TRIGGER),
    C_EDIT_MODE   = getCN(ETEXT, 'edit_mode');

/**
 * The EditableText widget will let a user edit any string of DOM text.
 * The DOM node containing the text must also have a clickable element
 * that will activate the editor.
 *
 * @class EditableText
 * @constructor
 * @extends Widget
 */
var EditableText = function() {
    EditableText.superclass.constructor.apply(this, arguments);
};

EditableText.NAME = ETEXT;

EditableText.ATTRS = {
    /**
     * A clickable node that will display the text-editing widget. Can be
     * set using a CSS selector, Node instance, or HTMLElement.
     *
     * @attribute trigger
     * @type Node
     */
    trigger: {
        setter: function(node) {
            if (this.get(RENDERED)) {
                this._bindTrigger(node);
            }
            return node;
        }
    },

    /**
     * The text to be updated by the editor's value.  Can be
     * set using a CSS selector, Node instance, or HTMLElement.
     *
     * @attribute text
     * @type Node
     */
    text: {
        setter: function(v) {
            return Y.Node.one(v);
        },
        validator: function(v) {
            return Y.Node.one(v);
        }
    },

    /**
     * The editable text's current value.  Returns a normalized text
     * string.
     *
     * If this is a DOM node of <p> tags, turn the node into a string
     * with \n\n marking <p> breaks.
     *
     * @attribute value
     * @type String
     * @readOnly
     */
    value: {
        getter: function() {
            var text_node = this.get(TEXT);
            var ptags = text_node.all('p');
            if (Y.Lang.isValue(ptags) && ptags.size()) {
                var lines = [];
                ptags.each(function(ptag) {
                    lines = lines.concat([ptag.get('text'), '\n\n']);
                });
                var content = lines.join("");
                // Remove trailing whitespace.
                return content.replace(/\s+$/,'');
            } else {
                // Long lines may have been truncated with an ellipsis so we
                // may need to get the original untruncated text.
                var text = text_node.getData(ORIGINAL_ELLIPSIS_TEXT);
                if (!Y.Lang.isString(text)) {
                    text = text_node.get('text');
                }
                return Y.Lang.trim(text);
            }
        },
        readOnly: true
    },

    /**
     * Flag determining if the editor accepts empty input.
     *
     * @attribute accept_empty
     * @type Boolean
     * @default false
     */
    accept_empty: {
        value: false,
        getter: function() {
            if (this.editor) {
                return this.editor.get(ACCEPT_EMPTY);
            }
        }
    },

    /**
     * Determines the maximum number of lines to display before the text is
     * truncated with an ellipsis. 0 means no truncation.
     *
     * @attribute truncate_lines
     * @default 0
     */
    truncate_lines: {
        value: 0,
        validator: function(value) {
            return Y.Lang.isNumber(value) && value >= 0;
        }
    }
};

/**
 * Static object hash used to capture existing markup for progressive
 * enhancement.  Can discover the 'trigger' and 'text' nodes.
 *
 * @property EditableText.HTML_PARSER
 * @type Object
 * @static
 */
EditableText.HTML_PARSER = {
    trigger: '.' + C_TRIGGER,
    text   : '.' + C_TEXT
};

Y.extend(EditableText, Y.Widget, {

    /**
     * Handle to the trigger's click event listener.
     *
     * @property _click_handler
     * @type Event.Handle
     * @protected
     */
    _click_handler: null,

    /**
     * The inline editor widget instance that will be used to display the
     * text.
     *
     * @property editor
     * @type InlineEditor
     */
    editor: null,

    /**
     * The inline editor's bounding box node.
     *
     * @property _editor_bb
     * @type Node
     * @protected
     */
    _editor_bb: null,

    /**
     * Handle trigger click events.  Displays the editor widget.
     *
     * @method _triggerEdit
     * @param e {Event} Click event facade.
     * @protected
     */
    _triggerEdit: function(e) {
        e.preventDefault();
        this.show_editor();
        var cancel = this._editor_bb.one('.' + C_CANCEL);
        var anim = new Y.Anim({
            node: cancel,
            easing: Y.Easing.easeOut,
            duration: 0.2,
            from: { left: 0 },
            to: { left: -7 }
        });
        var self = this;
        anim.on('end', function(e) {
            self.editor.focus();
        });
        anim.run();
    },

    /**
     * Displays the inline editor component, calling {render} if
     * necessary.  Replaces the current {contentBox} with the widget
     * contents.
     *
     * @method show_editor
     */
    show_editor: function() {
        // Make sure that the cancel button starts back under the edit.
        var bounding_box = this.get(BOUNDING_BOX);
        bounding_box.one('.' + C_CANCEL).setStyle('left', 0);
        bounding_box.addClass(C_EDIT_MODE);
        this.editor.set(VALUE, this.get(VALUE));
        this.editor.syncUI();
        this.editor.show();
        this.editor.focus();
    },

    /**
     * Hide the editor component, and display the static
     * text.
     *
     * @method hide_editor
     */
    hide_editor: function() {
        var box = this.get(BOUNDING_BOX);
        box.removeClass(C_EDIT_MODE);
        this.editor.hide();
    },

    /**
     * Animate new text being saved by the editor.
     *
     * @method _uiAnimateSave
     * @protected
     */
    _uiAnimateSave: function() {
        this._uiAnimateFlash(Y.lp.anim.green_flash);
    },

    /**
     * Animate the user canceling an in-progress edit.
     *
     * @method _uiAnimateCancel
     * @protected.
     */
    _uiAnimateCancel: function() {
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
        var anim = flash_fn({ node: this.get(TEXT) });
        anim.run();
    },

    /**
     * If truncate_lines has been set, show an ellipsis for long text which
     * overflows the allowed number of lines.
     * @private
     */
    _showEllipsis: function() {
        var truncate_lines = this.get(TRUNCATE_LINES);
        if (truncate_lines > 0) {
            var text = this.get(TEXT);
            text.ellipsis({lines: truncate_lines});
        }
    },

    /**
     * Initialize the widget.  If an InlineEditor widget hasn't been
     * supplied, it will construct one first, and configure the editor
     * to appear in the appropriate DOM position.  Renders the editor
     * widget, sets it's initial visibility, and adds attribute event
     * listeners.
     *
     * @method initializer
     * @protected
     */
    initializer: function(cfg) {
        this.editor = cfg.editor ? cfg.editor : this._makeEditor(cfg);
        this.editor.hide();
        // Make sure the editor appears as a child of our contentBox.
        this.editor.render(this.get(CONTENT_BOX));

        // We want to publish the same events that the editor itself
        // does.
        this.editor.addTarget(this);

        // Map the 'accept_empty' attribute through to the underlying
        // editor.
        this.on('accept_emptyChange', this._afterAcceptEmptyChange);

        // We might want to cancel the render event, depending on the
        // user's browser.
        this.on('render', this._onRender);

        // Set up the callback to truncate the displayed text if necessary.
        var that = this;
        Y.on('domready', function() {
            that._showEllipsis();
            });
        Y.on('windowresize', function () {
            that._showEllipsis();
        });
    },

    /**
     * Destroy the inline editor widget, and remove the DOM nodes
     * created by it.
     *
     * @method destructor
     * @protected
     */
    destructor: function() {
        if (this._click_handler) {
            this._click_handler.detach();
        }

        this.editor.destroy();

        var bb = this._editor_bb;
        if (bb && Y.Node.getDOMNode(bb)) {
            var parentNode = bb.get('parentNode');
            if (parentNode && Y.Node.getDOMNode(parentNode)) {
                parentNode.removeChild(bb);
            }
        }
    },

    /**
     * Check if we want to prevent the render event from firing for
     * Launchpad B-Grade browsers (Konqueror with KHTML).
     *
     * @method _onRender
     * @param e {Event.Facade} The event object.
     * @protected
     */
    _onRender: function(e) {
        // The webkit UA property will be set to the value '1' if the
        // browser uses the KHTML engine.
        //
        // See
        // http://developer.yahoo.com/yui/3/api/UA.html#property_webkit
        if (Y.UA.webkit === 1) {
            // Our editor is really broken in KHTML, so just prevent the
            // render event from firing and modifying the DOM.  This
            // effectively shuts down the widget.  See bug #331584.
            e.preventDefault();
        }
    },

    /**
     * Create an inline editor instance if one wasn't supplied by the
     * user. Saves the editor's bounding box so that it can be removed
     * later.
     *
     * @method _makeEditor
     * @param cfg {Object} The current user configuration, usually
     * supplied to the initializer function.
     * @protected
     */
    _makeEditor: function(cfg) {
        var editor_cfg = Y.merge(cfg, {
            value: this.get(VALUE)
        });

        // We don't want these to be inherited from our own constructor
        // arguments.
        delete editor_cfg.boundingBox;
        delete editor_cfg.contentBox;

        var editor = new InlineEditor(editor_cfg);
        // Save the bounding box so we can remove it later.
        this._editor_bb = editor.get(BOUNDING_BOX);

        return editor;
    },

    /**
     * Create the editor's DOM structure, and assign the appropriate CSS
     * classes.
     *
     * @method renderUI
     * @protected
     */
    renderUI: function() {
        // Just in case the user didn't assign the correct classes.
        this.get(TEXT).addClass(C_TEXT);
        this.get(TRIGGER).addClass(C_TRIGGER);
    },

    /**
     * Subscribe to UI events generated by the inline editor widget.
     *
     * @method bindUI
     * @protected
     */
    bindUI: function() {
        // XXX: mars 2008-12-19
        // I should be able to use this.after('editor:save') here, but
        // the event model is broken: the listener will fire *before*
        // the editor's event listener finishes, and *before* the
        // editor's 'value' attribute has been set!
        //
        // For now, we'll just use editor.after() directly.
        this.editor.after('ieditor:save', this._afterSave, this);
        this.after('ieditor:cancel', this._afterCancel);

        this._bindTrigger(this.get(TRIGGER));

        // Multi-line editors display a frame on mouseover.
        if (this.editor.get(MULTILINE)) {
            var trigger = this.get(TRIGGER);
            var edit_controls = trigger.get('parentNode');
            if (Y.Lang.isValue(edit_controls)) {
                var edit_text = this.get(TEXT);
                var control_hover_class = 'edit-controls-hover';
                var text_hover_class = C_TEXT + '-hover';
                edit_controls.on('mouseover', function(e) {
                    edit_controls.addClass(control_hover_class);
                    edit_text.addClass(text_hover_class);
                });
                edit_controls.on('mouseout', function(e) {
                    edit_controls.removeClass(control_hover_class);
                    edit_text.removeClass(text_hover_class);
                });
            }
        }
    },

    /**
     * If the widget has been rendered, set the editable text's value to
     * the value of the inline editor widget.
     *
     * @method syncUI
     * @protected
     */
    syncUI: function() {
        // We only want to grab the editor's current value if we've
        // finished our own rendering phase.
        if (this.get(RENDERED)) {
            var text = this.get(TEXT),
                val  = this.editor.get(VALUE);
            text.setData(ORIGINAL_ELLIPSIS_TEXT, val);
            text.set('innerHTML', '');
            if (this.editor.get(MULTILINE)) {
                text.set('innerHTML', val);
            } else {
                text.appendChild(document.createTextNode(val));
            }
        }
        this.fire('rendered');
    },

    /**
     * Bind the inline editor trigger element.
     *
     * @method _bindTrigger
     * @param node {Node} The node instance to bind to.
     * @protected
     */
    _bindTrigger: function(node) {
        // Clean up the existing handler, to prevent event listener leaks.
        if (this._click_handler) {
            this._click_handler.detach();
        }
        this._click_handler = node.on('click', this._triggerEdit, this);
    },


    /**
     * Function to run after the user clicks 'save' on the inline editor.
     * Syncs the UI, hides the editor, and animates a successful text
     * change.  This also resets the initial_value_override so that we do
     * not continue to override the value when syncUI is called.
     *
     * @method _afterSave
     * @param e {Event.Custom} The editor widget's "save" event.
     * @protected
     */
    _afterSave: function(e) {
        this.editor.hideLoadingSpinner();
        this.syncUI();
        this.hide_editor();
        this._showEllipsis();
        this._uiAnimateSave();
        this.editor.set(INITIAL_VALUE_OVERRIDE, null);
    },

    /**
     * Function to run after the user clicks 'Cancel' on the editor
     * widget.  Hides the editor, and animates a cancelled edit.
     *
     * @method _afterCancel
     * @param e {Event.Custom} The editor's "cancel" event.
     * @protected
     */
    _afterCancel: function(e) {
        this.hide_editor();
        this._uiAnimateCancel();
    },

    /**
     * Pass through changes to the 'accept_empty' attribute to the editor
     * widget.
     *
     * @method _afterAcceptEmptyChange
     * @param e {Event} Change event for the 'accept_empty' attribute.
     * @protected
     */
    _afterAcceptEmptyChange: function(e) {
        this.editor.set(ACCEPT_EMPTY, e.newVal);
    },

    /**
     * Override to disable the widget for certain browsers.
     * See the YUI docs on `renderer` for widgets for more.
     *
     * @method renderer
     */
    renderer: function() {
        EditableText.superclass.renderer.apply(this, arguments);
    }
});

Y.lp.ui.disableTabIndex(EditableText);

Y.EditableText = EditableText;

}, "0.2", {"skinnable": true,
           "requires": ["oop", "anim", "event", "node", "widget",
                        "lp.anim", "lp.ui-base", "lp.app.errors",
                        "lp.app.formwidgets.resizing_textarea",
                        "lp.app.ellipsis"]});
