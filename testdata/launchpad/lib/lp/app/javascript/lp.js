// Some Javascript code from Plone Solutions
// http://www.plonesolutions.com, thanks!

/**
 * Launchpad common utilities and functions.
 *
 * @module lp
 * @namespace lp
 */
YUI.add('lp', function(Y) {
    var lp = Y.namespace('lp');

    /**
     * A representation of the launchpad_views cookie.
     *
     * The launchpad_views cookie is used to store the state of optional
     * page content.
     *
     * @class launchpad_views
     */
    lp.launchpad_views = {
        /**
         * Store a value as the named key.
         *
         * @method set
         * @param {String} key the name the value is stored as.
         * @param {string} value the value to store.
         */
        set: function(key, value) {
            var domain = document.location.hostname.replace(
                /.*(launchpad.*)/, '$1');
            var future = new Date();
            future.setYear(future.getFullYear() + 1);
            var config = {
                path: '/',
                domain: domain,
                secure: true,
                expires: future
                };
            Y.Cookie.setSub('launchpad_views', key, value, config);
            },
        /**
         * Retrieve the value in the key.
         *
         * @method get
         * @param {String} key the name the value is stored as.
         * @return {string} the value of the key.
         */
        get: function(key) {
            // The default is true.  Only values explicitly set to false
            // are false.
            return (Y.Cookie.getSub('launchpad_views', key) !== 'false');
            }
    };

    /**
     * Activate all collapsible sections of a page.
     *
     * @method activate_collapsibles
     */
    Y.lp.activate_collapsibles = function() {
        // CSS selector 'legend + *' gets the next sibling element.
        Y.lp.app.widgets.expander.createByCSS(
            '.collapsible', '> :first-child', '> :first-child + *', true);
    };

    /**
     * Return a hyperlink with the specified URL.
     */
    var get_hyperlink  = function(url){
        var link =  Y.Node.create('<a>junk</a>');
        link.set('href', url);
        return link;
    };

    /**
     * Return the path portion of the specified URL.
     */
    Y.lp.get_url_path = function(url) {
        pathname = get_hyperlink(url).get('pathname');
        if (!pathname || pathname[0] !== '/') {
            // Ensure the leading slash often dropped by msie.
            pathname = '/' + pathname;
        }
        if (pathname.length > 1 && pathname[1] === '/') {
            // Ensure a single root often broken by a concatenation error.
            pathname = pathname.substring(1, pathname.length);
        }
        return pathname;
    };

    /**
     * Return the query string of the specified URL.
     */
    Y.lp.get_url_query = function(url){
        var link = get_hyperlink(url);
        var query = link.get('search');
        if (query.length > 0) {
            query = query.slice(1);
        }
        return query;
    };
}, "0.1", {"requires":["cookie", "lp.app.widgets.expander"]});
