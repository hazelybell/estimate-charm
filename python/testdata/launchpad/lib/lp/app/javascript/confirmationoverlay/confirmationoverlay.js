/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

/* XXX: rvb 2011-08-30 bug=837447: This module should be moved to
 * a central place with the other overlays.
 * (lib/lp/app/javascript/overlay)
 */

YUI.add('lp.app.confirmationoverlay', function(Y) {

/**
 * Display a confirmation overlay before submitting a form.
 *
 * @module lp.app.confirmationoverlay
 */

var NAME = 'lp-app-confirmationoverlay';

/**
 * The ConfirmationOverlay class builds on the lp.ui.FormOverlay
 * class.  It 'wraps' itself around a button so that a confirmation
 * pop-up is displayed when the button is clicked to let the user
 * a chance to cancel the form submission.  Note that the button
 * can be simply 'disabled' if it's desirable to prevent the usage
 * of that button if the user's browser has no Javascript support.
 * It can also be used without providing a button to the constructor;
 * in this case, the caller is responsible for calling show() manually
 * and also providing a function to be called (submit_fn).
 *
 * @class ConfirmationOverlay
 * @namespace lp.app
 */
function ConfirmationOverlay(config) {
    ConfirmationOverlay.superclass.constructor.apply(this, arguments);
}

ConfirmationOverlay.NAME = NAME;

ConfirmationOverlay.ATTRS = {

    /**
     * An (optional) input button that should be 'guarded' by this
     * confirmation overlay.
     *
     * @attribute button
     * @type Node
     * @default null
     */
    button: {
        value: null
    },

    /**
     * The form that should be submitted once the confirmation has been
     * passed.
     *
     * @attribute submit_form
     * @type Node
     * @default null
     */
    submit_form: {
        value: null
    },

    /**
     * An (optional) callback function that should be called (instead
     * of submitting the form ) when the confirmation has been passed.
     *
     * @attribute submit_fn
     * @type Function
     * @default null
     */
    submit_fn: {
        value: null
    },

    /**
     * An optional function (must return a string or a Node) that will be run
     * to populate the form_content of the confirmation overlay when it's
     * displayed.  This is useful if the confirmation overlay must displayed
     * information that is only available at form submission time.
     *
     * @attribute form_content_fn
     * @type Function
     * @default null
     *
     */
    form_content_fn: {
        value: null
    },

    /**
     * An optional function (must return a string or a Node) that will be run
     * to populate the headerContent of the confirmation overlay when it's
     * displayed.  This is useful if the confirmation overlay must displayed
     * information that is only available at form submission time.
     *
     * @attribute header_content_fn
     * @type Function
     * @default null
     *
     */
    header_content_fn: {
        value: null
    },

    /**
     * An optional function (must return a boolean) that will be run to
     * before the confirmation overlay is shown to decide whether it
     * should really be displayed.
     *
     * @attribute display_confirmation_fn
     * @type Function
     * @default null
     *
     */
    display_confirmation_fn: {
        value: null
    },

    /**
     * The text to display on the OK button.
     *
     * @attribute submit_text
     * @type Function
     * @default 'OK'
     *
     */
    submit_text: {
        value: 'OK'
    },

    /**
     * The text to display on the Cancel button.
     *
     * @attribute cancel_text
     * @type Function
     * @default 'Cancel'
     *
     */
    cancel_text: {
        value: 'Cancel'
    }
};

Y.extend(ConfirmationOverlay, Y.lp.ui.FormOverlay, {

    initializer: function(cfg) {
        var submit_button = Y.Node.create(
            '<button type="submit" class="ok-btn" />')
            .set("text", this.get('submit_text'));
        var cancel_button = Y.Node.create(
            '<button type="button" class="cancel-btn" />')
            .set("text", this.get('cancel_text'));
        this.set('form_submit_button', submit_button);
        this.set('form_cancel_button', cancel_button);

        var self = this;
        var submit_fn = this.get('submit_fn');
        if (submit_fn === null) {
            // When ok is clicked, submit the form.
            var submit_form = function() {
                self._createHiddenDispatcher();
                self._submitForm();
            };
            this.set('form_submit_callback', submit_form);
        }
        else {
            // When ok is clicked, call submit_fn.
            var submit_form_fn = function() {
                self.hide();
                submit_fn();
            };
            this.set('form_submit_callback', submit_form_fn);
        }

        var button = this.get('button');
        if (Y.Lang.isValue(button)) {
            this.set('submit_form', this.get('button').ancestor('form'));

            // Enable the button if it's disabled.
            button.set('disabled', false);

            // Wire this._handleButtonClicked to the button.
            button.on('click', Y.bind(this._handleButtonClicked, this));
       }
       // Hide the overlay.
       this.hide();
    },

    /**
     * Submit the form (this is used after the user has clicked the 'ok'
     * button on the confirmation form.
     *
     * @method _submitForm
     */
    _submitForm: function() {
        // We can't use YUI's io-form here because we want the browser to
        // display the page returned by the POST's request.
        this.get('submit_form').submit();
    },

    /**
     * Update overlay's content and show the overlay.
     *
     * @method show
     *
     */
    show: function() {
        // Update the overlay's content.
        this._renderUIFormOverlay();
        this._fillContent();
        this._positionOverlay();
        this._setFormContent();
        // Render and display the overlay.
        this.render();
        ConfirmationOverlay.superclass.show.call(this);
    },

    /**
     * Prevent form submission and display the confirmation overlay.
     *
     * @method _handleButtonClicked
     */
     _handleButtonClicked: function(e) {
        var display_confirmation_fn = this.get('display_confirmation_fn');
        if (display_confirmation_fn === null || display_confirmation_fn()) {
            // Stop the event to prevent the form submission.
            e.preventDefault();
            this.show();
        }
    },

    /**
     * Update the header and the content of the overlay.
     *
     * @method _fillContent
     */
     _fillContent: function() {
        var form_content_fn = this.get('form_content_fn');
        if (form_content_fn !== null) {
            var content = form_content_fn();
            // Make sure that form_content is a string,
            // if it's a Y.Node, FormOverlay will append
            // it to the form content instead of replacing it.
            if (content instanceof Y.Node) {
                content = content.get('innerHTML');
            }
            this.set('form_content', content);
        }
        var header_content_fn = this.get('header_content_fn');
        if (header_content_fn !== null) {
            this.set('headerContent', header_content_fn());
        }
     },


    /**
     * Center the overlay in the viewport.
     *
     * @method  _positionOverlay
     */
     _positionOverlay: function() {
        this.set(
            'align',
            {points: [
              Y.WidgetPositionAlign.CC,
              Y.WidgetPositionAlign.CC]
            });
    },

    /**
     * Create a hidden input to simulate the click on the right
     * button.
     *
     * @method _createHiddenDispatcher
     */
    _createHiddenDispatcher: function() {
        var dispatcher = Y.Node.create('<input>')
            .set('type', 'hidden')
            .addClass('hidden-input')
            .set('name', this.get('button').get('name'))
            .set('value', this.get('button').get('value'));
        this.get('submit_form').append(dispatcher);
    }

});

var namespace = Y.namespace('lp.app.confirmationoverlay');
namespace.ConfirmationOverlay = ConfirmationOverlay;

}, "0.1", {"skinnable": true, "requires": ["lp.ui.formoverlay"]});
