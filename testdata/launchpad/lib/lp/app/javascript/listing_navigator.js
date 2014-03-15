/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Client-side listing rendering from batches.
 *
 * @module app
 * @submodule listing_navigator
 */

YUI.add('lp.app.listing_navigator', function(Y) {

var module = Y.namespace('lp.app.listing_navigator');

function empty_nodelist() {
    return new Y.NodeList([]);
}

/**
 * Rewrite all nodes with navigation classes so that they are hyperlinks.
 * Content is retained.
 */
function linkify_navigation(container_node) {
    Y.each(['previous', 'next', 'first', 'last'], function(class_name) {
        container_node.all('.' + class_name).each(function(node) {
            var new_node = Y.Node.create('<a href="#"></a>');
            new_node.addClass(class_name);
            new_node.setContent(node.getContent());
            node.replace(new_node);
        });
    });
}

/**
 * If there is no context (say /bugs/+bugs) we need to generate a weblink for
 * the lp.client to use for things. This is a helper to take the current url
 * and try to generate a likely web_link value to build a url off of.
 */
function likely_web_link() {
    var url = location.href;
    var cut_at = url.indexOf('+');

    // make sure we trim the trailing / off the web link we generate
    return url.substr(0, cut_at - 1);
}


/**
 * Constructor.
 *
 * A simplistic model of the current batch.
 *
 * These values are stored in the History object, so that the browser
 * back/next buttons correctly adjust.
 *
 * Accepts a config containing:
 *  - batch_key: A string representing the position and ordering of the
 *    current batch, as returned by listing_navigator.get_batch_key
 */
module.SimpleListingModel = Y.Base.create('simple-listing-model', Y.Base, [], {

    /**
     * Initializer sets up the History object that stores most of the
     * model data.
     */
    initializer: function(config) {
        this.set('history', new Y.History({
            initialState: {
                    batch_key: config.batch_key
                }
        }));
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
        batch_key: {
            value: null
        },
        history: {
            value: null
        },
        total: {
            value: null
        }
    }
});


/**
 * Constructor.
 * cache is the JSONRequestCache for the batch.
 * template is the template to use for rendering batches.
 * target is a YUI node to update when rendering batches.
 * navigation_indices is a YUI NodeList of nodes to update with the current
 * batch info.
 * io_provider is something providing the Y.io interface, typically used for
 * testing.  Defaults to Y.io.
 */
module.ListingNavigator = function(config) {
    module.ListingNavigator.superclass.constructor.apply(this, arguments);
};


module.ListingNavigator.ATTRS = {
    batches: {value: {}},
    batch_info_template: {value: '<strong>{{start}}</strong> &rarr; ' +
        '<strong>{{end}}</strong> of {{total}} results'},
    backwards_navigation: {valueFn: empty_nodelist},
    forwards_navigation: {valueFn: empty_nodelist},
    io_provider: {value: null},
    pre_fetch: {value: false},
    navigation_indices: {valueFn: empty_nodelist},
    target: {value: null},
    container: {
        value: null,
        getter: function(value) {
            if (!Y.Lang.isValue(value)) {
                return this.get('target');
            }
            return value;
        }
    },
    template: {value: null}
};

Y.extend(module.ListingNavigator, Y.Base, {
    initializer: function(config) {
        var lp_client = new Y.lp.client.Launchpad();
        var cache = lp_client.wrap_resource(null, config.cache);
        var batch_key;
        var template = config.template;

        var search_params = this.get_search_params(config);
        this.set('search_params', search_params);
        batch_key = this.handle_new_batch(cache);
        this.set('model', this.make_model(batch_key, cache));

        // init the indicator plugin on the target
        // it defaults to invisible, so safe init
        this.indicator = new Y.lp.app.indicator.OverlayIndicator({
            target: config.target.get('parentNode'),
            success_action: Y.lp.app.indicator.actions.scroll_to_target
        });

        this.indicator.render();

        this.pre_fetch_batches();
        // Work around mustache.js bug 48 "Blank lines are not preserved."
        // https://github.com/janl/mustache.js/issues/48
        if (Y.Lang.isValue(template)) {
            template = template.replace(/\n/g, '&#10;');
        }
        this.set('template', template);

        // Wire up the default history change processing if supported by the
        // model.
        var history = this.get('model').get('history');
        if (Y.Lang.isValue(history)) {
            this.get('model').get('history').after(
                'change', this.default_history_changed, this);
        }
        linkify_navigation(this.get('container'));
    },

    /**
     * Default event handler for history:change events.
     */
    default_history_changed: function(e) {
        if (e.newVal.hasOwnProperty('batch_key')) {
            var batch_key = e.newVal.batch_key;
            var batch = this.get('batches')[batch_key];
            this.pre_fetch_batches();
            this.render();
            this._bindUI();
        }
        else {
            // Handle Chrom(e|ium)'s initial popstate.
            this.get('model').get('history').replace(e.prevVal);
        }
    },

    get_failure_handler: function(fetch_only) {
        var error_handler = new Y.lp.client.ErrorHandler();
        error_handler.showError = Y.bind(
            Y.lp.app.errors.display_error, window, null);
        if (!fetch_only){
            error_handler.clearProgressUI = Y.bind(
                this.indicator.error, this.indicator
            );
        }
        return error_handler.getFailureHandler();
    },

    /**
     * Call the callback when a node matching the selector is clicked.
     *
     * The node is also marked up appropriately.
     * Scoped at the parentNode of the target.
     */
    clickAction: function(selector, callback) {
        var nodes = this.get('target').get('parentNode').all(selector);
        nodes.on('click', function(e) {
            e.halt();
            // If the target link is disabled, we want to ignore the click.
            var link = e.target;
            if (link.get('tagName').toLowerCase() !== 'a' ) {
                link = link.ancestor('a');
            }
            if (!Y.Lang.isValue(link) || link.hasClass('invalid-link')) {
                return;
            }
            callback.call(this);
        }, this);
        nodes.addClass('js-action');
    },

    /**
     * Retrieve the current batch for rendering purposes.
     */
    get_current_batch: function() {
        return this.get('batches')[this.get('model').get_batch_key()];
    },

    /**
     * Handle a previously-unseen batch by storing it in the cache.
     */
     handle_new_batch: function(batch) {
        var batch_key = module.get_batch_key(batch);
        this.get('batches')[batch_key] = batch;
        return batch_key;
    },

    /**
     * If the supplied batch is adjacent to the current batch, find an alias
     * of one of the batches and store it.
     *
     * A batch has two major aliases because "forwards" may be true or false.
     * Either the ajacent batch will have an alias for the current batch, or
     * the current batch will have an alias for the adjacent batch.
     */
    dealias_batches: function(batch) {
        var batch_a_keys = module.get_batch_key_list(batch);
        var batch_b_keys = module.get_batch_key_list(
            this.get_current_batch());
        var aliases = module.find_batch_alias(batch_a_keys, batch_b_keys);
        if (Y.Lang.isNull(aliases)){
            return;
        }
        var alias_batch = this.get('batches')[aliases[0]];
        if (Y.Lang.isValue(alias_batch)){
            this.get('batches')[aliases[1]] = alias_batch;
        } else {
            alias_batch = this.get('batches')[aliases[1]];
            if (Y.Lang.isValue(alias_batch)){
                this.get('batches')[aliases[0]] = alias_batch;
            }
        }
    },

    /**
     * Return the model to use for rendering the batch.
     */
    get_render_model: function(current_batch) {
        return current_batch.mustache_model;
    },

    _bindUI: function () {
        // Sub-classes override this.
    },

    render: function() {
        this.render_content();
        this.render_navigation();
    },


    /**
     * Render listings via Mustache.
     *
     * If model is supplied, it is used as the data for rendering the
     * listings.  Otherwise, LP.cache.mustache_model is used.
     *
     * The template is always LP.mustache_listings.
     */
    render_content: function() {
        var current_batch = this.get_current_batch();
        var content = Y.lp.mustache.to_html(
            this.get('template'), this.get_render_model(current_batch));
        this.get('target').setContent(content);
    },

    /**
     * Return the number of items in the specified batch.
     * @param batch
     */
    _batch_size: function(batch) {
        return batch.mustache_model.items.length;
    },

    /**
     * Render the navigation elements.
     */
    render_navigation: function() {
        var current_batch = this.get_current_batch();
        var total = this.get('model').get('total');
        var batch_info = Y.lp.mustache.to_html(
            this.get('batch_info_template'), {
            start: current_batch.start + 1,
            end: current_batch.start + this._batch_size(current_batch),
            total: total
        });
        this.get('navigation_indices').setContent(batch_info);
        this.update_navigation_links();
    },

    has_prev: function() {
        return !Y.Lang.isNull(this.get_current_batch().prev);
    },

    has_next: function() {
        return !Y.Lang.isNull(this.get_current_batch().next);
    },

    /**
     * Enable/disable navigation links as appropriate.
     */
    update_navigation_links: function() {
        this.get('backwards_navigation').toggleClass(
            'invalid-link', !this.has_prev());
        this.get('forwards_navigation').toggleClass(
            'invalid-link', !this.has_next());
    },

    update_from_new_model: function(query, fetch_only, model) {
        var batch_key = this.handle_new_batch(model);
        this.dealias_batches(model);
        if (fetch_only) {
            return;
        }
        this.get('model').set('total', model.total);
        this.update_from_cache(query, batch_key);
    },

    /**
     * A shim to use the data of an LP.cache to render the listings and
     * cache their data.
     *
     * query is a mapping of query variables generated by get_batch_query.
     * batch_key is the key generated by get_batch_key for the model.
     */
    update_from_cache: function(query, batch_key) {
        this.get('model').set_batch(batch_key, query);
        this.indicator.success();
    },

    /**
     * Return the query vars to use for the specified batch.
     * This includes the search params and the batch selector.
     */
    get_batch_query: function(config) {
        var query = Y.merge(
            this.get('search_params'), {orderby: config.order_by});
        if (Y.Lang.isValue(config.memo)) {
            query.memo = config.memo;
        }
        if (Y.Lang.isValue(config.start)) {
            query.start = config.start;
        }
        if (config.forwards !== undefined && !config.forwards) {
            query.direction = 'backwards';
        }
        return query;
    },


    /**
     * Pre-fetch adjacent batches.
     */
    pre_fetch_batches: function() {
        var that=this;
        if (!this.get('pre_fetch')){
            return;
        }
        Y.each(this.get_pre_fetch_configs(), function(config) {
            config.fetch_only = true;
            that.update(config);
        });
    },


    /**
     * Update the display to the specified batch.
     *
     * If the batch is cached, it will be used immediately.  Otherwise, it
     * will be retrieved and cached upon retrieval.
     */
    update: function(config) {
        if (!config.fetch_only){
            this.indicator.setBusy();
        }

        var key = module.get_batch_key(config);
        var cached_batch = this.get('batches')[key];
        var query = this.get_batch_query(config);

        if (Y.Lang.isValue(cached_batch)) {
            if (config.fetch_only){
                return;
            }
            this.update_from_cache(query, key);
        }
        else {
            this.load_model(query, config.fetch_only);
        }
    },

    /**
     * Update the navigator to display the last batch.
     */
    last_batch: function() {
        var current_batch = this.get_current_batch();
        this.update({
            forwards: false,
            memo: "",
            start: current_batch.last_start,
            order_by: current_batch.order_by
        });
    },

    first_batch_config: function(order_by) {
        if (order_by === undefined) {
            order_by = this.get_current_batch().order_by;
        }
        return {
            forwards: true,
            memo: null,
            start: 0,
            order_by: order_by
        };
    },

    /**
     * Update the navigator to display the first batch.
     *
     * The order_by defaults to the current ordering, but may be overridden.
     */
    first_batch: function(order_by) {
        this.update(this.first_batch_config(order_by));
    },

    /**
     * Update the navigator to display the next batch.
     */
    next_batch: function() {
        var config = module.next_batch_config(this.get_current_batch());
        if (config === null){
            return;
        }
        this.update(config);
    },
    /**
     * Update the navigator to display the previous batch.
     */
    prev_batch: function() {
        var config = module.prev_batch_config(this.get_current_batch());
        if (config === null){
            return;
        }
        this.update(config);
    },
    /**
     * Generate a list of configs to pre-fetch.
     */
    get_pre_fetch_configs: function() {
        var configs = [];
        var next_batch_config = module.next_batch_config(
            this.get_current_batch());
        if (next_batch_config !== null){
            configs.push(next_batch_config);
        }
        return configs;
    },

    /**
     * Load the specified batch via ajax.  Display & cache on load.
     *
     * query is the query string for the URL, as a mapping.  (See
     * get_batch_query).
     */
    load_model: function(query, fetch_only) {
        var load_model_config = {
            on: {
                success: Y.bind(
                    this.update_from_new_model, this, query, fetch_only),
                failure: this.get_failure_handler(fetch_only)
            }
        };
        var context = this.get_current_batch().context;
        var view_name = this.get_current_batch().view_name;

        if (Y.Lang.isValue(this.get('io_provider'))) {
            load_model_config.io_provider = this.get('io_provider');
        }

        if (!context) {
            // try to see if there is no context we can fake the object in
            // order to pass through
            context = new Y.lp.client.Entry(
                new Y.lp.client.Launchpad({
                    io_provider: load_model_config.io_provider
                }), {
                    'web_link': likely_web_link()
                }
            );
        }

        Y.lp.client.load_model(
            context, view_name, load_model_config, query);
    },

    make_model: function(batch_key, cache) {
        return new module.SimpleListingModel({
            batch_key: batch_key,
            total: cache.total
        });
    },

    get_search_params: function(config) {
        var search_params = Y.lp.app.listing_navigator.get_query(
            config.current_url);
        delete search_params.start;
        delete search_params.memo;
        delete search_params.direction;
        delete search_params.orderby;
        return search_params;
    }
});


/**
 * Return the value for a given feature flag in the current scope.
 * Only flags declared as "related_features" on the view are available.
 */
module.get_feature_flag = function(flag_name) {
    return LP.cache.related_features[flag_name].value;
};


/**
 * Get the key for the specified batch, for use in the batches mapping.
 */
module.get_batch_key = function(config) {
    return JSON.stringify([config.order_by, config.memo, config.forwards,
                           config.start]);
};


/**
 * Return the query of the specified URL in structured form.
 */
module.get_query = function(url) {
    var querystring = Y.lp.get_url_query(url);
    return Y.QueryString.parse(querystring);
};


/**
 * Return a mapping describing the batch previous to the current batch.
 */
module.prev_batch_config = function(batch) {
    if (!Y.Lang.isValue(batch.prev)){
        return null;
    }
    return {
        forwards: false,
        memo: batch.prev.memo,
        start: batch.prev.start,
        order_by: batch.order_by
    };
};


/**
 * Return a mapping describing the batch after the current batch.
 */
module.next_batch_config = function(batch) {
    if (!Y.Lang.isValue(batch.next)) {
        return null;
    }
    return {
        forwards: true,
        memo: batch.next.memo,
        start: batch.next.start,
        order_by: batch.order_by
    };
};

/**
 * Return a list of the batch keys described in this batch: prev, current and
 * next.  If next or prev is null, the corresponding batch key will be null.
 */
module.get_batch_key_list = function(batch) {
    var prev_config = module.prev_batch_config(batch);
    var next_config = module.next_batch_config(batch);
    var keys = [];
    if (Y.Lang.isNull(prev_config)){
        keys.push(null);
    } else {
        keys.push(module.get_batch_key(prev_config));
    }
    keys.push(module.get_batch_key(batch));
    if (Y.Lang.isNull(next_config)){
        keys.push(null);
    } else {
        keys.push(module.get_batch_key(next_config));
    }
    return keys;
};


/**
 * Find an alias between the two supplied batches, if they are adjacent.
 * Returns a list of two batch keys that should be considered equivalent.
 * If the supplied batches are not adjacent, returns null.
 */
module.find_batch_alias = function(batch_a, batch_b) {
    var prev_batch;
    var next_batch;
    if (batch_a[2] === batch_b[1] || batch_a[1] === batch_b[0]){
        prev_batch = batch_a;
        next_batch = batch_b;
    } else if (batch_b[2] === batch_a[1] || batch_b[1] === batch_a[0]){
        prev_batch = batch_b;
        next_batch = batch_a;
    }
    else {
        return null;
    }
    if (prev_batch[1] !== next_batch[0]){
        return [prev_batch[1], next_batch[0]];
    } else {
        return [prev_batch[2], next_batch[1]];
    }
};

}, "0.1", {
    "requires": [
        "base", "node", 'history', 'lp.client', 'lp.app.errors',
        'lp.app.indicator', 'lp.mustache'
    ]
});
