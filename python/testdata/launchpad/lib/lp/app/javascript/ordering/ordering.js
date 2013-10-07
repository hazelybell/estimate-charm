/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.ordering', function(Y) {
    /**
     * A menu bar for quickly reordering a list of items on a page.
     * This widget is used for managing the bar, it's buttons, and
     * the state of the ordering.
     *
     * The widget doesn't actually change the page state based on
     * requested ordering.  It fires an event to signal that a sort
     * order update is required.
     *
     * External code should listen for orderbybar:sort to know when
     * to update the page.
     *
     * @module lp.ordering
     */
    function OrderByBar() {
        OrderByBar.superclass.constructor.apply(this, arguments);
    }

    OrderByBar.NAME = 'orderbybar';

    OrderByBar.ATTRS = {

        /**
         * A list of [key, name] pairs where key is the sorting key
         * as used in a URL, i.e. ?orderby=importance, and name is
         * the display name for the button of the menu bar.
         *
         * We could probably get away without a default here, since
         * this will always be changed.  But having a default allows
         * the widget to show something if you create an OrderByBar
         * without any config.
         *
         * @attribute sort_keys
         * @type Array
         */
        sort_keys: {
            value: [
                ['bugnumber', 'Number', 'asc'],
                ['bugtitle', 'Title', 'asc'],
                ['status', 'Status', 'asc'],
                ['importance', 'Importance', 'desc'],
                ['bug-heat-icons', 'Heat', 'desc'],
                ['package', 'Package name', 'asc'],
                ['milestone', 'Milestone', 'asc'],
                ['assignee', 'Assignee', 'asc'],
                ['bug-age', 'Age', 'desc']
            ]
        },


        /**
         * The active sort key.  This should coorespond to the current
         * view of the data on the web page.
         *
         * Again, defaults will likely be overwritten with any use.
         *
         * @attribute active
         * @type String
         * @default importance
         */
        active: {
            value: 'importance',
            validator: function(value) {
                var sort_keys = this.get('sort_keys');
                var len = sort_keys.length;
                var i;
                for (i=0; i<len; i++) {
                    if (value === sort_keys[i][0]) {
                        return true;
                    }
                }
                // Fail big here, so call sites know what went wrong.
                throw Error('active attribute was not found in sort_keys');
            }
        },

        /**
         * The current sort order, either desc or asc.
         *
         * @attribute sort_order
         * @type String
         * @default 'asc'
         */
        sort_order: {
            value: 'asc',
            validator: function(value) {
                if (value === 'asc' || value === 'desc') {
                    return true;
                } else {
                    // Fail big here, so call sites know what went wrong.
                    throw Error('sort_order must be either "asc" or "desc"');
                }
            }
        },

        /**
         * The constructed sort key passed to a URL.  Used internally
         * to track the sort key and ordering, i.e. "-importance" vs.
         * "importance".
         *
         * @attribute sort_clause
         * @type String
         * @default importance
         *
         */
        sort_clause: {
            value: 'importance'
        },

        /**
         * Cache for the created li nodes.
         *
         * This allows the widget to refer back to the nodes
         * without having to look them up again via DOM traversal.
         *
         * @attribute li_nodes
         * @type Array
         * @default null
         */
        li_nodes: {
            value: null
        },

        /**
         * Config param to signal whether we need a div added
         * for config/settings widgets to hook onto.
         *
         * @attribute config_slot
         * @type Boolean
         * @default false
         */
        config_slot: {
            value: false
        },

        /**
         * A reference to the node created if config_slot is true.
         * This prevents having to do DOM lookup to find the node
         * again.
         *
         * @attribute config_node
         * @type Y.Node
         * @default null
         */
        config_node: {
            value: null
        }
    };

    OrderByBar.LI_TEMPLATE = [
        '<li id="{li_id}">{li_label}',
        '<span class="sort-arr"></span></li>'].join('');
    OrderByBar.ASCENDING_ARROW = Y.Node.create(
        '<span class="sprite order-ascending"></span>');
    OrderByBar.DESCENDING_ARROW = Y.Node.create(
        '<span class="sprite order-descending"></span>');

    Y.extend(OrderByBar, Y.Widget, {

        /**
         * Method used by the widget to fire custom event to
         * signal a new sorting is required.
         *
         * @method _fireSortEvent
         */
        _fireSortEvent: function() {
            var prefix = '';
            if (this.get('sort_order') === 'desc') {
                prefix = '-';
            }
            var sort_clause = prefix + this.get('active');
            this.set('sort_clause', sort_clause);
            var event_name = this.constructor.NAME + ':sort';
            Y.fire(event_name, sort_clause);
        },

        /**
         * Change the active_sort class from the previously active
         * node to the currently active node.
         *
         * @method _setActiveSortClassName
         */
        _setActiveSortClassName: function(preclick_sort_key) {
            var active = this.get('active');
            // We do not have to do anything if the button is already active.
            if (active !== preclick_sort_key) {
                var li_nodes = this.get('li_nodes');
                var len = li_nodes.length;
                var prev_li_id = 'sort-' + preclick_sort_key;
                var active_li_id = 'sort-' + active;
                var i,
                    li_node,
                    id;
                // Loop through the li_nodes we have and remove the
                // active-sort class from the previously active node
                // and add the class to the currently active node.
                for (i=0; i<len; i++) {
                    li_node = li_nodes[i];
                    id = li_node.get('id');
                    if (id === prev_li_id) {
                        li_node.removeClass('active-sort');
                    } else if (id === active_li_id) {
                        li_node.addClass('active-sort');
                    }
                }
            }
        },

        _setSortOrder: function(value, arrow_span) {
            if (value === 'asc') {
                arrow_span.setContent(this.constructor.ASCENDING_ARROW);
                arrow_span.addClass('asc');
                arrow_span.removeClass('desc');
                this.set('sort_order', 'asc');
            } else {
                arrow_span.setContent(this.constructor.DESCENDING_ARROW);
                arrow_span.addClass('desc');
                arrow_span.removeClass('asc');
                this.set('sort_order', 'desc');
            }
        },

        /**
         * Method used to update the arrows used in the display.
         * This will also update the widget's attributes to match
         * the new state.
         *
         * @method _updateSortArrows
         */
        _updateSortArrows: function(
            clicked_node, clicked_node_sort_key, preclick_sort_key) {
            // References to the span holding the arrow and the arrow HTML.
            var arrow_span = clicked_node.one('span');

            var is_active_sort_button = false;
            if (clicked_node_sort_key === preclick_sort_key) {
                is_active_sort_button = true;
            }
            if (is_active_sort_button) {
                // Handle the case where the button clicked is the current
                // active sort order.  We change sort directions for it.
                if (arrow_span.hasClass('desc')) {
                    this._setSortOrder('asc', arrow_span);
                } else {
                    this._setSortOrder('desc', arrow_span);
                }
            } else {
                // We have a different sort order clicked and need to
                // remove arrow from recently active sort button as
                // well as add an arrow to a new button.
                var old_active_sort_key = '#sort-' + preclick_sort_key;
                var old_active_li = this.get('contentBox').one(
                    old_active_sort_key);
                var old_arrow_span = old_active_li.one('span');
                old_arrow_span.setContent('');
                var pre_click_sort_order = this.get('sort_order');
                old_arrow_span.removeClass(pre_click_sort_order);
                // Update current li span arrow and set new sort order.
                var sort_order;
                Y.each(this.get('sort_keys'), function(key_data) {
                    if (key_data[0] === clicked_node_sort_key) {
                        sort_order = key_data[2];
                    }
                });
                this._setSortOrder(sort_order, arrow_span);
            }
        },

        /**
         * Get the sort key for a sort button.
         *
         * @method _sortKey
         */
        _sortKey: function(node) {
            return node.get('id').replace('sort-', '');
        },

        /**
         * Handle the click of one of the li nodes.
         *
         * @method _handleClick
         */
        _handleClick: function(clicked_node) {
            // Reverse from the node's ID to the sort key, i.e.
            // "sort-foo" gives us "foo" as the sort key.
            var clicked_node_sort_key = this._sortKey(clicked_node);
            // Get a reference to what was active before click and update
            // the "active" widget state.
            var preclick_sort_key = this.get('active');
            this.set('active', clicked_node_sort_key);
            this._setActiveSortClassName(preclick_sort_key);
            // Update display and fire events.
            this._updateSortArrows(
                clicked_node, clicked_node_sort_key, preclick_sort_key);
            this._fireSortEvent();
        },

        /**
         * Show or hide sort buttons.
         *
         * @method updateVisibility
         */
        updateVisibility: function(visibility) {
            var that = this;
            if (visibility === null) {
                Y.each(this.get('li_nodes'), function(li_node) {
                    li_node.show();
                });
            } else {
                Y.each(this.get('li_nodes'), function(li_node) {
                    var sort_key = that._sortKey(li_node);
                    if (visibility[sort_key]) {
                        li_node.show();
                    } else {
                        li_node.hide();
                    }
                });
            }
        },

        /**
         * Create the bar, the li nodes used for buttons, and
         * append to the page via the provided srcNode.
         *
         * @method renderUI
         */
        renderUI: function() {
            var orderby_ul = Y.Node.create('<ul></ul>');
            var keys = this.get('sort_keys');
            var len = keys.length;
            var li_nodes = [];
            var i,
                id,
                label,
                li_html,
                li_node,
                sort_order;
            for (i=0; i<len; i++) {
                id = keys[i][0];
                label = keys[i][1];
                li_html = Y.Lang.sub(
                    this.constructor.LI_TEMPLATE,
                    {li_id: 'sort-' + id, li_label: label});
                li_node = Y.Node.create(li_html);
                if (this.get('active') === id) {
                    li_node.addClass('active-sort');
                    sort_order = this.get('sort_order');
                    this._setSortOrder(sort_order, li_node.one('span'));
                }
                orderby_ul.appendChild(li_node);
                li_nodes.push(li_node);
            }
            this.set('li_nodes', li_nodes);
            var div = Y.Node.create('<div></div>');
            div.appendChild('<p>Order by:</p>');
            div.appendChild(orderby_ul);
            // Optionally, add a slot for any config widget to hook onto.
            if (this.get('config_slot')) {
                var config_div = Y.Node.create('<div></div>').addClass(
                    'config-widget');
                div.prepend(config_div);
                this.set('config_node', config_div);
            }
            this.get('srcNode').appendChild(div);
        },

        /**
         * Add click listeners to the li nodes used as buttons.
         *
         * @method bindUI
         */
        bindUI: function() {
            var li_nodes = this.get('li_nodes');
            var len = li_nodes.length;
            var that = this;
            var i,
                li_node;
            for (i=0; i<len; i++) {
                li_node = li_nodes[i];
                li_node.on('click', function(e) {
                    that._handleClick(this);
                });
            }
        }
    });

    var ordering = Y.namespace('lp.ordering');
    ordering.OrderByBar = OrderByBar;

}, '0.1', {'requires': ['widget']});
