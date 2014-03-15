/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.ui.activator', function(Y) {

var ACTIVATOR     = 'activator',

    // Local aliases
    getCN = Y.ClassNameManager.getClassName,

    // Templates.
    MESSAGE_HEADER_TEMPLATE = '<div></div>',
    MESSAGE_BODY_TEMPLATE = '<div></div>',
    MESSAGE_CLOSE_BUTTON_TEMPLATE = '<button>Close</button>',

    // Events.
    ACT           = 'act',

    // Class for hiding elements.
    C_HIDDEN      = getCN(ACTIVATOR, 'hidden'),

    // Classes identifying elements.
    C_ACT         = getCN(ACTIVATOR, 'act'),
    C_DATA_BOX    = getCN(ACTIVATOR, 'data-box'),
    C_MESSAGE_BOX = getCN(ACTIVATOR, 'message-box'),

    // Classes for internally created elements.
    C_MESSAGE_CLOSE  = getCN(ACTIVATOR, 'message-close'),
    C_MESSAGE_HEADER = getCN(ACTIVATOR, 'message-header'),
    C_MESSAGE_BODY   = getCN(ACTIVATOR, 'message-body'),

    // Classes indicating status.
    C_PROCESSING  = getCN(ACTIVATOR, 'processing'),
    C_CANCEL      = getCN(ACTIVATOR, 'cancellation'),
    C_SUCCESS     = getCN(ACTIVATOR, 'success'),
    C_FAILURE     = getCN(ACTIVATOR, 'failure'),

    ALL_STATUSES  = [C_SUCCESS, C_FAILURE, C_CANCEL, C_PROCESSING];

/**
 * The Activator widget will hook up an element to trigger an action,
 * and it will change the display to indicate whether the action
 * is processing, ended successfully, ended in error, or was cancelled.
 *
 * A CSS class is applied in each different state. Success and
 * failure also trigger a green or red flash animation.
 *
 * @class Activator
 * @constructor
 * @extends Widget
 */
var Activator = function() {
    Activator.superclass.constructor.apply(this, arguments);
};

Activator.NAME = ACTIVATOR;

Activator.ATTRS = {};

Y.extend(Activator, Y.Widget, {

    /**
     * Destination of status messages.
     *
     * @property message_box
     * @type Node
     */
    message_box: null,

    /**
     * Destination of new data. Useful when activating an editor.
     *
     * @property data_box
     * @type Node
     */
    data_box: null,

    /**
     * Element that triggers the event.
     *
     * @property action_element
     * @type Node
     */
    action_element: null,

    /**
     * Set the CSS class on the context box to indicate that the status is
     * either error, success, cancellation, or processing.
     *
     * @method _setStatusClass
     * @protected.
     */
    _setStatusClass: function(css_class) {
        Y.Array.each(ALL_STATUSES, function (old_class, i) {
            this.get('contentBox').removeClass(old_class);
        }, this);
        this.get('contentBox').addClass(css_class);
    },

    /**
     * Display message for either error, success, cancellation, or
     * processing.
     *
     * @method _renderMessage
     * @protected.
     */
    _renderMessage: function(title, message_node) {
        this.message_box.set('innerHTML', '');
        if (message_node === undefined) {
            this.message_box.addClass(C_HIDDEN);
        } else {
            this.message_box.removeClass(C_HIDDEN);

            // Close button
            var message_close_button = Y.Node.create(
                MESSAGE_CLOSE_BUTTON_TEMPLATE);
            message_close_button.addClass(C_MESSAGE_CLOSE);
            message_close_button.addClass('lazr-btn');

            message_close_button.on('click', function (e) {
                this.message_box.addClass(C_HIDDEN);
            }, this);

            // Header
            var message_header = Y.Node.create(MESSAGE_HEADER_TEMPLATE);
            message_header.appendChild(message_close_button);
            message_header.appendChild(Y.Node.create(title));
            message_header.addClass(C_MESSAGE_HEADER);

            // Body
            var message_body = Y.Node.create(
                MESSAGE_BODY_TEMPLATE);
            message_body.appendChild(message_node);
            message_body.addClass(C_MESSAGE_BODY);

            this.message_box.appendChild(message_header);
            this.message_box.appendChild(message_body);
        }
    },

    /**
     * Animate that the action occurred successfully, and overwrite the
     * contents of the element which has the C_DATA_BOX class.
     *
     * @method renderSuccess
     * @param {Node} data_node Optional parameter to update data. Normally
     *                         this would indicate editing a field.
     * @param {Node} message_node Optional parameter to display a message.
     * @protected
     */
    renderSuccess: function(data_node, message_node) {
        if (data_node !== undefined) {
            this.data_box.set('innerHTML', '');
            this.data_box.appendChild(data_node);
        }
        this._setStatusClass(C_SUCCESS);
        this._renderMessage('Message', message_node);
        var anim = Y.lp.anim.green_flash({node: this.animation_node});
        anim.run();
    },

    /**
     * Animate failure.
     *
     * @method renderFailure
     * @param {Node} Optional parameter to display a message.
     * @protected.
     */
    renderFailure: function(message_node) {
        this._renderMessage('Error', message_node);
        this._setStatusClass(C_FAILURE);
        var anim = Y.lp.anim.red_flash({node: this.animation_node});
        anim.run();
    },

    /**
     * Animate cancellation.
     *
     * @method renderCancellation
     * @param {Node} Optional parameter to display a message.
     * @protected.
     */
    renderCancellation: function(message_node) {
        this._renderMessage('Message', message_node);
        this._setStatusClass(C_CANCEL);
        var anim = Y.lp.anim.red_flash({node: this.animation_node});
        anim.run();
    },

    /**
     * Indicate that the action is processing. This is normally done
     * by configuring the C_PROCESSING class to display a spinning
     * animated GIF.
     *
     * @method renderProcessing
     * @param {Node} Optional parameter to display a message.
     * @protected.
     */
    renderProcessing: function(message_node) {
        this._renderMessage('Message', message_node);
        this._setStatusClass(C_PROCESSING);
    },

    /**
     * Initialize the widget.
     *
     * @method initializer
     * @protected
     */
    initializer: function(cfg) {
        this.publish(ACT);
        if (cfg === undefined || cfg.contentBox === undefined) {
            // We need the contentBox to be passed in the cfg,
            // although the init method is the one that actually copies
            // that cfg to the contentBox ATTR.
            throw new Error("Missing contentBox argument for Activator.");
        }
        this.message_box = this.get('contentBox').one('.' + C_MESSAGE_BOX);
        if (this.message_box === null) {
            throw new Error("Can't find element with CSS class " +
                C_MESSAGE_BOX + ".");
        }
        this.data_box = this.get('contentBox').one('.' + C_DATA_BOX);
        if (this.data_box === null) {
            throw new Error("Can't find element with CSS class " +
                C_DATA_BOX + ".");
        }
        this.action_element = this.get('contentBox').one('.' + C_ACT);
        if (this.action_element === null) {
            throw new Error("Can't find element with CSS class " +
                C_ACT + ".");
        }
        this.animation_node = cfg.animationNode;
        if (this.animation_node === undefined) {
            this.animation_node = this.get('contentBox');
        }
    },

    /**
     * Update the DOM structure and edit CSS classes.
     *
     * @method renderUI
     * @protected
     */
    renderUI: function() {
        // Just in case the user didn't assign the correct classes.
        this.action_element.removeClass(C_HIDDEN);
        // Use &thinsp; character to prevent IE7 from hiding the
        // yui3-activator-act button, when it just has a background-image
        // and no content in it or in the data_box.
        this.get('contentBox').prepend('&thinsp;');
    },

    /**
     * Set the event handler for the actor element.
     *
     * @method bindUI
     * @protected
     */
    bindUI: function() {
        var activator = this;
        Y.on('click', function(e) {
            activator.fire(ACT);
            e.preventDefault();
        }, this.action_element);
    },

    /**
     * UI syncing should all be handled by the status events.
     *
     * @method syncUI
     * @protected
     */
    syncUI: function() {
    }
});

Y.lp.ui.disableTabIndex(Activator);

Y.namespace('lp.ui.activator');
Y.lp.ui.activator.Activator = Activator;


}, "0.1", {"skinnable": true,
           "requires": ["oop", "event", "node", "widget",
                        "lp.anim", "lp.ui-base"]});
