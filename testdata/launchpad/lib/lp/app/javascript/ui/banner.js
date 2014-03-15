/*
 * Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Notification banner widget
 *
 * @module lp.ui.banner
 * @namespace lp.ui
 * @module banner
 */
YUI.add('lp.ui.banner', function (Y) {

    var ns = Y.namespace('lp.ui.banner');

    // GLOBALS
    ns.PRIVATE = 'private';
    ns.BETA = 'beta';

    /**
     * Banner widget base class
     *
     * This is the base Banner, you're supposed to supply some message data to
     * generate the banner in the proper method.
     *
     * This banner provides all shared functionality between the Privacy and
     * Beta banners.
     *
     * @class Banner
     * @extends Y.Widget
     *
     */
    ns.Banner = Y.Base.create('banner', Y.Widget, [], {
        template: [
            '<div class="banner">',
                '<span class="badge {{ banner_type }}">{{ badge_text }}</span>',
                '<span class="banner-content">{{{ content }}}</span>',
            '</div>'
        ].join(''),


        /**
         * Bind events that our widget supports such as closing the banner.
         *
         * We also watch the destroy event to clean up side effect css we
         * created.
         *
         * @method bindUI
         */
        bindUI: function () {
            this.on('destroy', function (ev) {
                // XXX: Bug #1076074
                var body = Y.one('body');
                var banner_type = this.get('banner_type');
                body.removeClass(banner_type);

                // Remove any container the page might have provided for us to
                // start out with.
                var container_class = '.' + banner_type + '_banner_container';
                var container = Y.one(container_class);
                if (container) {
                    Y.one(container_class).remove();
                }
            });

            this.after('contentChange', function () {
                this.renderUI();
            });
        },

        /**
         * Default initialize method.
         *
         * @method initialize
         * @param {Object} cfg
         */
        initialize: function (cfg) {
        },

        /**
         * Widget render method to generate the html of the widget.
         *
         * @method renderUI
         */
        renderUI: function () {
            var contentBox = this.get('contentBox');
            contentBox.addClass(this.get('banner_type'));
            var html = Y.lp.mustache.to_html(this.template, this.getAttrs());
            contentBox.setHTML(html);

            // XXX: Bug #1076074
            // Needs to get cleaned up. Only applies to the global
            // banners and not to other ones which we're working to allow.
            // This is currently required because the #locationbar is
            // absolutely located and needs to be moved as banners change.
            var body = Y.one('body');
            body.addClass(this.get('banner_type'));

            if (this.get('visible')) {
                this.show();
            }
        },

        /**
         * We need to override show so that we force a browser repaint which
         * allows our CSS3 animation to run. Otherwise the browser sees we
         * added new DOM elements and jumps straight to the finished animation
         * point.
         *
         * @method show
         */
        show: function () {
            var _node = this.get('boundingBox')._node;
            var getComputedStyle = document.defaultView.getComputedStyle;
            _node.style.display = getComputedStyle(_node).display;
            return this.set('visible', true);
        }

    }, {
        ATTRS: {
            /**
             * Instead of a sprite we might have text such as the Beta banner.
             *
             * @attribute badge_text
             * @default undefined
             * @type {String}
             */
            badge_text: {},

            /**
             * The Banner is meant to house some message to the user provided
             * by this content. It can be html and is not escaped for that
             * reason.
             *
             * @attribute content
             * @default undefined
             * @type {String}
             */
            content: {},

            /**
             * This is listed to help aid in discovery of how the container
             * node for the widget is determined. It's passed into the
             * render() method and the Widget constructs itself inside of
             * there.
             *
             * @attribute boundingBox
             * @default undefined
             * @type {Node}
             */
            boundingBox: {

            },

            /**
             * Much of the Widget is determined by the type of banner it is.
             * See the constants defined PRIVATE and BETA for two known types.
             * If you set this manually you'll be able to provide custom
             * styling as required because the type is used as a css class
             * property.
             *
             * @attribute banner_type
             * @default undefined
             * @type {String}
             */
            banner_type: {},

            /**
             * Start out as not visible which should render as opacity 0, then
             * we update it and it animates due to our css3.
             *
             * @attribute visible
             * @default false
             * @type {Bool}
             */
            visible: {
                value: false
            }
        }
    });

    /**
     * Beta Banner widget
     *
     * This is the Beta feature banner which needs to know about the title and
     * url of the feature to construct the content correctly. Features are
     * meant to be matched to the current LP.cache.related_features data
     * available.
     *
     * @class BetaBanner
     * @extends Banner
     *
     */
    ns.BetaBanner = Y.Base.create('banner', ns.Banner, [], {

    }, {
        ATTRS: {
            /**
             * @attribute badge_text
             * @default "BETA!"
             * @type {String}
             */
            badge_text: {
                value: 'BETA!'
            },

            /**
             * The content for the beta banner is constructed from hard coded
             * content and the list of enabled beta features currently
             * relevant to the page.
             *
             * @attribute content
             * @default {generated}
             * @type {String}
             */
            content: {
                getter: function () {
                    var content = "Some parts of this page are in beta:&nbsp;";
                    var key;
                    // We need to process the features to build the features
                    // that apply.
                    var features = this.get('features');
                    for (key in features) {
                       if (features.hasOwnProperty(key)) {
                           var obj = features[key];
                           if (obj.is_beta) {
                               content = content + [
                                 '<span class="beta-feature">',
                                 obj.title,
                                 '&nbsp;<a class="info-link" href="',
                                 obj.url + '">(read more)</a>',
                                 '</span>'
                               ].join('');
                           }
                        }
                    }
                    return content;
                }
            },

            /**
             * features is a nested object of the beta features going. See
             * LP.cache.related_features for the list of features. We only
             * want those related features that are in beta.
             * Ex: {
             *     disclosure.private_projects.enabled: {
             *         is_beta: true,
             *         title: "",
             *         url: "http://blog.ld.net/general/private-projects-beta",
             *         value: "true"
             *     }
             * }
             * @attribute features
             * @default {}
             * @type {Object}
             */
            features: {},

            /**
             * Manually force the banner type so users don't need to set it.
             * This is a beta banner class.
             *
             * @attribute banner_type
             * @default BETA
             * @type {String}
             */
            banner_type: {
                value: ns.BETA
            }

        }
    });

    /**
     * Private Banner widget
     *
     * This is the Private feature banner which is pretty basic.
     *
     * Note that this doesn't automatically follow the information type code.
     * Nor does it listen to the choice widgets and try to update. It's purely
     * meant to function as told to do so. Most of the work around making sure
     * the banner shows and works properly is in the View code in global.js.
     *
     * @class PrivateBanner
     * @extends Banner
     *
     */
    ns.PrivateBanner = Y.Base.create('banner', ns.Banner, [], {

    }, {
        ATTRS: {
            badge_text: {
                value: ''
            },

            content: {
                value: 'The information on this page is private.'
            },

            /**
             * Manually force the banner type so users don't need to set it.
             * This is a beta banner class.
             *
             * @attribute banner_type
             * @default BETA
             * @type {String}
             */
            banner_type: {
                value: ns.PRIVATE
            }
        }
    });

}, '0.1', {
    requires: ['base', 'node', 'anim', 'widget', 'lp.mustache', 'yui-log']
});
