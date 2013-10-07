/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.views.global.test', function (Y) {
    var tests = Y.namespace('lp.views.global.test');
    var info_type = Y.namespace('lp.app.information_type');
    var ns = Y.lp.views;

    tests.suite = new Y.Test.Suite('lp.views.global test');
    tests.suite.add(new Y.Test.Case({
        name: 'lp.views.global',

        setUp: function () {
            this.container = Y.one('#fixture');
            window.LP = {
                cache: {
                    related_features: {
                        private_projects: {
                            is_beta: true,
                            title: "Private Projects",
                            url: "http://blog.ld.net/general/beta",
                            value: "true"
                        }
                    },
                    information_type_data: {
                        PUBLIC: {
                            value: 'PUBLIC', name: 'Public',
                            is_private: false, order: 1,
                            description: 'Public Description'
                        },
                        EMBARGOED: {
                            value: 'EMBARGOED', name: 'Embargoed',
                            is_private: true, order: 2,
                            description: 'Something embargoed'
                        },
                        PROPRIETARY: {
                            value: 'PROPRIETARY', name: 'Proprietary',
                            is_private: true, order: 3,
                            description: 'Private Description'
                        }
                    }
                }
            };
        },

        tearDown: function () {
            this.container.empty();
        },

        test_library_exists: function () {
            Y.Assert.isObject(ns.Global,
                "Could not locate the lp.views.global module");
        },

        test_basic_render: function () {
            // Nothing is currently rendered out by default.
            var view = new ns.Global();
            view.render();

            Y.Assert.areEqual(
                '',
                this.container.get('innerHTML'),
                'The container is still empty.');
            view.destroy();
        },

        test_beta_banner: function () {
            // If we've prepped on load a beta banner will auto appear.
            var banner_container = Y.Node.create('<div/>');
            banner_container.addClass('beta_banner_container');
            this.container.append(banner_container);
            var view = new ns.Global();
            view.render();

            // We have to wait until after page load event fires to test
            // things out.
            var banner_node = Y.one('.banner');
            Y.Assert.isObject(
                banner_node,
                'The container has a new banner node in there.');

            view.destroy();
        },

        test_privacy: function () {
            var beta_container = Y.Node.create('<div/>');
            var private_container = Y.Node.create('<div/>');

            beta_container.addClass('beta_banner_container');
            private_container.addClass('private_banner_container');

            this.container.append(beta_container);
            this.container.append(private_container);
            var view = new ns.Global();
            view.render();

            // We have to wait until after page load event fires to test
            // things out.
            var banner_nodes = Y.all('.banner');
            Y.Assert.areEqual(
                2,
                banner_nodes._nodes.length,
                'We should have two banners rendered.');

            view.destroy();
        },

        test_privacy_banner_from_event: function () {
            // We can also get a privacy banner via a fired event.
            // This is hard coded to the <body> tag so we have to do some
            // manual clean up here.
            var view = new ns.Global();
            view.render();

            var msg = 'Testing Global';
            Y.fire(info_type.EV_ISPRIVATE, {
                text: msg
            });

            var banner = Y.one('.banner');
            var banner_text = banner.one('.banner-content').get('text');
            Y.Assert.areNotEqual(
                -1,
                banner_text.indexOf(msg),
                'The event text is turned into the banner content');

           // Manually clean up.
           Y.one('.yui3-banner').remove(true);
           view.destroy();
        },

        test_banner_updates_content: function () {
            // If we change our privacy information type the banner needs to
            // update the content to the new text value from the event.
            var view = new ns.Global();
            view.render();

            var msg = 'Testing Global';
            Y.fire(info_type.EV_ISPRIVATE, {
                text: msg
            });

            var updated_msg = 'Updated content';
            Y.fire(info_type.EV_ISPRIVATE, {
                text: updated_msg
            });

            var banner = Y.one('.banner');
            var banner_text = banner.one('.banner-content').get('text');
            Y.Assert.areNotEqual(
                -1,
                banner_text.indexOf(updated_msg),
                'The banner updated content to the second event message.');

           // Manually clean up.
           Y.one('.yui3-banner').remove(true);
           view.destroy();

        }
    }));

}, '0.1', {
    requires: ['test', 'event-simulate', 'node-event-simulate',
               'lp.app.information_type', 'lp.views.global']
});
