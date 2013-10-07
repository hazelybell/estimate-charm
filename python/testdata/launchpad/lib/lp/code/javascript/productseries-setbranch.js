/* Copyright 2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Control enabling/disabling of complex form on the
 * productseries/+setbranch page.
 *
 * @module Y.lp.code.productseries_setbranch
 * @requires node, DOM
 */
YUI.add('lp.code.productseries_setbranch', function(Y) {
    Y.log('loading lp.code.productseries_setbranch');
    var module = Y.namespace('lp.code.productseries_setbranch');

    module._get_selected_rcs = function() {
       var rcs_types = module._rcs_types();
       var selected = 'None';
       for (var i = 0; i < rcs_types.length; i++) {
          if (rcs_types[i].checked) {
             selected = rcs_types[i].value;
             break;
          }
       }
       return selected;
    };


    module.__rcs_types = null;

    module._rcs_types = function() {
       if (module.__rcs_types === null) {
          module.__rcs_types = document.getElementsByName('field.rcs_type');
       }
       return module.__rcs_types;
    };

    module.set_enabled = function(field_id, is_enabled) {
       var field = Y.DOM.byId(field_id);
       field.disabled = !is_enabled;
    };

    module.onclick_rcs_type = function(e) {
       /* Which rcs type radio button has been selected? */
       // CVS
       var rcs_types = module._rcs_types();
       var selectedRCS = module._get_selected_rcs();
       module.set_enabled('field.cvs_module', selectedRCS == 'CVS');
    };

    module.onclick_branch_type = function(e) {
       /* Which branch type radio button was selected? */
       var selectedRCS = module._get_selected_rcs();
       var types = document.getElementsByName('field.branch_type');
       var type = 'None';
       for (var i = 0; i < types.length; i++) {
          if (types[i].checked) {
             type = types[i].value;
             break;
          }
       }
       // Linked
       module.set_enabled('field.branch_location', type == 'link-lp-bzr');
       module.set_enabled('field.branch_name', type != 'link-lp-bzr');
       module.set_enabled('field.branch_owner', type != 'link-lp-bzr');
       // New, empty branch.
       // Import
       var is_external = (type == 'import-external');
       module.set_enabled('field.repo_url', is_external);
       module.set_enabled('field.cvs_module',
                   (is_external & selectedRCS == 'CVS'));
       var rcs_types = module._rcs_types();
       for (var j = 0; j < rcs_types.length; j++) {
          rcs_types[j].disabled = !is_external;
       }
    };

    module.setup = function() {
       Y.all('input[name="field.rcs_type"]').on(
          'click', module.onclick_rcs_type);
       Y.all('input[name="field.branch_type"]').on(
          'click', module.onclick_branch_type);

       // Set the initial state.
       module.onclick_rcs_type();
       module.onclick_branch_type();
    };

   }, "0.1", {"requires": ["node", "DOM"]}
);
