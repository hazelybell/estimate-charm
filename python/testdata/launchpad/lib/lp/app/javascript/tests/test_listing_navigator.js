/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.app.listing_navigator.test', function (Y) {
    var module = Y.lp.app.listing_navigator;
    var TestListingNavigator = Y.Base.create('test-listing-navigator',
                                             module.ListingNavigator, [], {
        update_from_cache: function() {
            this.constructor.superclass.update_from_cache.apply(this,
                                                                arguments);
            this.pre_fetch_batches();
            this.render();
        },
        get_search_params: function(config) {
            return config.search_params;
        }
    }, {});

    var get_navigator = function(url, config) {
        var mock_io = new Y.lp.testing.mockio.MockIo();
        if (Y.Lang.isUndefined(url)){
            url = '';
        }
        if (Y.Lang.isUndefined(config)){
            config = {};
        }
        var target = config.target;
        if (!Y.Lang.isValue(target)){
            var target_parent = Y.Node.create('<div></div>');
            target = Y.Node.create('<div "id=#client-listing"></div>');
            target_parent.appendChild(target);
        }
        lp_cache = {
            context: {
                resource_type_link: 'http://foo_type',
                web_link: 'http://foo/bar'
            },
            view_name: '+items',
            next: {
                memo: 467,
                start: 500
            },
            prev: {
                memo: 457,
                start: 400
            },
            forwards: true,
            order_by: 'foo',
            memo: 457,
            start: 450,
            last_start: 23,
            field_visibility: {},
            field_visibility_defaults: {}
        };
        if (config.no_next){
            lp_cache.next = null;
        }
        if (config.no_prev){
            lp_cache.prev = null;
        }
        var navigator_config = {
            current_url: url,
            cache: lp_cache,
            io_provider: mock_io,
            pre_fetch: config.pre_fetch,
            target: target,
            template: ''
        };
        return new TestListingNavigator(navigator_config);
    };


    var tests = Y.namespace('lp.app.listing_navigator.test');
    tests.suite = new Y.Test.Suite('Listing Navigator Tests');

    tests.suite.add(new Y.Test.Case({
        name: 'render',

        setUp: function() {
            this.target = Y.Node.create('<div></div>').set(
                'id', 'client-listing');
            Y.one('body').appendChild(this.target);
        },

        tearDown: function() {
            Y.one('#fixture').setContent('');
            this.target.remove();
            delete this.target;
            Y.lp.testing.helpers.reset_history();
        },

        get_render_navigator: function(container) {
            var lp_cache = {
                mustache_model: {
                    items: [{foo: 'bar', show_foo: true}]
                },
                next: null,
                prev: null,
                start: 5,
                total: 256,
                field_visibility: {show_foo: true},
                field_visibility_defaults: {show_foo: false}
            };
            var template = "{{#items}}{{#show_foo}}{{foo}}{{/show_foo}}" +
                "{{/items}}";
            var navigator =  new TestListingNavigator({
                cache: lp_cache,
                template: template,
                target: this.target,
                container: container
            });
            var index = Y.Node.create(
                '<div><strong>3</strong> &rarr; <strong>4</strong>' +
                ' of 512 results</div>');
            navigator.get('navigation_indices').push(index);
            navigator.get('backwards_navigation').push(
                Y.Node.create('<div></div>'));
            navigator.get('forwards_navigation').push(
                Y.Node.create('<div></div>'));
            return navigator;
        },
        test_render: function() {
            // Rendering should work with #client-listing supplied.
            var navigator = this.get_render_navigator();
            navigator.render();
            Y.Assert.areEqual('bar', navigator.get('target').getContent());
        },
        /**
         * update_navigation_links should disable "previous" and "first" if
         * there is no previous batch (i.e. we're at the beginning.)
         */
        test_update_navigation_links_disables_backwards_navigation_if_no_prev:
        function() {
            var navigator = this.get_render_navigator();
            var action = navigator.get('backwards_navigation').item(0);
            navigator.update_navigation_links();
            Y.Assert.isTrue(action.hasClass('invalid-link'));
        },
        /**
         * update_navigation_links should enable "previous" and "first" if
         * there is a previous batch (i.e. we're not at the beginning.)
         */
        test_update_navigation_links_enables_backwards_navigation_if_prev:
        function() {
            var navigator = this.get_render_navigator();
            var action = navigator.get('backwards_navigation').item(0);
            action.addClass('inactive');
            navigator.get_current_batch().prev = {
                start: 1, memo: 'pi'
            };
            navigator.update_navigation_links();
            Y.Assert.isFalse(action.hasClass('invalid-link'));
        },
        /**
         * update_navigation_links should disable "next" and "last" if there is
         * no next batch (i.e. we're at the end.)
         */
        test_update_navigation_links_disables_forwards_navigation_if_no_next:
        function() {
            var navigator = this.get_render_navigator();
            var action = navigator.get('forwards_navigation').item(0);
            navigator.update_navigation_links();
            Y.Assert.isTrue(action.hasClass('invalid-link'));
        },
        /**
         * update_navigation_links should enable "next" and "last" if there is a
         * next batch (i.e. we're not at the end.)
         */
        test_update_navigation_links_enables_forwards_navigation_if_next:
                function() {
            var navigator = this.get_render_navigator();
            var action = navigator.get('forwards_navigation').item(0);
            action.addClass('inactive');
            navigator.get_current_batch().next = {
                start: 1, memo: 'pi'
            };
            navigator.update_navigation_links();
            Y.Assert.isFalse(action.hasClass('invalid-link'));
        },
        /**
         * Creating a navigator should convert previous, next, first last into
         * hyperlinks, while retaining the original content.
         */
        test_linkify_navigation: function() {
            Y.one('#fixture').setContent(
                '<span id="notme" class="first"></span>' +
                '<div id="bugs-table-listing">' +
                '<span class="previous">PreVious</span>' +
                '<span class="next">NeXt</span>' +
                '<span class="first">FiRST</span>' +
                '<span class="last">lAst</span>' +
                '</div>');
            this.target = Y.one('#bugs-table-listing');
            this.get_render_navigator(this.target);
            function checkNav(selector, content) {
                var nodelist = Y.all(selector);
                nodelist.each(function (node) {
                    if (node.get('id') !== 'notme') {
                        Y.Assert.areEqual('a',
                            node.get('tagName').toLowerCase());
                        Y.Assert.areEqual(content, node.getContent());
                        Y.Assert.areEqual('#',
                            node.get('href').substr(-1, 1));
                    } else {
                        Y.Assert.areEqual('span',
                            node.get('tagName').toLowerCase(),
                            'Ignore nodes outside of the bug listing table');
                    }
                });
            }
            checkNav('.previous', 'PreVious');
            checkNav('.next', 'NeXt');
            checkNav('.first', 'FiRST');
            checkNav('.last', 'lAst');
        },

        /**
         * Render should update the navigation_indices with the result info.
         */
        test_update_navigation_links_indices: function() {
            var navigator = this.get_render_navigator();
            var index = navigator.get('navigation_indices').item(0);
            Y.Assert.areEqual(
                '<strong>3</strong> \u2192 <strong>4</strong> of 512 results',
                index.getContent());
            navigator.render();
            Y.Assert.areEqual(
                '<strong>6</strong> \u2192 <strong>6</strong> of 256 results',
                index.getContent());
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'first_batch',

        setUp: function() {
            this.target = Y.Node.create('<div></div>').set(
                'id', 'client-listing');
            Y.one('body').appendChild(this.target);
            Y.config.win.history.state = {};
        },

        tearDown: function() {
            this.target.remove();
            delete this.target;
            Y.lp.testing.helpers.reset_history();
        },

        /**
         * Return a ListingNavigator ordered by 'intensity'
         */
        get_intensity_listing: function() {
            mock_io = new Y.lp.testing.mockio.MockIo();
            lp_cache = {
                context: {
                    resource_type_link: 'http://foo_type',
                    web_link: 'http://foo/bar'
                },
                view_name: '+items',
                mustache_model: {
                    foo: 'bar',
                    items: []
                },
                next: null,
                prev: null,
                field_visibility: {},
                field_visibility_defaults: {}
            };

            var navigator = new TestListingNavigator({
                current_url:
                    "http://yahoo.com?start=5&memo=6&direction=backwards",
                cache: lp_cache,
                template: "<ol>" + "{{#item}}<li>{{name}}</li>{{/item}}</ol>",
                target: this.target,
                io_provider: mock_io
            });
            navigator.first_batch('intensity');
            Y.Assert.areEqual('', navigator.get('target').getContent());
            mock_io.last_request.successJSON({
                context: {
                    resource_type_link: 'http://foo_type',
                    web_link: 'http://foo/bar'
                },
                mustache_model:
                {
                    item: [
                    {name: 'first'},
                    {name: 'second'}],
                    items: []
                },
                order_by: 'intensity',
                start: 0,
                forwards: true,
                memo: null,
                next: null,
                prev: null
            });
            return navigator;
        },

        test_first_batch: function() {
            /* first_batch retrieves a listing for the new ordering and
             * displays it */
            var navigator = this.get_intensity_listing();
            var mock_io = navigator.get('io_provider');
            Y.Assert.areEqual('<ol><li>first</li><li>second</li></ol>',
                navigator.get('target').getContent());
            Y.Assert.areEqual('/bar/+items/++model++?orderby=intensity&start=0',
                mock_io.last_request.url);
        },

        test_first_batch_uses_cache: function() {
            /* first_batch will use the cached value instead of making a
             * second AJAX request. */
            var navigator = this.get_intensity_listing();
            Y.Assert.areEqual(1, navigator.get('io_provider').requests.length);
            navigator.first_batch('intensity');
            Y.Assert.areEqual(1, navigator.get('io_provider').requests.length);
        },

        test_io_error: function() {
            var overlay_node;
            var navigator = this.get_intensity_listing();
            navigator.first_batch('failure');
            navigator.get('io_provider').failure();
            overlay_node = Y.one('.yui3-lazr-formoverlay-errors');
            Y.Assert.isTrue(Y.Lang.isValue(overlay_node));
        }
    }));


    tests.suite.add(new Y.Test.Case({
        name: 'Batch caching',

        setUp: function() {
            this.target = Y.Node.create('<div></div>').set(
                'id', 'client-listing');
            Y.one('body').appendChild(this.target);
        },

        tearDown: function() {
            this.target.remove();
            delete this.target;
            Y.lp.testing.helpers.reset_history();
        },

        test_update_from_new_model_caches: function() {
            /*
             * update_from_new_model caches the settings in the
             * module.batches.
             */
            var lp_cache = {
                context: {
                    resource_type_link: 'http://foo_type',
                    web_link: 'http://foo/bar'
                },
                mustache_model: {
                    foo: 'bar'
                },
                next: null,
                prev: null,
                field_visibility: {},
                field_visibility_defaults: {}
            };
            var template = "<ol>" +
                "{{#item}}<li>{{name}}</li>{{/item}}</ol>";
            var navigator = new TestListingNavigator({
                current_url: window.location,
                cache: lp_cache,
                template: template,
                target: this.target
            });
            var key = module.get_batch_key({
                order_by: "intensity",
                memo: 'memo1',
                forwards: true,
                start: 5,
                target: this.target
            });
            var batch = {
                order_by: 'intensity',
                memo: 'memo1',
                forwards: true,
                start: 5,
                next: null,
                prev: null,
                mustache_model: {
                    item: [
                        {name: 'first'},
                        {name: 'second'}
                    ],
                    items: ['a', 'b', 'c']
                }};
            var query = navigator.get_batch_query(batch);
            navigator.update_from_new_model(query, true, batch);
            Y.lp.testing.assert.assert_equal_structure(
                batch, navigator.get('batches')[key]);
        },
        /**
         * get_batch_key returns a JSON-serialized list.
         */
        test_get_batch_key: function() {
            var key = module.get_batch_key({
                order_by: 'order_by1',
                memo: 'memo1',
                forwards: true,
                target: this.target,
                start: 5});
            Y.Assert.areSame('["order_by1","memo1",true,5]', key);
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'get_query',

        test_get_query: function() {
            // get_query returns the query portion of a URL in structured form.
            var query = module.get_query('http://yahoo.com?me=you&a=b&a=c');
            Y.lp.testing.assert.assert_equal_structure(
                {me: 'you', a: ['b', 'c']}, query);
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'get_batch_url',

        setUp: function() {
            this.target = Y.Node.create('<div></div>').set(
                'id', 'client-listing');
            Y.one('body').appendChild(this.target);
        },

        tearDown: function() {
            this.target.remove();
            delete this.target;
            Y.lp.testing.helpers.reset_history();
        },

        /**
         * get_batch_query accepts the order_by param.
         */
        test_get_batch_query_orderby: function() {
            var navigator = new TestListingNavigator({
                search_params: {
                    param: 1
                },
                target: this.target,
                cache: {next: null, prev: null}
            });
            var query = navigator.get_batch_query({order_by: 'importance'});
            Y.Assert.areSame('importance', query.orderby);
            Y.Assert.areSame(1, query.param);
        },
        /**
         * get_batch_query accepts the memo param.
         */
        test_get_batch_query_memo: function() {
            var navigator = new TestListingNavigator({
                search_params: {
                    param: 'foo'
                },
                target: this.target,
                cache: {next: null, prev: null}
            });
            var query = navigator.get_batch_query({memo: 'pi'});
            Y.Assert.areSame('pi', query.memo);
            Y.Assert.areSame('foo', query.param);
        },
        /**
         * When memo is null, query.memo is undefined.
         */
        test_get_batch_null_memo: function() {
            var navigator = new TestListingNavigator({
                search_params: {},
                cache: {next: null, prev: null},
                target: this.target
            });
            var query = navigator.get_batch_query({memo: null});
            Y.Assert.areSame(undefined, query.memo);
        },
        /**
         * If 'forwards' is true, direction does not appear.
         */
        test_get_batch_query_forwards: function() {
            var navigator = new TestListingNavigator({
                search_params: {
                    param: 'pi'
                },
                cache: {next: null, prev: null},
                target: this.target
            });
            var query = navigator.get_batch_query({forwards: true});
            Y.Assert.areSame('pi', query.param);
            Y.Assert.areSame(undefined, query.direction);
        },
        /**
         * If 'forwards' is false, direction is set to backwards.
         */
        test_get_batch_query_backwards: function() {
            var navigator = new TestListingNavigator({
                search_params: {
                    param: 'pi'
                },
                cache: {next: null, prev: null},
                target: this.target
            });
            var query = navigator.get_batch_query({forwards: false});
            Y.Assert.areSame('pi', query.param);
            Y.Assert.areSame('backwards', query.direction);
        },
        /**
         * If start is provided, it overrides existing values.
         */
        test_get_batch_query_start: function() {
            var navigator = new TestListingNavigator({
                search_params: {},
                cache: {next: null, prev:null},
                target: this.target
            });
            var query = navigator.get_batch_query({});
            Y.Assert.areSame(undefined, query.start);
            query = navigator.get_batch_query({start: 1});
            Y.Assert.areSame(1, query.start);
            query = navigator.get_batch_query({start: null});
            Y.lp.testing.assert.assert_equal_structure({}, query);
        }
    }));


    tests.suite.add(new Y.Test.Case({
        name: 'navigation',

        setUp: function() {
            this.target = Y.Node.create('<div></div>').set(
                'id', 'client-listing');
            Y.one('body').appendChild(this.target);
        },

        tearDown: function() {
            this.target.remove();
            delete this.target;
            Y.lp.testing.helpers.reset_history();
        },

        test_model_uses_view_name: function() {
            var navigator = get_navigator('', {target: this.target});
            navigator.get_current_batch().view_name = '+funitems';
            navigator.load_model({});
            Y.Assert.areSame(
                '/bar/+funitems/++model++',
                navigator.get('io_provider').last_request.url);
        },

        /**
         * last_batch uses memo="", start=navigator.current_batch.last_start,
         * direction=backwards, orderby=navigator.current_batch.order_by.
         */
        test_last_batch: function() {
            var navigator = get_navigator(
                '?memo=pi&direction=backwards&start=57', {target: this.target});
            navigator.last_batch();
            Y.Assert.areSame(
                '/bar/+items/++model++?orderby=foo&memo=&start=23&' +
                'direction=backwards',
                navigator.get('io_provider').last_request.url);
        },

        /**
         * first_batch omits memo and direction, start=0,
         * orderby=navigator.current_batch.order_by.
         */
        test_first_batch: function() {
            var navigator = get_navigator(
                '?memo=pi&start=26', {target: this.target});
            navigator.first_batch();
            Y.Assert.areSame(
                '/bar/+items/++model++?orderby=foo&start=0',
                navigator.get('io_provider').last_request.url);
        },

        /**
         * next_batch uses values from current_batch.next +
         * current_batch.ordering.
         */
        test_next_batch: function() {
            var navigator = get_navigator(
                '?memo=pi&start=26', {target: this.target});
            navigator.next_batch();
            Y.Assert.areSame(
                '/bar/+items/++model++?orderby=foo&memo=467&start=500',
                navigator.get('io_provider').last_request.url);
        },

        /**
         * Calling next_batch when there is none is a no-op.
         */
        test_next_batch_missing: function() {
            var navigator = get_navigator(
                '?memo=pi&start=26', {no_next: true, target: this.target});
            navigator.next_batch();
            Y.Assert.areSame(
                null, navigator.get('io_provider').last_request);
        },

        /**
         * prev_batch uses values from current_batch.prev + direction=backwards
         * and ordering=current_batch.ordering.
         */
        test_prev_batch: function() {
            var navigator = get_navigator(
                '?memo=pi&start=26', {target: this.target});
            navigator.prev_batch();
            Y.Assert.areSame(
                '/bar/+items/++model++?orderby=foo&memo=457&start=400&' +
                'direction=backwards',
                navigator.get('io_provider').last_request.url);
        },

        /**
         * Calling prev_batch when there is none is a no-op.
         */
        test_prev_batch_missing: function() {
            var navigator = get_navigator(
                '?memo=pi&start=26',
                {no_prev: true, no_next: true, target: this.target});
            navigator.prev_batch();
            Y.Assert.areSame(
                null, navigator.get('io_provider').last_request);
        },

        /**
         * Verify we get a reasonable default context if there is no context
         * available as is the case with the BugsBugTaskSearchListingView.
         */
        test_default_context: function () {
            var navigator = get_navigator('', {target: this.target});
            // now remove the context
            var batch = navigator.get_current_batch();
            delete batch.context;

            navigator.get_current_batch().view_name = '+funitems';
            navigator.load_model({});

            // the start of the url used will be whatever the current
            // location.href is for the window object. We can make sure we did
            // get a nicely generated url though by checking they end built
            // correctly.
            var generated_url = navigator.get('io_provider').last_request.url;

            Y.Assert.areSame(
                '+funitems/++model++',
                generated_url.substr(generated_url.indexOf('+')));
        }

    }));

    tests.suite.add(new Y.Test.Case({
        name: "pre-fetching batches",
        setUp: function() {
            this.target = Y.Node.create('<div></div>').set(
                'id', 'client-listing');
            Y.one('body').appendChild(this.target);
        },
        tearDown: function() {
            this.target.remove();
            delete this.target;
            Y.lp.testing.helpers.reset_history();
        },
        /**
         * get_pre_fetch_configs should return a config for the next batch.
         */
        test_get_pre_fetch_configs: function() {
            var navigator = get_navigator('', {target: this.target});
            var configs = navigator.get_pre_fetch_configs();
            var batch_keys = [];
            Y.each(configs, function(value) {
                batch_keys.push(module.get_batch_key(value));
            });
            Y.Assert.areSame('["foo",467,true,500]', batch_keys[0]);
            Y.Assert.areSame(1, batch_keys.length);
        },

        /**
         * get_pre_fetch_configs should return an empty list if no next batch.
         */
        test_get_pre_fetch_configs_no_next: function() {
            var navigator = get_navigator(
                '', {no_next: true, target: this.target});
            var configs = navigator.get_pre_fetch_configs();
            var batch_keys = [];
            Y.each(configs, function(value) {
                batch_keys.push(module.get_batch_key(value));
            });
            Y.Assert.areSame(0, batch_keys.length);
        },

        get_pre_fetch_navigator: function(config) {
            var navigator = get_navigator('', config);
            var batch = navigator.get_current_batch();
            batch.next = {memo: 57, start: 56};
            batch.order_by = '';
            return navigator;
        },

        /**
         * Calling pre_fetch_batches should produce a request for the next
         * batch.
         */
        test_pre_fetch_batches: function() {
            var navigator = this.get_pre_fetch_navigator({target: this.target});
            var io_provider = navigator.get('io_provider');
            navigator.set('pre_fetch', true);
            Y.Assert.isNull(io_provider.last_request);
            navigator.pre_fetch_batches();
            Y.Assert.areSame(
                io_provider.last_request.url,
                '/bar/+items/++model++?orderby=&memo=57&start=56');
        },

        /**
         * Calling pre_fetch_batches should not produce a request for the next
         * batch if Navigator.get('pre_fetch') is false.
         */
        test_pre_fetch_disabled: function() {
            var last_url;
            var navigator = this.get_pre_fetch_navigator({target: this.target});
            navigator.pre_fetch_batches();
            Y.Assert.areSame(null, navigator.get('io_provider').last_request);
        },

        /**
         * Initialization does a pre-fetch.
         */
        test_pre_fetch_on_init: function() {
            var navigator = get_navigator(
                '', {pre_fetch: true, target:this.target});
            var last_url = navigator.get('io_provider').last_request.url;
            Y.Assert.areSame(
                last_url,
                '/bar/+items/++model++?orderby=foo&memo=467&start=500');
        },
        /**
         * update_from_new_model does a pre-fetch.
         */
        test_pre_fetch_on_update_from_new_model: function() {
            var navigator = get_navigator('', {target: this.target});
            var io_provider = navigator.get('io_provider');
            var lp_client = new Y.lp.client.Launchpad();
            var batch = lp_client.wrap_resource(null, {
                context: {
                    resource_type_link: 'http://foo_type',
                    web_link: 'http://foo/bar'
                },
                view_name: '+items',
                order_by: 'baz',
                memo: 'memo1',
                next: {
                    memo: "pi",
                    start: 314
                },
                prev: null,
                forwards: true,
                start: 5,
                mustache_model: {
                    item: [
                        {name: 'first'},
                        {name: 'second'}
                    ],
                    items: ['a', 'b', 'c']
                }});
            Y.Assert.isNull(io_provider.last_request);
            navigator.set('pre_fetch', true);
            navigator.update_from_new_model({}, false, batch);
            Y.Assert.areSame(
                io_provider.last_request.url,
                '/bar/+items/++model++?orderby=baz&memo=pi&start=314');
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: "Test indicators",

        tearDown: function () {
            Y.lp.testing.helpers.reset_history();
        },

        /**
         * Update starts showing the pending indicator
         */
        test_show_on_update: function() {
            var navigator = get_navigator();
            navigator.update({});
            Y.Assert.isTrue(navigator.indicator.get('visible'));
        },
        /**
         * A fetch-only update starts ignores the pending indicator
         */
        test_ignore_on_fetch_only_update: function() {
            var navigator = get_navigator();
            navigator.update({fetch_only: true});
            Y.Assert.isFalse(navigator.indicator.get('visible'));
        },
        /**
         * A successful IO operation clears the pending indicator.
         */
        test_hide_on_success: function() {
            var navigator = get_navigator();
            navigator.update({});
            navigator.get('io_provider').last_request.successJSON({
                mustache_model: {items: []},
                next: null,
                prev: null
            });
            Y.Assert.isFalse(navigator.indicator.get('visible'));
        },
        /**
         * A successful fetch-only IO operation ignores the pending indicator.
         */
        test_no_hide_on_fetch_only_success: function() {
            var navigator = get_navigator();
            navigator.indicator.setBusy();
            navigator.update({fetch_only: true});
            navigator.get('io_provider').last_request.successJSON({
                mustache_model: {items: []},
                next: null,
                prev: null
            });
            Y.Assert.isTrue(navigator.indicator.get('visible'));
        },
        /**
         * A failed IO operation hides the pending indicator.
         */
        test_hide_on_failure: function() {
            var navigator = get_navigator();
            navigator.update({});
            navigator.get('io_provider').failure();
            Y.Assert.isFalse(navigator.indicator.get('visible'));
        },
        /**
         * A failed fetch-only IO operation does not hide the pending indicator.
         */
        test_no_hide_on_fetch_only_failure: function() {
            var navigator = get_navigator();
            navigator.indicator.setBusy();
            navigator.update({fetch_only: true});
            navigator.get('io_provider').failure();
            Y.Assert.isTrue(navigator.indicator.get('visible'));
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: "Find batch aliases",

        test_get_batch_key_list: function() {
            var keys = module.get_batch_key_list({
                prev: null,
                next:null,
                memo: 'pi',
                start: -1,
                forwards: true,
                order_by: 'ordering'
            });
            Y.ArrayAssert.itemsAreSame(
                [null, '["ordering","pi",true,-1]', null], keys);
            keys = module.get_batch_key_list({
                prev: {
                    memo: "pi",
                    start: -2
                },
                next: {
                    memo: "e",
                    start: 0
                },
                memo: 'pi',
                start: -1,
                forwards: true,
                order_by: 'ordering'
            });
            Y.ArrayAssert.itemsAreSame([
                '["ordering","pi",false,-2]',
                '["ordering","pi",true,-1]',
                '["ordering","e",true,0]'], keys);
        },

        /* Detect batch aliases for forward movement (next). */
        test_find_batch_alias_moving_forward: function() {
            var prev_batch = ['a', 'b', 'c'];
            var next_batch = ["b'", 'c', 'd'];
            var result = module.find_batch_alias(prev_batch, next_batch);
            Y.Assert.areSame(result[0], 'b');
            Y.Assert.areSame(result[1], "b'");
            result = module.find_batch_alias(next_batch, prev_batch);
            Y.Assert.areSame(result[0], 'b');
            Y.Assert.areSame(result[1], "b'");
        },

        /* Detect batch aliases for backward movement (prev). */
        test_find_batch_alias_moving_backward: function() {
            var prev_batch = ['a', 'b', 'c'];
            var next_batch = ['b', "c'", 'd'];
            var result = module.find_batch_alias(prev_batch, next_batch);
            Y.Assert.areSame(result[0], 'c');
            Y.Assert.areSame(result[1], "c'");
            result = module.find_batch_alias(next_batch, prev_batch);
            Y.Assert.areSame(result[0], 'c');
            Y.Assert.areSame(result[1], "c'");
        },

        /* Do not detect aliases if batches are unrelated */
        test_find_batch_alias_unrelated: function() {
            var prev_batch = ['a', 'b', 'c'];
            var next_batch = ['d', 'e', 'f'];
            var result = module.find_batch_alias(next_batch, prev_batch);
            Y.Assert.isNull(result);
        },

        /**
         * When dealias_batches is called on the next batch, the current batch
         * is re-added to the batches mapping, under its alias from the next
         * batch.
         */
        test_dealias_batches_next: function() {
            var navigator = get_navigator();
            var next_batch = {
                memo: 467,
                start: 500,
                order_by: 'foo',
                forwards: true,
                prev: {
                    memo: 467,
                    start: 450
                },
                next: null
            };
            var prev_batch_config = module.prev_batch_config(next_batch);
            var prev_batch_key = module.get_batch_key(
                prev_batch_config);
            navigator.dealias_batches(next_batch);
            Y.Assert.areSame(
                navigator.get('batches')[prev_batch_key],
                navigator.get_current_batch()
            );
            Y.Assert.areNotSame(
                prev_batch_key, navigator.get('model').get_batch_key());
        },
        /**
         * When dealias_batches is called on the previous batch, the current
         * batch is re-added to the batches mapping, under its alias from the
         * previous batch.
         */
        test_dealias_batches_prev: function() {
            var navigator = get_navigator();
            var prev_batch = {
                memo: 457,
                start: 400,
                order_by: 'foo',
                forwards: false,
                next: {
                    memo: 467,
                    start: 450
                },
                prev: null
            };
            var next_batch_config = module.next_batch_config(prev_batch);
            var next_batch_key = module.get_batch_key(
                next_batch_config);
            navigator.dealias_batches(prev_batch);
            Y.Assert.areSame(
                navigator.get('batches')[next_batch_key],
                navigator.get_current_batch()
            );
            Y.Assert.areNotSame(
                next_batch_key, navigator.get('model').get_batch_key());
        }
    }));

    tests.suite.add(new Y.Test.Case({
        name: 'browser history',

        setUp: function() {
            this.target = Y.Node.create('<div></div>').set(
                'id', 'client-listing');
            Y.one('body').appendChild(this.target);
        },

        tearDown: function() {
            this.target.remove();
            delete this.target;
            Y.lp.testing.helpers.reset_history();
        },

        /**
         * Update from cache generates a change event for the specified batch.
         */
        test_update_from_cache_generates_event: function() {
            var navigator = get_navigator('', {target: this.target});
            var e = null;
            navigator.get('model').get('history').on('change',
                                                     function(inner_e) {
                e = inner_e;
            });
            navigator.get('batches')['some-batch-key'] = {
                mustache_model: {
                    items: []
                },
                next: null,
                prev: null
            };
            navigator.update_from_cache({foo: 'bar'}, 'some-batch-key');
            Y.Assert.areEqual('some-batch-key', e.newVal.batch_key);
            Y.Assert.areEqual('?foo=bar', e._options.url);
        },

        /**
         * When a change event is emitted, the relevant batch becomes the
         * current batch and is rendered.
         */
        test_change_event_renders_cache: function() {
            var navigator = get_navigator('', {target: this.target});
            var batch = {
                mustache_model: {
                    items: [],
                    foo: 'bar'
                },
                next: null,
                prev: null
            };
            navigator.set('template', '{{foo}}');
            navigator.get('batches')['some-batch-key'] = batch;
            navigator.get('model').get('history').addValue(
                'batch_key', 'some-batch-key');
            Y.Assert.areEqual(batch, navigator.get_current_batch());
            Y.Assert.areEqual('bar', navigator.get('target').getContent());
        }
    }));

}, '0.1', {
    'requires': ['base', 'test', 'lp.testing.helpers', 'test-console',
        'lp.app.listing_navigator', 'lp.testing.mockio', 'lp.testing.assert',
        'history']
});
