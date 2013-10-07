/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.buglisting_utils', function(Y) {
    /**
     * A utility for configuring the display of bug listings.
     *
     * The purpose of this widget is be a mechanism for turning
     * fields on and off in a bug listing display.  It extends
     * from BaseConfigUtil, which provides the clickable settings
     * icon.  When the icon is clicked, a form overlay opens with
     * various checkboxes for turning fields on and off.
     *
     * This doesn't actually change the display, though.  It fires
     * an event that the buglisting navigator will hook into to update
     * the list's display.
     *
     * @module lp.buglisting_utils
     */

    // Constants.
    var FORM = 'form';


    /**
     * BugListingConfigUtil is the main object used to manipulate
     * a bug listing's display.
     *
     * Constructor accepts a config containing
     * - model (a BugListingModel)
     * - cookie_name
     * - form the FormOverlay to manipulate
     *
     * If model is not supplied, model parameters must be included, especially
     * - form_visibility
     * - form_visibility_defaults
     *
     * @class BugListingConfigUtil
     * @extends Y.lp.configutils.BaseConfigUtil
     * @constructor
     */
    function BugListingConfigUtil() {
        BugListingConfigUtil.superclass.constructor.apply(this, arguments);
    }

    BugListingConfigUtil.NAME = 'buglisting-config-util';

    /**
     * Object to reference display names for field_visibility
     * form inputs.
     */
    BugListingConfigUtil.field_display_names = {
        show_id: 'Number',
        show_importance: 'Importance',
        show_status: 'Status',
        show_information_type: 'Information Type',
        show_heat: 'Heat',
        show_targetname: 'Package/Project/Series name',
        show_datecreated: 'Age',
        show_date_last_updated: 'Date last updated',
        show_assignee: 'Assignee',
        show_reporter: 'Reporter',
        show_milestone_name: 'Milestone',
        show_tag: 'Tags'
    };

    BugListingConfigUtil.ATTRS = {

        /**
         * The cookie name as set by the view.
         *
         * We get this value from the LP cache.
         *
         * @attribute cookie_name
         * @type String
         */
        cookie_name: {
            valueFn: function() {
                if (
                    Y.Lang.isValue(window.LP) &&
                    Y.Lang.isValue(LP.cache.cbl_cookie_name)) {
                    return LP.cache.cbl_cookie_name;
                } else {
                    return '';
                }
            }
        },

        /**
         * A reference to the form overlay used in the overlay.
         *
         * @attribute form
         * @type Y.lp.ui.FormOverlay
         * @default null
         */
        form: {
            value: null
        },
        model: {
            value: null
        }
    };

    BugListingConfigUtil.INPUT_TEMPLATE = [
        '<li><input type="checkbox" class="{name}" name="{name}" ',
        'value="{display_name}" id="{name}_id" {checked}> ',
        '<label for="{name}_id">{display_name}</label></li>'].join('');

    Y.extend(BugListingConfigUtil, Y.lp.configutils.BaseConfigUtil, {

        initializer: function(config){
            if (config === undefined){
                config = {};
            }
            if (Y.Lang.isNull(this.get('model'))){
                this.set('model',
                    new Y.lp.bugs.buglisting.BugListingModel(config));
            }
        },

        /**
         * Hook into the destroy lifecyle to ensure the form
         * overlay is destroyed.
         *
         * @method destructor
         */
        destructor: function() {
            if (Y.Lang.isValue(this.get(FORM))) {
                var form = this.get(FORM);
                this.set(FORM, null);
                form.destroy();
            }
        },

        /**
         * Build the input nodes used on the form overlay.
         *
         * @method getFormInputs
         */
        getFormInputs: function() {
            var fields = this.get('model').get_field_visibility();
            var display_names = this.constructor.field_display_names;
            var nodes = [];
            var item,
                name,
                display_name,
                checked,
                input_html,
                input_node;
            for (item in fields) {
                if (fields.hasOwnProperty(item)) {
                    name = item;
                    display_name = display_names[item];
                    if (fields[item] === true) {
                        checked = 'checked';
                    } else {
                        checked = '';
                    }
                    input_html = Y.Lang.sub(
                        this.constructor.INPUT_TEMPLATE,
                        {name: name, display_name: display_name,
                        checked: checked});
                    input_node = Y.Node.create(input_html);
                    nodes.push(input_node);
                }
            }
            return new Y.NodeList(nodes);
        },

        /**
         * Build the reset link for the form.
         *
         * Also, provide a click handler to reset the fields config.
         *
         * @method getResetLink
         */
        getResetLink: function() {
            var link = Y.Node.create('<a></a>');
            link.addClass('js-action');
            link.addClass('reset-buglisting');
            link.setContent('Reset to default');
            link.on('click', function(e) {
                var model = this.get('model');
                var defaults = model.get('field_visibility_defaults');
                this.updateFieldVisibilty(defaults, true);
                this.setCookie();
            }, this);
            return link;
        },

        /**
         * Build the form content for form overlay.
         *
         * @method buildFormContent
         */
        buildFormContent: function() {
            var div = Y.Node.create(
                '<ul></ul>').addClass('buglisting-opts');
            var inputs = this.getFormInputs();
            div.append(inputs);
            var link = this.getResetLink();
            div.append(link);
            return div;
        },

        /**
         * Helper method for updating field_visibility.
         *
         * @method updateFieldVisibilty
         */
        updateFieldVisibilty: function(fields, destroy_form) {
            this.get('model').set_field_visibility(fields);
            var form = this.get(FORM);
            if (Y.Lang.isValue(form)) {
                form.hide();
            }
            // Destroy the form and rebuild it.
            if (destroy_form === true) {
                this.get(FORM).hide();
                this._extraRenderUI();
            }
        },

        /**
         * Process the data from the form overlay submit.
         *
         * data is an object whose members are the checked
         * input elements from the form.  data has the same members
         * as field_visibility, so if the key is in data it should
         * be set to true in field_visibility.
         *
         * @method handleOverlaySubmit
         */
        handleOverlaySubmit: function(data) {
            var fields = this.get('model').get_field_visibility();
            var member;
            for (member in fields) {
                if (fields.hasOwnProperty(member)) {
                    if (Y.Lang.isValue(data[member])) {
                        // If this field exists in data, set it true.
                        // in field_visibility.
                        fields[member] = true;
                    } else {
                        // Otherwise, set the member to false in
                        // field_visibility.
                        fields[member] = false;
                    }
                }
            }
            this.updateFieldVisibilty(fields);
            this.setCookie(fields);
        },

        /**
         * Set the given value for the buglisting config cookie.
         * If config is not specified, the cookie will be cleared.
         *
         * @method setCookie
         */
        setCookie: function(config) {
            var cookie_name = this.get('cookie_name');
            if (Y.Lang.isValue(config)) {
                Y.Cookie.setSubs(cookie_name, config, {
                    path: '/',
                    expires: new Date('January 19, 2038')});
            } else {
                Y.Cookie.remove(cookie_name, {path: '/'});
            }
        },

        /**
         * Hook in _extraRenderUI provided by BaseConfigUtil
         * to add a form overlay to the widget.
         *
         * @method _extraRenderUI
         */
        _extraRenderUI: function() {
            var form_content = this.buildFormContent();
            var on_submit_callback = Y.bind(this.handleOverlaySubmit, this);
            util_overlay = new Y.lp.ui.FormOverlay({
                align: 'left',
                headerContent: '<h2>Visible information</h2>',
                centered: true,
                form_content: form_content,
                form_submit_button: Y.Node.create(
                    '<input type="submit" value="Update" ' +
                    'class="update-buglisting" />'
                ),
                form_cancel_button: Y.Node.create(
                    '<button type="button" name="field.actions.cancel" ' +
                    'class="hidden" >Cancel</button>'
                ),
                form_submit_callback: on_submit_callback
            });
            util_overlay.get(
                'boundingBox').addClass(this.getClassName('overlay'));
            this.set(FORM, util_overlay);
            util_overlay.render();
            util_overlay.hide();
        },

        /**
         * Hook into _handleClick provided by BaseConfigUtil
         * to show overlay when the settings cog icon is clicked.
         *
         * @method _handleClick
         */
        _handleClick: function() {
            var form = this.get(FORM);
            form.show();
        }

    });

    var buglisting_utils = Y.namespace('lp.buglisting_utils');
    buglisting_utils.BugListingConfigUtil = BugListingConfigUtil;

    /**
     * Update the visibilty of the sort buttons.
     *
     * We want to display only the sort buttons for fields which
     * are displayed. To avoid surprises for users, the current sort
     * order is always displayed, even when the related data is not
     * shown.
     *
     * @param orderbybar {Object} The order by bar.
     * @param data_visibility {Associative Array} The visibility data
     *     as used in Y.bugs.buglisting.BugListingModel.
     */
    function update_sort_button_visibility(orderbybar, data_visibility) {
        // We must translate the field names as used by
        // BugListingConfigUtil to those used by the "order by" buttons.
        var orderby_visibility = {};
        var order_key;
        var data_key;
        for (data_key in data_visibility) {
            if (data_visibility.hasOwnProperty(data_key) &&
                data_key.substring(0, 5) === 'show_') {
                order_key = data_key.replace('show_', '');
                orderby_visibility[order_key] = data_visibility[data_key];
            }
        }
        // Never hide the button for the current sort order...
        orderby_visibility[orderbybar.get('active')] = true;
        // ...and buttons for sort orders that should always be displayed.
        Y.each(orderbybar.always_display, function(sort_key) {
            orderby_visibility[sort_key] = true;
        });
        orderbybar.updateVisibility(orderby_visibility);
    }

    buglisting_utils.update_sort_button_visibility =
        update_sort_button_visibility;

}, '0.1', {'requires': [
    'cookie', 'history', 'lp.configutils', 'lp.ui.formoverlay',
    'lp.bugs.buglisting'
    ]});
