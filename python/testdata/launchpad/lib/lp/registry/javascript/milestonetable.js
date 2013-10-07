/* Copyright 2010-2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Dynamically add milestones to an HTML table.
 *
 * @module Y.lp.registry.milestonetable
 * @requires node, io-base, lang, lp.anim
 */
YUI.add('lp.registry.milestonetable', function(Y) {
    Y.log('loading lp.registry.milestonetable');
    var module = Y.namespace('lp.registry.milestonetable');

    // get_milestone_row() needs these when it is called. Other methods
    // should get this information passed as an argument.
    module._milestone_row_uri_template = null;
    module._tbody = null;

    module._prepend_node = function(parent_node, child_node) {
        // Add the child_node to the parent_node as the first item.
        var children = parent_node.get('children');
        if (children === null) {
            parent_node.appendChild(child_node);
        } else {
            parent_node.insertBefore(child_node, children.item(0));
            }
        };

    module._ensure_table_is_seen = function(tbody) {
        // Remove the 'hidden' class from the table to ensure it is visible.
        table = tbody.ancestor();
        table.removeClass('hidden');
        };

    module._clear_add_handlers = function(data) {
        // Detach the callback and errorback functions from the Y.io events.
        // The data has been used. If they are not detached, there will be
        // multiple adds for each use of the Create milestone link.
        data.success_handle.detach();
        data.failure_handle.detach();
        };

    module._on_add_success = function(id, response, data) {
        // Add the milestone to the milestone table on Y.io success.
        var row = Y.Node.create(Y.Lang.trim(response.responseText));
        module._ensure_table_is_seen(data.tbody);
        module._prepend_node(data.tbody, row);
        Y.lp.anim.green_flash({node: row}).run();
        module._clear_add_handlers(data);
        };

    module._on_add_failure = function(id, response, data) {
        // Add the failure message to the milestone table on Y.io failure.
        var row = Y.Node.create(Y.Lang.sub(
            '<tr><td colspan="0">' +
            'Could not retrieve milestone {name}</td></tr>', data));
        module._ensure_table_is_seen(data.tbody);
        module._prepend_node(data.tbody, row);
        Y.lp.anim.red_flash({node: row}).run();
        module._clear_add_handlers(data);
        };

    module._setup_milestone_event_data = function(parameters, tbody) {
        // Attach the callback to the Y.io event and return their data
        var data = {
            name: parameters.name,
            tbody: tbody
            };
        data.success_handle = Y.on(
            'io:success', module._on_add_success, this, data);
        data.failure_handle = Y.on(
            'io:failure', module._on_add_failure, this, data);
        return data;
        };

    /**
      * The milestoneoverlay next_step to add the milestone to the page.
      *
      * This is the callback passed as 'next_step' in milestoneoverlay config.
      *
      * @method get_milestone_row
      * @param {Object} parameters Object literal of config name/value pairs.
      *     The form parameters that were submitted to create the milestone.
      */
    module.get_milestone_row = function(parameters) {
        module._setup_milestone_event_data(parameters, module._tbody);
        var milestone_row_uri = Y.Lang.sub(
            module._milestone_row_uri_template, parameters);
        Y.io(milestone_row_uri);
        };

    /**
      * Setup the URL to get the milestone and the table it will be added too.
      *
      * @method setup
      * @param {Object} parameters Object literal of config name/value pairs.
      *     config.milestone_row_uri_template is the Y.Lang.sub template
      *         that is used to create the URL to get the milestone row.
      *     config.milestone_rows_id is the id the tbody that the
      *         milestone row will be added too.
      */
    module.setup =  function(config) {
        if (config === undefined) {
            throw new Error(
                "Missing setup config for milestonetable.");
            }
        if (config.milestone_row_uri_template === undefined ||
            config.milestone_rows_id === undefined ) {
            throw new Error(
                "Undefined properties in setup config for milestonetable.");
            }
        module._milestone_row_uri_template = config.milestone_row_uri_template;
        module._tbody = Y.one(config.milestone_rows_id);
        if (module._tbody === null) {
            throw new Error(
                Y.Lang.sub("'{milestone_rows_id}' not in page.", config));
            }
        };

}, "0.1", {"requires": [
    "node", "io-base", "lang", "lp.anim"
    ]});
