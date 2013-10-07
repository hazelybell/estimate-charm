/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Setup for managing subscribers list for bugs.
 *
 * @module workitems
 * @submodule expanders
 */

YUI.add('lp.workitems.expanders', function(Y) {

    var namespace = Y.namespace('lp.workitems.expanders');

    /**
     * Record of all expanders and their default state.
     */
    var expanders = [];

    function expander_expand(expander, i){
        expander[0].render(true, false);
    }
    namespace._expander_expand = expander_expand;

    function expander_collapse(expander, i){
        expander[0].render(false, false);
    }
    namespace._expander_collapse = expander_collapse;

    function expander_restore_default_state(expander, i){
        expander[0].render(expander[1], false);
    }
    namespace._expander_restore_default_state = expander_restore_default_state;

    /**
     * Attach an expander to each expandable in the page.
     */
    function setUpWorkItemExpanders(expander_config){
        Y.all('[class=expandable]').each(function(e) {
            add_expanders(e, expander_config);
        });

        Y.all('.expandall_link').on("click", function(event){
            attach_handler(event, expander_expand);
        });

        Y.all('.collapseall_link').on("click", function(event){
            attach_handler(event, expander_collapse);
        });

        Y.all('.defaultall_link').on("click", function(event){
            attach_handler(event, expander_restore_default_state);
        });
    }
    namespace.setUpWorkItemExpanders = setUpWorkItemExpanders;

    function add_expanders(e, expander_config){
        var expander_icon = e.one('[class=expander]');
        // Our parent's first sibling is the tbody we want to collapse.
        var widget_body = e.ancestor().next();

        if (Y.Lang.isUndefined(expander_config))
        {
            expander_config = {};
        }

        var expander = new Y.lp.app.widgets.expander.Expander(expander_icon,
                                                              widget_body,
                                                              expander_config);
        expander.setUp(true);

        var index = e.ancestor('[class=workitems-group]').get('id');

        // We record the expanders so we can reference them later
        // First we have an array indexed by each milestone
        if (!Y.Lang.isValue(expanders[index])){
            expanders[index] = [];
        }

        // For each milestone, store an array containing the expander
        // object and the default state for it
        default_expanded = widget_body.hasClass('default-expanded');
        expanders[index].push(new Array(expander, default_expanded));
    }
    namespace._add_expanders = add_expanders;

    function attach_handler(event, func){
        var index = event.currentTarget.get('id');
        index = index.match(/milestone_\d+/)[0];
        Y.Array.forEach(expanders[index], func);
    }
    namespace._attach_handler = attach_handler;

}, "0.1", {"requires": ["lp.app.widgets.expander"]});

