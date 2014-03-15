/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

/* XXX: rvb 2011-08-30 bug=837447: This module should be moved to
 * a central place with the other overlays.
 * (lib/lp/app/javascript/overlay)
 */

YUI.add('lp.ui.formoverlay', function(Y) {

/**
 * Display a functioning form in an overlay.
 *
 * @module lp.ui.formoverlay
 */


var ns = Y.namespace("lp.ui");
var getCN = Y.ClassNameManager.getClassName,
    NAME = 'lazr-formoverlay',
    CONTENT_BOX  = 'contentBox',
    RENDERUI = "renderUI",
    BINDUI = "bindUI";

   /**
    * The FormOverlay class builds on the lp.ui.PrettyOverlay class
    * to display form content and extract form data for the callsite.
    *
    * @class FormOverlay
    * @namespace lp.ui
    */
function FormOverlay(config) {
    FormOverlay.superclass.constructor.apply(this, arguments);

    Y.after(this._renderUIFormOverlay, this, RENDERUI);
    Y.after(this._bindUIFormOverlay, this, BINDUI);
    Y.after(this._bindDestroyOnHide, this, BINDUI);

}

FormOverlay.NAME = NAME;

/**
 * Static string that will be used for class of the form header.
 *
 * @property FormOverlay.C_FORM_HEADER
 * @type string
 * @static
 */
FormOverlay.C_FORM_HEADER = getCN(NAME, 'form-header');

/**
 * Static string that will be used for class of the form.
 *
 * @property FormOverlay.C_FORM
 * @type string
 * @static
 */
FormOverlay.C_FORM = getCN(NAME, 'form');

/**
 * Static string that will be used for class of the cancel button.
 *
 * @property FormOverlay.C_CANCEL
 * @type string
 * @static
 */
FormOverlay.C_CANCEL = getCN(NAME, 'cancel');

/**
 * Static string that will be used for class of the error container.
 *
 * @property FormOverlay.C_ERRORS
 * @type string
 * @static
 */
FormOverlay.C_ERRORS = getCN(NAME, 'errors');

/**
 * Static string that will be the class of the container for form buttons.
 *
 * @property FormOverlay.C_ACTIONS
 * @type string
 * @static
 */
FormOverlay.C_ACTIONS = getCN(NAME, 'actions');

/**
 * Static html template to contain the form header.
 *
 * @property FormOverlay.FORM_TEMPLATE
 * @type string
 * @static
 */
FormOverlay.FORM_HEADER_TEMPLATE =
    '<div class="' + FormOverlay.C_FORM_HEADER + '" />';

/**
 * Static html template to use for creating the form element.
 *
 * @property FormOverlay.FORM_TEMPLATE
 * @type string
 * @static
 */
FormOverlay.FORM_TEMPLATE = '<form class="' + FormOverlay.C_FORM + '" />';

/**
 * Static html template to use for creating the form's default submit button.
 *
 * @property FormOverlay.SUBMIT_TEMPLATE
 * @type string
 * @static
 */
FormOverlay.SUBMIT_TEMPLATE = '<input type="submit" value="Submit" />';

/**
 * Static html template to use for creating the form's default cancel button.
 *
 * @property FormOverlay.CANCEL_TEMPLATE
 * @type string
 * @static
 */
FormOverlay.CANCEL_TEMPLATE = '<button type="button"' +
    'class="' + FormOverlay.C_CANCEL + '">Cancel</button>';


/**
 * Static html template used for creating the error element.
 *
 * @property FormOverlay.ERROR_TEMPLATE
 * @type string
 * @static
 */
FormOverlay.ERROR_TEMPLATE =
    '<div class="' + FormOverlay.C_ERRORS + '" />';

FormOverlay.ATTRS = {

    /**
     * The innerHTML for the form header as a string.
     *
     * @attribute form_header
     * @type string
     * @default ''
     */
    form_header: {
        value: ''
    },

    /**
     * The innerHTML for the form as a string.
     *
     * @attribute form_content
     * @type string
     * @default ''
     */
    form_content: {
        value: ''
    },

    /**
     * The node representing the form's submit button.
     *
     * @attribute form_submit_button
     * @type Node
     * @default.null (Render will construct a submit button if none
     * is provided.)
     */
    form_submit_button: {
        value: null
    },

    /**
     * The node representing the form's cancel button.
     *
     * @attribute form_cancel_button
     * @type Node
     * @default.null (Render will construct a cancel button if none
     * is provided.)
     */
    form_cancel_button: {
        value: null
    },

    /**
     * The callback function that should be called when the form is
     * submitted.
     *
     * @attribute form_submit_callback.
     * @type function
     * @default null.
     */
    form_submit_callback: {
        value: null
    },

    /**
     * The object that provides the io function for doing XHR requests.
     *
     * @attribute io_provider
     * @type object
     * @default Y
     */
    io_provider: {
        value: Y
    },

    /**
     * A boolean indicating whether or not this overlay should destroy
     * itself when hidden.
     *
     * @attribute destroy_on_hide
     * @type: boolean
     * @default: false
     */
    destroy_on_hide: {
        value: false,
        writeOnce: "initOnly"
    },

    /**
     * A boolean indicating whether or not this overlay should show the close
     * button in the top right corner.
     *
     * @attribute destroy_on_hide
     * @type: boolean
     * @default: false
     */
    show_close_button: {
        value: false,
        writeOnce: "initOnly"
    }
};


Y.extend(FormOverlay, Y.lp.ui.PrettyOverlay, {

    initializer: function() {
        // This function is intentionally blank as it's not defined by
        // PrettyOverlay but is required by YUI.
    },
    /**
     * Create the nodes for the form and add them to the contentBody.
     * <p>
     * This method is invoked after renderUI is invoked for the Widget class
     * using YUI's aop infrastructure.
     * </p>
     *
     * @method _renderUIFormOverlay
     * @protected
     */
    _renderUIFormOverlay: function(){
        // Create a node that will contain the form header:
        this.form_header_node = Y.Node.create(
            FormOverlay.FORM_HEADER_TEMPLATE);

        // Create a form node that will contain the form content:
        this.form_node = Y.Node.create(FormOverlay.FORM_TEMPLATE);

        // Create a submit button if none was provided in the
        // configuration.
        if (this.get("form_submit_button") === null) {
            this.set("form_submit_button",
                     Y.Node.create(FormOverlay.SUBMIT_TEMPLATE));
        }

        // Create a cancel button if none was provided in the
        // configuration.
        if (this.get("form_cancel_button") === null &&
                !this.get('show_close_button')){
            this.set("form_cancel_button",
                     Y.Node.create(FormOverlay.CANCEL_TEMPLATE));
        }

        // Create node to contain any errors when when the showError()
        // method is called.
        this.error_node = Y.Node.create(FormOverlay.ERROR_TEMPLATE);

        // Set the top right close button visibility.
        var close_button = this.get('boundingBox').one('.close a');
        if (this.get('show_close_button')) {
            close_button.setStyle('visibility', 'inherit');
        }

        this._setFormContent();
    },

    /**
     * Bind the submit button to the _onFormSubmit() method.
     * <p>
     * This method is invoked after bindUI is invoked for the Widget class
     * using YUI's aop infrastructure.
     * </p>
     *
     * @method bindUI
     * @protected
     */
    _bindUIFormOverlay: function(){
        Y.on("submit",
             Y.bind(this._onFormSubmit, this),
             this.form_node);

        // Setup the cancel button to hide the formoverlay.
        if (Y.Lang.isValue(this.get("form_cancel_button"))) {
            Y.on("click",
                 Y.bind(function(e){ this.hide();}, this),
                 this.get("form_cancel_button"));
        }
        this.on("visibleChange", function(e) {
            // If the 'centered' configuration attribute is set to true,
            // then we should always re-center relative to the current
            // viewport when shown:
            if (e.newVal) {
                if (this.get('centered')){
                    this.centered();
                }
                this._focusChild();
            }
        });
    },

    /**
     * If destroy_on_hide, call the destroy method when this formoverlay
     * is hidden.
     *
     * @method _bindDestroyOnHide
     * @protected
     */
    _bindDestroyOnHide: function(){
        if (this.get('destroy_on_hide')) {
            this.after('visibleChange', function(e) {
                if (!e.newVal) {
                    this.destroy();
                }
            });
        }
    },

    /**
     * Setup and add the form to the DOM.
     *
     * @method _setFormContent
     * @private
     */
    _setFormContent: function(){
        // Add the form header content to the form header.
        this.form_header_node.set('innerHTML',
            this.get('form_header'));


        // Add the form content to the form node.
        // The form_content can be a string of HTML (as is useful when
        // it is obtained via AJAX) or a form node (as is useful if the
        // form is grabbed from the current page).
        var form_content = this.get('form_content');
        if (form_content instanceof Y.Node) {
            this.form_node.appendChild(form_content);
        } else {
            this.form_node.set("innerHTML", form_content);
        }

        // Append the error msg node at the bottom of the form.
        this.form_node.appendChild(this.error_node);

        // Create a div to wrap the submit button in, to provide
        // more flexibility for alignment and styling etc.
        var wrapper_div = Y.Node.create('<div/>');
        wrapper_div.addClass(FormOverlay.C_ACTIONS);
        wrapper_div.appendChild(this.get("form_submit_button"));
        if (Y.Lang.isValue(this.get("form_cancel_button"))) {
            wrapper_div.appendChild(this.get("form_cancel_button"));
        }
        this.form_node.appendChild(wrapper_div);

        var body_node = Y.Node.create('<div/>');
        body_node.appendChild(this.form_header_node);
        body_node.appendChild(this.form_node);

        this.setStdModContent(
            Y.WidgetStdMod.BODY, body_node, Y.WidgetStdMod.REPLACE);
    },


    /**
     * Focus the first form element or the close button if the form
     * is not yet loaded or was removed.
     *
     * @method _focusChild
     * @private
     */
    _focusChild: function() {
        var all_inputs = this.form_node.all('input,select,textarea,button');
        var sane_inputs = [];
        all_inputs.each(function(item, index, node_list) {
            var displayed = item.get('region').height > 0;
            var visible = item.getComputedStyle('visibility') === 'visible';
            var not_input_hidden = !(
                item.get('tagName') === 'INPUT' &&
                item.get('type') === 'hidden');
            if (displayed && visible && not_input_hidden) {
                sane_inputs.push(item);
            }
        });
        if (sane_inputs.length > 0) {
            sane_inputs[0].focus();
        } else {
            this.get('boundingBox').one('.close-button').focus();
        }
    },

    /**
     * Extract the form data and pass it to the user-provided submit
     * callback.
     *
     * @method _onFormSubmit
     * @private
     */
    _onFormSubmit: function(e){
        this.clearError();
        var submit_callback = this.get("form_submit_callback");

        // Prevent the event propagation only if we have a user-supplied
        // submit callback function. Otherwise let the event go ahead
        // with its default behavior.
        if (submit_callback) {
            e.halt(true);

            var data = this.getFormData();
            submit_callback(data, this.get("io_provider"));
        }
    },

    /**
    * Method to enumerate through an HTML form's elements collection
    * and return a string comprised of key-value pairs.
    *
    * This method was only slightly modified from YUI's io-form.js
    * _serialize method. (Removed encoding, returned hash, renamed vars).
    * Not sure how to best format the long lines.
    *
    * @method getFormData
    * @static
    * @return string
    */
    getFormData: function() {
        var data = {};

        // A helper function for adding form data to the return dict.
        // Note, similar to python's parse_qs, the value for each key
        // is a list, as a form can have the same key with multiple values
        // (for eg., a multiple select for languages - "lang=en&lang=de")
        var addData = function(key, value){
            if (data[key] === undefined){
                data[key] = [value];
            } else {
                data[key].push(value);
            }
        };

        // Another helper to get the value of an HTML option:
        var getOptionValue = function(option){
            if (option.attributes.value && option.attributes.value.specified){
                return option.value;
            } else {
                return option.text;
            }
        };

        // The following vars are used inside the for-loop below for selects.
        var select_idx;
        var num_options;
        var option;
        var option_value;

        // Iterate over the form elements collection to construct the
        // label-value pairs.
        var form_elem = Y.Node.getDOMNode(this.form_node);
        var elem_idx;
        var num_elems;
        for (elem_idx = 0,num_elems = form_elem.elements.length;
             elem_idx < num_elems;
             ++elem_idx) {

            var elem = form_elem.elements[elem_idx];

            if (elem.name && !elem.disabled) {

                switch (elem.type) {
                    // Safari, Opera, FF all default opt.value from .text if
                    // value attribute not specified in markup
                    case 'select-one':
                        if (elem.selectedIndex > -1) {
                            option = elem.options[elem.selectedIndex];
                            addData(elem.name, getOptionValue(option));
                        }
                        break;
                    case 'select-multiple':
                        if (elem.selectedIndex > -1) {
                            for (
                                select_idx = elem.selectedIndex,
                                    num_options = elem.options.length;
                                select_idx < num_options;
                                ++select_idx) {
                                option = elem.options[select_idx];
                                if (option.selected) {
                                    addData(elem.name,
                                            getOptionValue(option));
                                }
                            }
                        }
                        break;
                    case 'radio':
                    case 'checkbox':
                        if(elem.checked){
                            addData(elem.name, elem.value);
                        }
                        break;
                    case 'file':
                        // stub case as XMLHttpRequest will only send
                        // the file path as a string.
                    case undefined:
                        // stub case for fieldset element which returns
                        // undefined.
                    case 'reset':
                        // stub case for input type reset button.
                    case 'button':
                        // stub case for input type button elements.
                        break;
                    case 'submit':
                        break;
                    default:
                        addData(elem.name, elem.value);
                }
            }
        }
        return data;
    },

    /**
     * Display an error message or a number of error messages.
     *
     * @method showError
     */
    showError: function(error_msgs){
        this.error_node.empty(true);
        var error_content;
        if (Y.Lang.isString(error_msgs)) {
            error_content = Y.Node.create('<p></p>').set('text', error_msgs);
        } else {
            error_content = Y.Node.create(
                '<p>The following errors were encountered:</p><ul></ul>');
            var error_list = error_content.one('ul');
            var li_nodes = new Y.NodeList([]);
            Y.each(error_msgs, function(error_msg){
                li_nodes.push(
                    Y.Node.create('<li></li>').set('text', error_msg));
            });
            error_list.append(li_nodes);
        }
        this.error_node.appendChild(error_content);
    },

    /**
     * Clear any error message text.
     *
     * @method clearError
     */
    clearError: function(){
        this.error_node.empty(true);
    },

    /**
     * Load the form content from a URL. When the form content has been
     * fixed it will be rendered in the overlay.
     *
     * @method loadFormContentAndRender
     * @param url {String} The URL from where to load the form content.
     */
    loadFormContentAndRender: function (url) {
        var on_success = function(id, response, overlay) {
            overlay.set('form_content', response.responseText);
            overlay.renderUI();
            overlay.bindUI();
        };
        var on_failure = function(id, response, overlay) {
            overlay.set(
                'form_content',
                "Sorry, an error occurred while loading the form.");
            overlay.renderUI();
        };
        var cfg = {
            on: {success: on_success, failure: on_failure},
            "arguments": this
            };
        this.get("io_provider").io(url, cfg);
    }
});

ns.FormOverlay = FormOverlay;

}, "0.1", {"skinnable": true, "requires": ["lp.ui.overlay"]});
