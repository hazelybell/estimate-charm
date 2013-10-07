/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Provide functionality for the file bug pages.
 *
 * @module blueprints
 * @submodule addspec
 */
YUI.add('lp.blueprints.addspec', function(Y) {

var namespace = Y.namespace('lp.blueprints.addspec');
var to_choice = Y.lp.app.information_type.cache_to_choicesource;
var info_type = Y.lp.app.information_type;

namespace.set_up = function () {
    var choice_data = to_choice(LP.cache.information_type_data);
    var widget = Y.lp.app.choice.addPopupChoiceForRadioButtons(
        'information_type',
        choice_data);

    // We are not doing ajax saves of the information type so we need to
    // disable the flash on save for the widget.
    widget.set('flashEnabled', false);

    // Make sure we catch changes to the information type.
    widget.on('save', function (ev) {
        Y.fire(info_type.EV_CHANGE, {
            value: ev.target.get('value')
        });
    });
};

}, "0.1", {"requires": ['lp.app.information_type', 'lp.app.choice']});
