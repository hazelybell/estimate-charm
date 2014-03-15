/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Information Type choice widget for branch pages.
 */

YUI.add('lp.code.branch.information_type_choice', function(Y) {

var namespace = Y.namespace('lp.code.branch.information_type_choice');
var information_type = Y.namespace('lp.app.information_type');
var superclass = Y.Widget;

namespace.BranchInformationTypeWidget = Y.Base.create(
    "branchInformationTypeWidget", Y.Widget, [], {
    initializer: function(cfg) {
        this.lp_client = new Y.lp.client.Launchpad(cfg);
        this.privacy_link = Y.one('#privacy-link');
    },

    renderUI: function() {
        // If user doesn't have permission, no link, nothing to do.
        if (!Y.Lang.isValue(this.privacy_link)) {
            return;
        }
        var initial_value = information_type.get_cache_data_from_key(
            LP.cache.context.information_type, 'name', 'value');
        var information_type_value = Y.one('#information-type');
        this.information_type_edit = new Y.ChoiceSource({
            editicon: this.privacy_link,
            contentBox: Y.one('#privacy'),
            value_location: information_type_value,
            value: initial_value,
            title: "Change information type",
            items: information_type.cache_to_choicesource(
                LP.cache.information_type_data
            ),
            backgroundColor: '#FFFF99',
            flashEnabled: false
        });
        Y.lp.app.choice.hook_up_choicesource_spinner(
                this.information_type_edit);
        this.information_type_edit.render();
        this.privacy_link.addClass('js-action');
    },

    bindUI: function() {
        // If user doesn't have permission, no link, nothing to do.
        if (!Y.Lang.isValue(this.privacy_link)) {
            return;
        }
        var that = this;
        this.information_type_edit.on("save", function(e) {
            var value = that.information_type_edit.get('value');
            information_type.update_privacy_portlet(value);
            that._save_information_type(value);

        });
    },

    _save_information_type: function(value) {
        var that = this;
        var widget = this.information_type_edit;
        var error_handler = new Y.lp.client.FormErrorHandler();
        error_handler.showError = function(error_msg) {
            Y.lp.app.errors.display_error(
                Y.one('#information-type'), error_msg);
        };
        error_handler.handleError = function() {
            var orig_value = information_type.get_cache_data_from_key(
                LP.cache.context.information_type, 'name', 'value');
            widget.set('value', orig_value);
            if (that.get('use_animation')) {
                widget._showFailed();
            }
            information_type.update_privacy_portlet(orig_value);
            return false;
        };
        var submit_url = document.URL + "/+edit-information-type";
        var qs = Y.lp.client.append_qs(
                '', 'field.actions.change', 'Change Branch');
        qs = Y.lp.client.append_qs(qs, 'field.information_type', value);
        var config = {
            method: "POST",
            headers: {'Accept': 'application/xhtml;application/json'},
            data: qs,
            on: {
                start: function () {
                    widget._uiSetWaiting();
                },
                end: function () {
                    widget._uiClearWaiting();
                },
                success: function (id, response) {
                    that._information_type_save_success(value);
                    Y.lp.client.display_notifications(
                        response.getResponseHeader('X-Lazr-Notifications'));
                },
                failure: error_handler.getFailureHandler()
            }
        };
        this.lp_client.io_provider.io(submit_url, config);
    },

    _information_type_save_success: function(value) {
        LP.cache.context.information_type =
            information_type.get_cache_data_from_key(
                    value, 'value', 'name');
        Y.fire(information_type.EV_CHANGE, {
            value: value
        });
        if (this.get('use_animation')) {
            this.information_type_edit._showSucceeded();
        }
    }
}, {
    ATTRS: {
        // For testing
        use_animation: {
            value: true
        }
    }
});

}, "0.1", {
    requires: [
        "base", "oop", "node", "event", "io-base", "lp.ui.choiceedit",
        "lp.app.errors", "lp.app.choice", "lp.app.information_type"]
});
