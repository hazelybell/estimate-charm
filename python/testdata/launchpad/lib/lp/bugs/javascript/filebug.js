/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Provide functionality for the file bug pages.
 *
 * @module bugs
 * @submodule filebug
 */
YUI.add('lp.bugs.filebug', function(Y) {

var namespace = Y.namespace('lp.bugs.filebug');
var info_type = Y.lp.app.information_type;

// For tests.
var skip_animation;

var setup_filebug = function(skip_anim) {
    skip_animation = skip_anim;
    if (LP.cache.enable_bugfiling_duplicate_search) {
        Y.lp.bugs.filebug_dupefinder.setup_dupe_finder();
    }
    Y.lp.bugs.filebug_dupefinder.setup_dupes();
    // Only attempt to wire up the file bug form if the form is rendered.
    var filebugform = Y.one('#filebug-form');
    var bugreportingform = Y.one('#bug-reporting-form');
    if (Y.Lang.isValue(filebugform) || Y.Lang.isValue(bugreportingform)) {
        var search_button =
            Y.one(Y.DOM.byId('field.actions.projectgroupsearch'));
        if (Y.Lang.isValue(search_button )) {
            search_button.set('value', 'Check again');
        }
        setup_plain_inputs();
        set_default_privacy_banner();
        setup_security_related();
        setupChoiceWidgets();
    }
};


/**
 * If there are not choice widgets, but radio buttons, then we should watch
 * those radio buttons for change to make sure we fire the information type
 * change events.
 */
var setup_plain_inputs = function () {
   var itypes_table = Y.one('.radio-button-widget');

   if (itypes_table) {
       itypes_table.delegate('change', function(ev) {
           Y.fire(info_type.EV_CHANGE, {
               value: this.get('value')
           });
       }, "input[name='field.information_type']");
   }
};

/**
 * Due to the privacy setting of the project/bugs we might only allow a
 * non-public information type. In this case we need to go ahead and let the
 * user know it's going to be private.
 *
 * This is used by the security checks. If the issue is unmade/not security
 * related then we need to check the normal default behavior to make sure we
 * show the correct banner.
 */
var set_default_privacy_banner = function() {
    var itypes_table = Y.one('.radio-button-widget');
    var val = null;
    if (itypes_table) {
        val = itypes_table.one(
            "input[name='field.information_type']:checked").get('value');
    } else {
        val = 'PUBLIC';
    }

    if (LP.cache.bug_private_by_default) {
        var filebug_privacy_text = "This report will be private. " +
            "You can disclose it later.";

        Y.fire(info_type.EV_ISPRIVATE, {
            text: filebug_privacy_text,
            value: val
        });
    }
};


var setupChoiceWidgets = function() {
    Y.lp.app.choice.addPopupChoice('status', LP.cache.bugtask_status_data);
    Y.lp.app.choice.addPopupChoice(
        'importance', LP.cache.bugtask_importance_data);
    var cache = LP.cache.information_type_data;
    var information_helpers = Y.lp.app.information_type;
    var choices = information_helpers.cache_to_choicesource(cache);

    var information_type = Y.lp.app.choice.addPopupChoiceForRadioButtons(
        'information_type', choices, true);

    // When dealing with legacy inputs the information type could have not
    // been created and we get back a null value.
    if (information_type) {
        // We are not doing ajax saves of the information type so we need to
        // disable the flash on save for the widget.
        information_type.set('flashEnabled', false);

        // When the information type widget changes we need to let the
        // information type module know so it can process the change and
        // update things like banners displayed.
        information_type.on('save', function (ev) {
            Y.fire(info_type.EV_CHANGE, {
                value: ev.target.get('value')
            });
        });
    }
};

var setup_security_related = function() {
    var security_related = Y.one('[id="field.security_related"]');
    if (!Y.Lang.isValue(security_related)) {
        return;
    }
    var notification_text = "This report will be private " +
                           "because it is a security " +
                           "vulnerability. You can " +
                           "disclose it later.";
    security_related.on('change', function() {
        var checked = security_related.get('checked');
        if (checked) {
            // XXX: Bug #1078054
            // This should use the correct information type based on the
            // project default. We use PRIVATESECURITY because it'll get the
            // right banner shown.
            Y.fire(info_type.EV_ISPRIVATE, {
                text: notification_text,
                value: 'PRIVATESECURITY'
            });
        } else {
            Y.fire(info_type.EV_ISPUBLIC, {
                value: 'PUBLIC'
            });
            // Check with the default settings if we should add the privacy
            // banner back because it's the default of the current project.
            set_default_privacy_banner();
        }
    });
};

namespace.setup_filebug = setup_filebug;

}, "0.1", {"requires": [
    "base", "node", "event", "node-event-delegate", "lp.ui.choiceedit",
    "lp.ui.banner", "lp.app.choice", "lp.app.information_type",
    "lp.bugs.filebug_dupefinder"]});
