/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * A module which provides the BatchNavigatorHooks class. This class hooks
 * into the batch navigation links to provide ajax based navigation.
 */
YUI.add('lp.app.batchnavigator', function(Y) {

var namespace = Y.namespace('lp.app.batchnavigator');

function BatchNavigatorHooks(config, io_provider) {
    if (!Y.Lang.isValue(config.contentBox)) {
        Y.error("No contentBox specified in config.");
    }
    // The contentBox node contains the table and other HTML elements which
    // will be replaced each time a navigation operation completes.
    this.contentBox = Y.one(config.contentBox);
    if (this.contentBox === null ) {
        Y.error("Invalid contentBox '" + config.contentBox +
                "' specified in config.");
    }

    // LP client and error handling.
    this.lp_client = new Y.lp.client.Launchpad({io_provider: io_provider});
    this.error_handler = new Y.lp.client.ErrorHandler();
    this.error_handler.clearProgressUI = Y.bind(this.hideSpinner, this);
    this.error_handler.showError = Y.bind(function (error_msg) {
        Y.lp.app.errors.display_error(undefined, error_msg);
    }, this);

    // We normally make an XHR call to the same batch navigation links as
    // rendered but we also support getting data from a different specific
    // view defined on the content object.
    if (config.view_link !== undefined) {
        var link_url_base =
            LP.cache.context.self_link + '/' + config.view_link;
        this.link_url_base = link_url_base.replace('/api/devel', '');
    }

    // We add a query parameter called 'batch_request' to the URL so that the
    // view knows it needs to only render the table data. We support more than
    // one ajax batch navigator on a page and this parameter is used to tell
    // the view which one was clicked.
    this.batch_request_value = 'True';
    if (config.batch_request_value !== undefined) {
        this.batch_request_value = config.batch_request_value;
    }

    // We support invoked a user defined function after results have been
    // refreshed.
    this.post_refresh_hook = config.post_refresh_hook;
    this._connect_links();
}

namespace.BatchNavigatorHooks = BatchNavigatorHooks;

/**
 * A function to wire up the batch navigation links.
 */
BatchNavigatorHooks.prototype._connect_links = function() {
    if (Y.Lang.isFunction(this.post_refresh_hook)) {
        this.post_refresh_hook();
    }
    var self = this;
    self.links_active = true;
    self.nav_links = [];
    Y.Array.each(['first', 'previous', 'next', 'last'], function(link_type) {
        self.contentBox.all(
            'a.' + link_type + ', span.' + link_type)
                .each(function(nav_link) {
            var href = nav_link.get('href');
            if (href !== undefined) {
                var link_url = href;
                // We either use a custom URL with the batch control
                // parameters appended or append the batch_request parameter
                // to the standard batch navigation links.
                if (self.link_url_base !== undefined) {
                    var urlparts = href.split('?');
                    link_url = self.link_url_base + '?' + urlparts[1];
                }
                if (link_url.indexOf('batch_request=') < 0) {
                    link_url += '&batch_request=' + self.batch_request_value;
                }
                nav_link.addClass('js-action');
                nav_link.on('click', function(e) {
                    e.preventDefault();
                    if (self.links_active) {
                        self._link_handler(link_url);
                    }
                });
            }
            self.nav_links.push(nav_link);
        });
    });
};

/**
 * The function which fetches the next batch of data and displays it.
 * @param link_url the URL to invoke to get the data.
 */
BatchNavigatorHooks.prototype._link_handler = function(link_url) {
    var self = this;
    var y_config = {
        method: "GET",
        headers: {'Accept': 'application/json;'},
        data: '',
        on: {
            start: function() {
                self.showSpinner();
            },
            success: function(id, result) {
                self.hideSpinner();
                self.contentBox.set('innerHTML', result.responseText);
                self._connect_links();
            },
            failure: self.error_handler.getFailureHandler()
        }
    };
    this.lp_client.io_provider.io(link_url, y_config);
};

BatchNavigatorHooks.prototype.showSpinner = function() {
    // We make all the nav links inactive and show spinner(s) before the
    // 'First' links.
    this.links_active = false;
    Y.each(this.nav_links, function(nav_link) {
        nav_link.addClass('inactive');
        if (nav_link.hasClass('first')) {
            var spinner_node = Y.Node.create(
            '<img class="spinner" src="/@@/spinner" alt="Loading..." />');
            nav_link.insertBefore(spinner_node, nav_link);
        }
    });
};

BatchNavigatorHooks.prototype.hideSpinner = function() {
    // Remove the spinner(s) and make links active again.
    this.links_active = true;
    this.contentBox.all('.spinner').remove();
    Y.each(this.nav_links, function(nav_link) {
        var href = nav_link.get('href');
        if (href !== undefined) {
            nav_link.removeClass('inactive');
        }
    });
};

}, "0.1", {"requires": [
    "dom", "node", "event", "io-base", "lp.client", "lp.app.errors"]});
