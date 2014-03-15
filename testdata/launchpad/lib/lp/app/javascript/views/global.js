/*
 * Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Global View handler for Launchpad
 *
 * @module lp.views.Global
 * @namespace lp.views
 * @module global
 */
YUI.add('lp.views.global', function (Y) {

    var ns = Y.namespace('lp.views'),
        ui = Y.namespace('lp.ui'),
        info_type = Y.namespace('lp.app.information_type');

    /**
     * Provides a Y.View that controls all of the things that need handling on
     * every single request. All code currently in the base-layout-macros
     * should eventually moved into here to be loaded via the render() method.
     * Events bound as required, etc.
     *
     * @class Global
     * @extends Y.View
     */
    ns.Global = Y.Base.create('lp-views-global', Y.View, [], {
        _events: [],

        /**
         * Watch for page level events in all pages.
         *
         * @method _bind_events
         */
        _bind_events: function () {
            var that = this;

            // Watch for any changes in information type.
            this._events.push(Y.on(info_type.EV_ISPUBLIC, function (ev) {
                // Remove the banner if there is one.
                if (that._private_banner) {
                    that._private_banner.hide();
                    that._private_banner.destroy(true);
                    that._private_banner = null;
                    // XXX: Bug #1076074
                    var body = Y.one('body');
                    body.addClass('public');
                }
            }));

            // If the information type is changed to private, and we don't
            // currently have a privacy banner, then create a new one and set
            // it up.
            this._events.push(Y.on(info_type.EV_ISPRIVATE, function (ev) {
                // Create a Private banner if there is not currently one.
                if (!that._private_banner) {
                    that._private_banner = new ui.banner.PrivateBanner({
                        content: ev.text
                    });

                    // There is no current container for the banner since
                    // we're creating it on the fly.
                    var container = Y.Node.create('<div>');

                    // XXX: Bug #1076074
                    var body = Y.one('body');
                    body.removeClass('public');
                    that._private_banner.render(container);
                    // Only append the content to the DOM after the rest is
                    // one to avoid any repaints on the browser end.
                    body.prepend(container);
                    that._private_banner.show();
                } else {
                    // The banner is there but we need to update text.
                    that._private_banner.set('content', ev.text);
                }
            }));
        },

        /**
         * Clean up the view and its event bindings when destroyed.
         *
         * @method _destroy
         * @param {Event} ev
         * @private
         */
        _destroy: function (ev) {
            var index;
            for (index in this._events) {
                event = this._events[index];
                event.detach();
            }
        },

        _init_banners: function () {
            var that = this;

            // On page load the banner container already exists. This is so
            // that the height of the page is already determined.
            var is_beta = Y.one('.beta_banner_container');
            if (is_beta) {
                that._beta_banner = new ui.banner.BetaBanner({
                    features: LP.cache.related_features
                });
                that._beta_banner.render(is_beta);
                // We delay the show until the page is ready so we get our
                // pretty css3 animation that distracts the user a bit.
                Y.after('load', function (ev) {
                    that._beta_banner.show();
                });
            }

            // On page load the banner container already exists. This is so
            // that the height of the page is already determined.
            var is_private = Y.one('.private_banner_container');
            if (is_private) {
                that._private_banner = new ui.banner.PrivateBanner();
                that._private_banner.render(is_private);
                // We delay the show until the page is ready so we get our
                // pretty css3 animation that distracts the user a bit.
                Y.on('load', function (ev) {
                    that._private_banner.show();
                });
            }
        },

        initialize: function (cfg) {},

        render: function () {
            this._bind_events();
            this.on('destroy', this._destroy, this);
            this._init_banners();
        }

    }, {
        ATTRS: {

        }
    });

}, '0.1', {
    requires: ['base', 'view', 'lp.ui.banner', 'lp.app.information_type']
});
