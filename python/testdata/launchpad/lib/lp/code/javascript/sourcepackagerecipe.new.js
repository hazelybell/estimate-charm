/* Copyright 2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Control enabling/disabling form elements on the +new-recipe page.
 *
 * @module Y.lp.code.sourcepackagerecipe.new
 * @requires node, DOM
 */
YUI.add('lp.code.sourcepackagerecipe.new', function(Y) {
    Y.log('loading lp.code.sourcepackagerecipe.new');
    var module = Y.namespace('lp.code.sourcepackagerecipe.new');

    function getRadioSelectedValue(selector) {
      var tmpValue= false;
      Y.all(selector).each(function(node) {
          if (node.get('checked'))
            tmpValue = node.get('value');
        });
      return tmpValue;
    }

    var PPA_SELECTOR_ID = 'field.daily_build_archive';
    var PPA_NAME_ID = 'field.ppa_name';
    var set_field_focus = false;

    function set_enabled(field_id, is_enabled) {
       var field = Y.DOM.byId(field_id);
       field.disabled = !is_enabled;
       if (is_enabled && set_field_focus) field.focus();
    }

    module.onclick_use_ppa = function(e) {
      var value = getRadioSelectedValue('input[name="field.use_ppa"]');
      if (value == 'create-new') {
        set_enabled(PPA_NAME_ID, true);
        set_enabled(PPA_SELECTOR_ID, false);
      }
      else {
        set_enabled(PPA_NAME_ID, false);
        set_enabled(PPA_SELECTOR_ID, true);
      }
    };

    module.setup = function() {
       Y.all('input[name="field.use_ppa"]').on(
          'click', module.onclick_use_ppa);

       // Set the initial state.
       module.onclick_use_ppa();
       // And from now on, set the focus to the active input field when the
       // radio button is clicked.
       set_field_focus = true;
    };

   }, "0.1", {"requires": ["node", "DOM"]}
);
