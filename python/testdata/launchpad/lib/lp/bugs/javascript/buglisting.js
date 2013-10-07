/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Client-side rendering of bug listings.
 *
 * @module bugs
 * @submodule buglisting
 */

YUI.add('lp.bugs.buglisting', function (Y) {

    var module = Y.namespace('lp.bugs.buglisting');


    /**
     * Constructor.
     *
     * This is the model of the current batch, including the ordering,
     * position, and what fields are visibile.
     *
     * These values are stored in the History object, so that the browser
     * back/next buttons correctly adjust.  The system defaults for field
     * visibility are fixed, so they are stored directly on the object.
     *
     * Accepts a config containing:
     *  - field_visibility the requested field visibility as an associative
     *    array
     *  - field_visibility_defaults the system defaults for field visibility
     *    as an associative array.
     *  - batch_key: A string representing the position and ordering of the
     *    current batch, as returned by listing_navigator.get_batch_key
     */
    module.BugListingModel = Y.Base.create('buglisting-model', Y.Base, [],
    {
        /**
         * Initializer sets up the History object that stores most of the
         * model data.
         */
        initializer: function(config) {
            this.set('history', new Y.History({
                initialState: Y.merge(
                    config.field_visibility, {
                        batch_key: config.batch_key
                    }
                )
            }));
        },

        /**
         * Return the current field visibility, as an associative array.
         * Since the history contains field values that are not
         * field-visibility, use field_visibility_defaults to filter out
         * non-field-visibility values.
         */
        get_field_visibility: function () {
            var result = this.get('history').get();
            var key_source = this.get('field_visibility_defaults');
            Y.each(result, function(value, key) {
                if (!key_source.hasOwnProperty(key)){
                    delete result[key];
                }
            });
            return result;
        },

        /**
         * Set the field visibility, updating history.  Accepts an associative
         * array.
         */
        set_field_visibility: function(value) {
            this.get('history').add(value);
        },

        /**
         * Return the current batch key.
         */
        get_batch_key: function() {
            return this.get('history').get('batch_key');
        },

        /**
         * Set the current batch.  The batch_key and the query mapping
         * identifying the batch must be supplied.
         */
        set_batch: function(batch_key, query) {
            var url = '?' + Y.QueryString.stringify(query);
            this.get('history').addValue('batch_key', batch_key, {url: url});
        }
    }, {
        ATTRS: {
            field_visibility_defaults: { value: null },
            total: { value: null }
        }
    });

    /**
     * Constructor.
     * current_url is used to determine search params.
     * cache is the JSONRequestCache for the batch.
     * template is the template to use for rendering batches.
     * target is a YUI node to update when rendering batches.
     * navigation_indices is a YUI NodeList of nodes to update with the
     * current batch info.
     * io_provider is something providing the Y.io interface, typically used
     * for testing.  Defaults to Y.io.
     */
    module.BugListingNavigator = Y.Base.create(
        '', Y.lp.app.listing_navigator.ListingNavigator, [],
        {
            _bindUI: function () {
                Y.lp.app.inlinehelp.init_help();
            },

            /**
             * Return the model to use for rendering the batch.  This will
             * include updates to field visibility.
             */
            get_render_model: function(current_batch) {
                return Y.merge(
                    current_batch.mustache_model,
                    this.get('model').get_field_visibility());
            },

            make_model: function(batch_key, cache) {
                return new module.BugListingModel({
                    batch_key: batch_key,
                    total: cache.total,
                    field_visibility: cache.field_visibility,
                    field_visibility_defaults: cache.field_visibility_defaults
                });
            }
        },{});

    /**
     * Factory to return a BugListingNavigator for the given page.
     */
    module.BugListingNavigator.from_page = function () {
        var target = Y.one('#client-listing');
        if (Y.Lang.isNull(target)){
            return null;
        }
        var container = target.get('parentNode');
        var navigation_indices = Y.all('.batch-navigation-index');
        var pre_fetch = Y.lp.app.listing_navigator.get_feature_flag(
            'bugs.dynamic_bug_listings.pre_fetch');
        var navigator = new module.BugListingNavigator({
            current_url: window.location,
            cache: LP.cache,
            template: LP.mustache_listings,
            target: target,
            container: container,
            navigation_indices: navigation_indices,
            pre_fetch: Boolean(pre_fetch)
        });
        navigator.set('backwards_navigation',
                      container.all('.first,.previous'));
        navigator.set('forwards_navigation',
                      container.all('.last,.next'));
        navigator.clickAction('.first', navigator.first_batch);
        navigator.clickAction('.next', navigator.next_batch);
        navigator.clickAction('.previous', navigator.prev_batch);
        navigator.clickAction('.last', navigator.last_batch);
        navigator.update_navigation_links();
        return navigator;
    };

    /**
     * Helper view object for managing the buglisting code on the actual table
     * view.
     *
     * @class TableView
     * @extends Y.Base
     * @namespace lp.bugs.buglisting *
     */
    module.TableView = Y.Base.create('buglisting-tableview', Y.Base,
        [], {

        /**
         * Hook into the model events to aid in setting up history events.
         *
         * @method _bind_history
         * @private
         *
         */
        _bind_history: function () {
            var that = this;
            this.navigator.get('model').get('history').after(
                'change', function(e) {
                    // Only update the sort buttons if we've got a valid batch
                    // key.
                    if (Y.Object.hasKey(e.newVal, 'batch_key')) {
                        Y.lp.buglisting_utils.update_sort_button_visibility(
                            that.orderby,
                            e.newVal
                        );
                    }
                 }
            );
        },

        /**
         * Setup the order bar widget for use in the table view.
         *
         * @method _build_orderbar
         * @private
         *
         */
        _build_orderbar: function () {
            var that = this;
            that.orderby = new Y.lp.ordering.OrderByBar({
                srcNode: Y.one('#bugs-orderby'),
                sort_keys: this.get('sort_keys'),
                active: this.get('active_sort_key'),
                sort_order: this.get('sort_order'),
                config_slot: true
            });
            Y.on('orderbybar:sort', function(e) {
                that.navigator.first_batch(e);
            });
        },

        /**
         * We need to parse out the active key in case it indicates we should be
         * desc sorting, etc.
         *
         * @method _init_sort
         * @private
         *
         */
        _init_sort: function () {
            var active_key = this.get('active_sort_key');
            if (active_key.charAt(0) === '-') {
                this.set('active_sort_key',
                    active_key.substring(1, active_key.length));
                this.set('sort_order', 'desc');
            }
        },

        /**
         * If after init we still don't have any keys to sort on, we go with our
         * default sort key.
         *
         * @method _check_default_sort
         * @private
         *
         */
        _check_default_sort: function () {
            var active_key = this.get('active_key');
            var unknown_sort_key = true;

            Y.each(this.get('sort_keys'), function(sort_key) {
                if (sort_key[0] === active_key) {
                    unknown_sort_key = false;
                }
            });
            if (unknown_sort_key) {
                this.set('active_sort_key', this.get('default_sort'));
            }
        },

        /**
         * General YUI initializer setting up the tableview.
         *
         * @method intializer
         * @param {Object} cfg
         *
         */
        initializer: function (cfg) {
            this.navigator =
                Y.lp.bugs.buglisting.BugListingNavigator.from_page();

            if (Y.Lang.isNull(this.navigator)){
              return;
            }

            // now that we've set the values from the LP.cache, let's process it
            this._init_sort();
            // if we don't have sort values, we might want to set some defaults
            this._check_default_sort();
            this._build_orderbar();
            this._bind_history();
        },

        /**
         * Handle any UI binding, building for the tableview.
         *
         * @method render
         *
         */
        render: function () {
            var that = this;

            // Exit from render if we do not have a navigator.
            // XXX: deryck 2012-03-20 Bug #960476
            // This module is not tested, nor is it easily testable,
            // so tests for this return were not added.  This code
            // needs refactoring to be able to test this kind of stuff
            // more easily.
            if (!Y.Lang.isValue(this.navigator)) {
                return;
            }

            var field_visibility =
                that.navigator.get('model').get_field_visibility();

            that.orderby.always_display = ['title'];
            that.orderby.render();

            // The listing util needs to be called AFTER the orderby widget is
            // rendered or the little gear icon has no home and ends up in DOM
            // limbo land.
            var config_node = that.orderby.get('config_node');
            that.list_util = new Y.lp.buglisting_utils.BugListingConfigUtil({
                srcNode: config_node,
                model: that.navigator.get('model')
            });
            that.list_util.render();

            Y.on('buglisting-config-util:fields-changed', function(e) {
                that.navigator.change_fields(
                    that.list_util.get('field_visibility'));
            });

            // The advanced search page contains sort options that have
            // no related data fields we can display. If a user has selected
            // such a sort order, this sort option should always be visible.
            var check_visibility =
                field_visibility['show_' + this.get('active_sort_key')];
            if (check_visibility === undefined) {
                that.orderby.always_display.push(active_sort_key);
            }

            Y.lp.buglisting_utils.update_sort_button_visibility(
                 that.orderby,
                 field_visibility
            );
        }
    }, {
        ATTRS: {
            /**
             * @attribute default_sort
             * @default importance
             * @type String
             *
             */
            default_sort: {
                value: 'importance'
            },

            /**
             * @attribute active_sort_key
             * @default undefined
             * @type string
             *
             */
            active_sort_key: {

            },

            /**
             * @attribute sort_keys
             * @default undefined
             * @type Array
             *
             */
            sort_keys: {
            },

            /**
             * @attribute sort_order
             * @default asc
             * @type String
             *
             */
            sort_order: {
                value: 'asc'
            }
        }
    });

}, '0.1', {
    'requires': [
        'history', 'node', 'lp.app.listing_navigator', 'lp.app.inlinehelp',
        'lp.app.indicator', 'lp.ordering', 'lp.buglisting_utils'
    ]
});
