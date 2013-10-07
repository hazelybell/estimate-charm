/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * @module lp.app.licence
 * @requires node, event
 */

YUI.add('lp.app.licence', function(Y) {

var namespace = Y.namespace('lp.app.licence');

/**
 * A widget to provide the click handling for product licences.
 * This widget does no rendering itself; it is used to enhance existing HTML.
 */
namespace.LicenceWidget = Y.Base.create("licenceWidget", Y.Widget, [], {
    bindUI: function() {
        // Set a click event handler for the div containing all the
        // licence checkbox.  When any licence checkbox is selected, the
        // "I haven't specified the licence yet" radio button is set to
        // "This project consists of code licensed under:".  However note
        // that the pending-div only shows up if the project has never
        // selected a licence.  In other cases, there's an "I don't know yet"
        // choice in the "Other choices" licence section.
        var license_pending = Y.one('#license_pending');
        if (Y.Lang.isValue(license_pending)) {
            license_pending.on('click', function(e) {
                Y.all('[name="field.licenses"]').set('checked', false);
                reveal_details();
            });
            var div = Y.one('#pending-div');
            if (Y.Lang.isValue(div)) {
                div.delegate('click', function(e) {
                    Y.one('#license_pending').set('checked', false);
                    Y.one('#license_complete').set('checked', true);
               }, '[type=checkbox][name="field.licenses"]');
            }
        }

        // When Other/Proprietary or Other/Open Source is chosen, the
        // license_info widget is displayed.
        var other_com = Y.one('input[value="OTHER_PROPRIETARY"]');
        var other_os = Y.one('input[value="OTHER_OPEN_SOURCE"]');
        var details = Y.one('#license-details');
        var proprietary = Y.one('#proprietary');

        var that = this;
        function reveal_details() {
            var cfg = {};
            if (!that.get('use_animation')) {
                cfg.duration = 0;
            }
            if (other_com.get('checked') || other_os.get('checked')) {
                if (!details.hasClass('lazr-opened')) {
                    Y.lp.ui.effects.slide_out(details, cfg).run();
                }
            } else {
                if (!details.hasClass('lazr-closed')) {
                    Y.lp.ui.effects.slide_in(details, cfg).run();
                }
            }
            if (other_com.get('checked')) {
                if (!proprietary.hasClass('lazr-opened')) {
                    Y.lp.ui.effects.slide_out(proprietary, cfg).run();
                }
            } else {
                if (!proprietary.hasClass('lazr-closed')) {
                    Y.lp.ui.effects.slide_in(proprietary, cfg).run();
                }
            }
        }
        other_com.on('click', reveal_details);
        other_os.on('click', reveal_details);
        proprietary.removeClass('hidden');

        // Pre-reveal license_info widget.
        reveal_details();
    }
}, {
    ATTRS: {
        // Disable for tests.
        use_animation: {
            value: true
        }
    }
});

}, "0.1", {
    "requires": ["base", "event", "node", "lp.ui.effects"]
});
