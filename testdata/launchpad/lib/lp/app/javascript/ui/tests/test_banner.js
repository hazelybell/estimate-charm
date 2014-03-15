/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI.add('lp.ui.banner.test', function (Y) {

    var tests = Y.namespace('lp.ui.banner.test');
    tests.suite = new Y.Test.Suite('ui.banner Tests');

    var ns = Y.lp.ui.banner;

    tests.suite.add(new Y.Test.Case({
        name: 'ui.banner_tests',

        setUp: function () {
            this.container = Y.one('#fixture');
        },

        tearDown: function () {
            this.container.empty();
        },

        test_library_exists: function () {
            Y.Assert.isObject(Y.lp.ui.banner,
                "Could not locate the lp.ui.banner module");
        },

        test_render: function () {
            var b = new ns.Banner();
            b.render(this.container);

            var banners = Y.all('.banner');
            Y.Assert.areEqual(
                1,
                banners._nodes.length,
                'We have one banner node');

            // The banner should make sure it's in the container as well.
            var contained_banners = Y.all('#fixture .banner');
            Y.Assert.areEqual(
                1,
                contained_banners._nodes.length,
                'Banner node is placed.');
        },

        test_render_content: function () {
            var msg = 'This is a banner message. Fear me.',
                b = new ns.Banner({
                    content: msg
                });

            b.render(this.container);

            var banner = Y.one('.banner');
            Y.Assert.areEqual(
                msg,
                banner.one('.banner-content').get('text')
            );
        },

        test_render_private_type: function () {
            var msg = 'Private!',
                b = new ns.Banner({
                    content: msg,
                    banner_type: ns.PRIVATE
                });

            b.render(this.container);

            var banner = Y.one('.banner');
            Y.Assert.areEqual(
                msg,
                banner.one('.banner-content').get('text'),
                'The banner should have the private message.'
            );

            var badge = banner.one('.badge');

            Y.Assert.isTrue(
                badge.hasClass('private'),
                'The badge should have a private class on it.');

        },

        test_render_beta_type: function () {
            var msg = 'BETA!',
                b = new ns.Banner({
                    content: msg,
                    banner_type: ns.BETA
                });

            b.render(this.container);

            var banner = Y.one('.banner');
            Y.Assert.areEqual(
                msg,
                banner.one('.banner-content').get('text'),
                'The banner should have the beta message.'
            );

            var badge = banner.one('.badge');

            Y.Assert.isTrue(
                badge.hasClass('beta'),
                'The badge should have a beta class on it.');
        },

        test_render_badge_text: function () {
            // We can set the badge to contain text.
            var badge = 'BETA!',
                b = new ns.Banner({
                    badge_text: badge,
                    banner_type: ns.BETA
                });

            b.render(this.container);
            var banner = Y.one('.banner');
            Y.Assert.areEqual(
                badge,
                banner.one('.badge').get('text'),
                'The badge should have the beta message.'
            );
        },

        test_banner_text_update: function () {
            // The banner should update the rendered text when the content
            // ATTR is changed.
            var msg = 'This is a banner message. Fear me.',
                b = new ns.Banner({
                    content: msg
                });

            b.render(this.container);

            var banner = Y.one('.banner');
            Y.Assert.areEqual(
                msg,
                banner.one('.banner-content').get('text')
            );

            // Now change the content on the widget and check again.
            var new_msg = 'Updated me!';
            b.set('content', new_msg);
            banner = Y.one('.banner');
            Y.Assert.areEqual(
                new_msg,
                banner.one('.banner-content').get('text')
            );
        }
    }));


    tests.suite.add(new Y.Test.Case({
        name: 'ui.beta_banner_tests',

        setUp: function () {
            this.container = Y.one('#fixture');
        },

        tearDown: function () {
            this.container.empty();
        },

        test_base_beta_banner: function () {
            // The beta banner is auto set to the right type, has the right
            // badge text.
            var badge = 'BETA!',
                msg = 'are in beta:',
                b = new ns.BetaBanner({
                });

            b.render(this.container);
            var banner = Y.one('.banner');
            Y.Assert.areEqual(
                badge,
                banner.one('.badge').get('text'),
                'The badge should have the beta message.'
            );

            Y.Assert.areEqual(
                ns.BETA,
                b.get('banner_type'),
                'The banner should be the right type.'
            );

            Y.Assert.areNotEqual(
                -1,
                banner.one('.banner-content').get('text').indexOf(msg),
                'The badge should have beta content.'
            );
        },

        test_beta_features: function () {
            // The features fed to the banner effect display of the messages.
            var features = {
                private_projects: {
                    is_beta: true,
                    title: "Private Projects",
                    url: "http://blog.ld.net/general/private-projects-beta",
                    value: "true"
                },
                test_projects: {
                    is_beta: true,
                    title: "Test Projects",
                    url: "http://blog.ld.net/general/private-projects-beta",
                    value: "true"
                },
                no_beta: {
                    is_beta: false,
                    title: "Better not see me",
                    url: "http://blog.ld.net/general/private-projects-beta",
                    value: "true"
                }
            };

            var b = new ns.BetaBanner({
                    features: features
            });

            b.render(this.container);

            var banner = Y.one('.banner'),
                banner_content = banner.one('.banner-content').get('text');

            Y.Assert.areNotEqual(
                -1,
                banner_content.indexOf(features.private_projects.title),
                'The private projects feature should be displayed.'
            );

            Y.Assert.areNotEqual(
                -1,
                banner_content.indexOf(features.test_projects.title),
                'Also test projects since we support multiple features.'
            );

            Y.Assert.areEqual(
                -1,
                banner_content.indexOf(features.no_beta.title),
                'But not no beta since we only support beta features.'
            );
        }
    }));


    tests.suite.add(new Y.Test.Case({
        name: 'ui.private_banner_tests',

        setUp: function () {
            this.container = Y.one('#fixture');
        },

        tearDown: function () {
            this.container.empty();
        },

        test_base_private_banner: function () {
            // The private banner is auto set to the right type, has the right
            // badge text.
            var badge = '',
                msg = 'page is private',
                b = new ns.PrivateBanner({
                });

            b.render(this.container);
            var banner = Y.one('.banner');
            Y.Assert.areEqual(
                badge,
                banner.one('.badge').get('text'),
                'The badge should be empty'
            );

            Y.Assert.areEqual(
                ns.PRIVATE,
                b.get('banner_type'),
                'The banner should be the right type.'
            );

            Y.Assert.areNotEqual(
                -1,
                banner.one('.banner-content').get('text').indexOf(msg),
                'The badge should have a private warning.'
            );
        }
    }));

}, '0.1', {
    requires: ['test', 'lp.testing.helpers', 'lp.ui.banner']
});
