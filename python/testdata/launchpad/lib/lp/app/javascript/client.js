/* Copyright 2009-2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Utility methods and classes to deal with the Launchpad API using
 * Javascript.
 *
 * @module Y.lp.client
 */
YUI.add('lp.client', function(Y) {
    // Private code used only in the module.
    var NOTIFICATION_INFO = {
        'level10': {
            'selector': '.debug.message',
            'css_class': 'debug message'
        },
        'level20': {
            'selector': '.informational.message',
            'css_class': 'informational message'
        },
        'level30': {
            'selector': '.warning.message',
            'css_class': 'warning message'
        },
        'level40': {
            'selector': '.error.message',
            'css_class': 'error message'
        }
    };

    var update_cached_object = function (cache_name, cache, entry) {
        var fields_changed = [];
        var name;
        var html_name;
        for (name in cache) {
            if (cache.hasOwnProperty(name)) {
                var old_value = cache[name];
                var new_value = entry.get(name);
                if (name !== 'lp_html') {
                    if (old_value !== new_value) {
                        fields_changed.push(name);
                        cache[name] = new_value;
                        var field_updated_event_name =
                              'lp:' + cache_name + ':' + name + ':changed';
                        var new_value_html = entry.getHTML(name);
                        var event = {
                          name: name,
                          old_value: old_value,
                          new_value: new_value,
                          new_value_html: new_value_html,
                          entry: entry
                        };
                        Y.fire(field_updated_event_name, event);
                    }
                }
                else {
                    // Since we don't care here about the content, we aren't
                    // using the values here to determine if the field has
                    // changed, so we can just update the cache.
                    for (html_name in old_value) {
                        if (old_value.hasOwnProperty(html_name)) {
                            old_value[html_name] = new_value[html_name];
                        }
                    }
                }
            }
        }

        if (fields_changed.length > 0) {
            var event_name = 'lp:' + cache_name + ':changed';
            var event_ = {
                fields_changed: fields_changed,
                entry: entry
            };
            Y.fire(event_name, event_);
        }
    };


    var module = Y.namespace('lp.client');

    module.HTTP_CREATED = 201;
    module.HTTP_SEE_ALSO = 303;
    module.HTTP_NOT_FOUND = 404;

    module.XHTML = 'application/xhtml+xml';
    module.GET = 'get';
    module.POST = 'post';
    module.PATCH = 'patch';

    /* Log the normal attributes accessible via o[key], and if it is a
     * YUI node, log all of the attributes accessible via o.get(key).
     * This function is not recursive to keep the log output reasonable.
     *
     * @method log_object
     * @param o The object being logged.
     * @param {String} name An optional name to describe the object.
     */
    module.log_object = function(o, name) {
        var result;
        var format = function(value) {
            if (typeof value === 'string') {
                value = value.substring(0, 200); // Truncate long strings.
                return '"' + value + '"';
            } else if (typeof value === 'function') {
                // Only log the function parameters instead
                // of the whole code block.
                return String(value).split(" {")[0];
            } else if (value instanceof Array) {
                return 'Array of length ' + value.length;
            } else {
                return String(value);
            }
        };

        var introspect = function(collection) {
            var items = [];
            var keys = [];
            var key;
            var index;
            for (key in collection) {
                if (collection.hasOwnProperty(key)) {
                    keys.push(key);
                }
            }
            keys.sort();
            for (index in keys) {
                if (keys.hasOwnProperty(index)) {
                    key = keys[index];
                    var value;
                    try {
                        value = format(collection[key]);
                    } catch (e) {
                        // This is necessary to handle attributes which
                        // will throw a permission denied error.
                        value = e.message;
                    }
                    items.push(key + '=' + value);
                }
            }
            return items.join(',\n  ');
        };

        if (o === null || typeof o === 'string' || typeof o === 'function') {
            result = format(o);
        } else {
            result = '(direct-attributes)\n  ' + introspect(o);
            if (o.getAttrs !== undefined) {
                result += '\n(get()-attributes)\n  ' + introspect(o.getAttrs());
            }
        }
        if (name !== undefined) {
            result = name + ': ' + result;
        }
        Y.log(result);
    };

    // Generally useful functions.
    /* Helper to select the io_provider. */
    module.get_io_provider = function(io_provider) {
        if (io_provider === undefined) {
            return Y;
        }
        return io_provider;
    };

    /* Helper to select the io_provider from a config. */
    module.get_configured_io_provider = function(config, key) {
        if (key === undefined) {
            key = 'io_provider';
        }
        if (config === undefined || config[key] === undefined) {
            return Y;
        }
        return config[key];
    };

    module.append_qs = function(qs, key, value) {
        /* Append a key-value pair to a query string. */
        var elems = (qs && qs.length > 0) ? [qs] : [];
        var enc = encodeURIComponent;
        if (Y.Lang.isArray(value)) {
            var index;
            for (index = 0; index < value.length; index++) {
                elems.push(enc(key) + "=" + enc(value[index]));
            }
        }
        else {
            elems.push(enc(key) + "=" + enc(value));
        }
        return elems.join("&");
    };

    module.normalize_uri = function(uri) {
        /**
         * Converts an absolute URI into a relative URI.
         * Appends the root to a relative URI that lacks the root.
         * Does nothing to a relative URI that includes the root.
         */
        var host_start = uri.indexOf('//');
        if (host_start !== -1) {
            var host_end = uri.indexOf('/', host_start+2);
            // eg. "http://www.example.com/api/devel/foo";
            // Don't try to insert the service base into what was an
            // absolute URL. So "http://www.example.com/foo" becomes "/foo"
            return uri.substring(host_end, uri.length);
        }

        var base = "/api/devel";
        if (uri.indexOf(base.substring(1, base.length)) === 0) {
            // eg. "api/devel/foo"
            return '/' + uri;
        }
        if (uri.indexOf(base) !== 0) {
            if (uri.indexOf('/') !== 0) {
                // eg. "foo/bar"
                uri = base + '/' + uri;
            } else {
                // eg. "/foo/bar"
                uri = base + uri;
            }
        }
        return uri;
    };

    /**
     * After normalizing the uri, turn it into an absolute uri.
     * This is useful for passing in parameters to named_post and patch.
     *
     * @method get_absolute_uri
     * @param {String} uri
     * @return {String} URI.
     */
    module.get_absolute_uri = function(uri) {
        var location = document.location;

        uri = module.normalize_uri(uri);
        return location.protocol + '//' + location.host + uri;
    };

    /**
     * Turn an entry resource URI and a field name into a field resource URI.
     * @method get_field_uri
     * @param {String} base_uri
     * @param {String} field_name
     * @return {String} URI
     */
    module.get_field_uri = function(base_uri, field_name) {
        base_uri = module.normalize_uri(base_uri);
        field_name = escape(field_name);
        if (base_uri.charAt(base_uri.length - 1) === '/') {
            return base_uri + field_name;
        } else {
            return base_uri + '/' + field_name;
        }
    };

    /**
     * Get the URL of the view for an Entry
     * @method get_view_url
     * @param {Entry} entry
     * @param {String} view_name
     * @param {String} namespace
     * @param {String} query (optional) structured query variables to use.
     * @return {String} URL
     */
    module.get_view_url = function(entry, view_name, namespace, query){
        entry_url = Y.lp.get_url_path(entry.get('web_link'));
        var querystring = Y.QueryString.stringify(query);
        if (querystring !== '') {
            querystring = '?' + querystring;
        }
        return (
            entry_url + '/' + view_name + '/++' +
            namespace + '++' + querystring);
    };

    /**
     * Get the URL of the form for a view for an Entry
     * @method get_form_url
     * @param {Entry} entry
     * @param {String} view_name
     * @return {String} URL
     */
    module.get_form_url = function(entry, view_name) {
        return module.get_view_url(entry, view_name, 'form');
    };

    /**
     * Load the model for a view.
     *
     * @param entry An Entry, i.e. a Lanchpad API object
     * @param view_name The name of the view to retrieve the model for
     * @param config An IO config.
     * @param query (optional) The structured query variables to use.
     */
    module.load_model = function(entry, view_name, config, query){
        var url = module.get_view_url(entry, view_name, 'model', query);
        var old_on_success = config.on.success;
        var on = config.on;
        on.success = module.wrap_resource_on_success;
        var y_config = {
            on: on,
            'arguments': [entry.lp_client, url, old_on_success, false]
        };
        var io_provider = module.get_configured_io_provider(config);
        io_provider.io(url, y_config);
    };

    module.add_accept = function(config, headers) {
        if (headers === undefined) {
            headers = {};
        }
        var accept = config.accept || 'application/json';
        headers.Accept = accept;
        return headers;
    };

    module.start_and_size = function(data, start, size) {
        /* Create a query string with values for ws.start and/or ws.size. */
        if (start !== undefined) {
            data = module.append_qs(data, "ws.start", start);
        }
        if (size !== undefined) {
            data = module.append_qs(data, "ws.size", size);
        }
        return data;
    };

    module.update_cache = function(entry) {
        if (!entry) {
            return;
        }
        var original_uri = entry.uri;
        var full_uri = module.get_absolute_uri(original_uri);
        var name;
        var cached_object;
        for (name in LP.cache) {
            if (LP.cache.hasOwnProperty(name)) {
                cached_object = LP.cache[name];
                /*jslint continue:true*/
                if (!Y.Lang.isValue(cached_object)) {
                    continue;
                }
                if (cached_object.self_link === full_uri) {
                    Y.log(name + ' cached object has been updated.');
                    update_cached_object(name, cached_object, entry);
                }
            }
        }
    };

    module.wrap_resource_on_success = function(ignore, response, args) {
        var client = args[0];
        // The original uri of the caller.
        var uri = args[1];
        var callback = args[2];
        var update_cache = args[3];
        var method = args[4];
        var representation, wrapped;

        if (callback) {
            var media_type = response.getResponseHeader('Content-Type');
            if (media_type.substring(0,16) === 'application/json') {
                representation = Y.JSON.parse(response.responseText);

                // If the object fetched has a self_link, make that the object's
                // uri for use in other api methods off of that object.
                // During a PATCH request the caller is the object. Leave the
                // original_uri alone. Otherwise make the uri the object
                // coming back.
                if (Y.Lang.isValue(representation) &&
                    Y.Lang.isValue(representation.self_link) &&
                    method !== module.PATCH) {
                    uri = representation.self_link;
                }

                // If the response contains a notification header, display the
                // notifications.
                var notifications = response.getResponseHeader(
                    'X-Lazr-Notifications');
                if (notifications !== null && notifications !== "") {
                    module.display_notifications(notifications);
                }
                wrapped = client.wrap_resource(uri, representation);
                var result = callback(wrapped);
                if (update_cache) {
                    module.update_cache(wrapped);
                }
                return result;
            } else {
                return callback(response.responseText);
            }
        }
    };

    /**
     * Display a list of notifications - error, warning, informational or debug.
     * @param notifications An json encoded array of (level, message) tuples.
     */
    module.display_notifications = function (notifications) {
        if (notifications === undefined) {
            return;
        }
        if (notifications === 'null' || notifications === null
            || notifications === "") {
            module.remove_notifications();
            return;
        }

        var notifications_by_level = {
            'level10': {
                'notifications': []
            },
            'level20': {
                'notifications': []
            },
            'level30': {
                'notifications': []
            },
            'level40': {
                'notifications': []
            }
        };

        // Extract the notifications from the json.
        notifications = Y.JSON.parse(notifications);
        Y.each(notifications, function(notification, key) {
            var level = notification[0];
            var message = notification[1];
            notifications_by_level['level'+level].notifications.push(message);
        });

        // The place where we want to insert the notification divs.
        var last_message = null;
        // A mapping from the div class to notification messages.
        Y.each(notifications_by_level, function(info, key) {
            Y.each(info.notifications, function(notification) {
                var css_class = NOTIFICATION_INFO[key].css_class;
                var node = Y.Node.create("<div class='"+css_class+"'/>");
                node.set('innerHTML', notification);
                if (last_message === null) {
                    var div = Y.one('div#request-notifications');
                    div.insert(node);
                } else {
                    last_message.insert(node, 'after');
                }
                last_message = node;
            });
        });
    };

    /**
     * Remove any notifications that are currently displayed.
     */
    module.remove_notifications = function() {
        Y.each(NOTIFICATION_INFO, function (info) {
            var nodes = Y.all('div#request-notifications div'+info.selector);
            nodes.each(function(node) {
                var parent = node.get('parentNode');
                parent.removeChild(node);
            });
        });
    };

    // The resources that come together to make Launchpad.

    // A hosted file resource.
    module.HostedFile = function(client, uri, content_type, contents) {
        /* A binary file manipulable through the web service. */
        this.lp_client = client;
        this.uri = uri;
        this.content_type = content_type;
        this.contents = contents;
        this.io_provider = client.io_provider;
    };

    module.HostedFile.prototype = {
        'lp_save' : function(config) {
            /* Write a new version of this file back to the web service. */
            var on = config.on;
            var disposition = 'attachment; filename="' + this.filename + '"';
            var hosted_file = this;
            var args = hosted_file;
            var y_config = {
                method: "PUT",
                'on': on,
                'headers': {"Content-Type": hosted_file.content_type,
                            "Content-Disposition": disposition},
                'arguments': args,
                'data': hosted_file.contents,
                'sync': this.lp_client.sync
            };
            this.io_provider.io(module.normalize_uri(hosted_file.uri),
                                y_config);
        },

        'lp_delete' : function(config) {
            var on = config.on;
            var hosted_file = this;
            var args = hosted_file;
            var y_config = { method: "DELETE",
                             on: on,
                             'arguments': args,
                             sync: this.lp_client.sync
                           };
            this.io_provider.io(hosted_file.uri, y_config);
        }
    };

    module.Resource = function() {
        /* The base class for objects retrieved from Launchpad's web service. */
    };
    module.Resource.prototype = {
        'init': function(client, representation, uri) {
            /* Initialize a resource with its representation and URI. */
            this.lp_client = client;
            this.uri = uri;
            var key;
            for (key in representation) {
                if (representation.hasOwnProperty(key)) {
                    this[key] = representation[key];
                }
            }
        },

        'lookup_value': function(key) {
            /* A common getter interface for Entrys and non-Entrys. */
            return this[key];
        },

        'follow_link': function(link_name, config) {
            /* Return the object at the other end of the named link. */
            var on = config.on;
            var uri = this.lookup_value(link_name + '_link');
            if (uri === undefined) {
                uri = this.lookup_value(link_name + '_collection_link');
            }
            if (uri === undefined) {
                throw new Error("No such link: " + link_name);
            }

            // If the response is 404, it means we have a hosted file that
            // doesn't exist yet. If the response is 303 and goes off to
            // another site, that means we have a hosted file that does exist.
            // Either way we should turn the failure into a success.
            var on_success = on.success;
            var old_on_failure = on.failure;
            on.failure = function(ignore, response, args) {
                var client = args[0];
                var original_url = args[1];
                if (response.status === module.HTTP_NOT_FOUND ||
                    response.status === module.HTTP_SEE_ALSO) {
                    var file = new module.HostedFile(client, original_url);
                    return on_success(file);
                } else if (old_on_failure !== undefined) {
                    return old_on_failure(ignore, response, args);
                }
            };
            this.lp_client.get(uri, {on: on});
        },

        'named_get': function(operation_name, config) {
            /* Get the result of a named GET operation on this resource. */
            return this.lp_client.named_get(this.uri, operation_name,
                                            config);
        },

        'named_post': function(operation_name, config) {
            /* Trigger a named POST operation on this resource. */
            return this.lp_client.named_post(this.uri, operation_name,
                                             config);
        }
    };

    // The service root resource.
    module.Root = function(client, representation, uri) {
        /* The root of the Launchpad web service. */
        this.init(client, representation, uri);
    };
    module.Root.prototype = new module.Resource();

    module.Collection = function(client, representation, uri) {
        /* A grouped collection of objets from the Launchpad web service. */
        var index, entry;
        this.init(client, representation, uri);
        for (index = 0 ; index < this.entries.length ; index++) {
            entry = this.entries[index];
            this.entries[index] = new module.Entry(client,
                                                   entry,
                                                   entry.self_link);
        }
    };

    module.Collection.prototype = new module.Resource();

    module.Collection.prototype.lp_slice = function(on, start, size) {
        /* Retrieve a subset of the collection.

           :param start: Where in the collection to start serving entries.
           :param size: How many entries to serve.
        */
        return this.lp_client.get(this.uri,
                                  {on: on, start: start, size: size});
    };

    module.Entry = function(client, representation, uri) {
        /* A single object from the Launchpad web service. */
        this.lp_client = client;
        this.uri = uri;
        this.dirty_attributes = [];
        var entry = this;

        // Copy the representation keys into our own set of attributes, and add
        // an attribute-change event listener for caching purposes.
        var key;
        for (key in representation) {
            if (representation.hasOwnProperty(key)) {
                this.addAttr(key, {value: representation[key]});
                this.on(key + "Change", this.mark_as_dirty);
            }
        }
    };

    module.Entry.prototype = new module.Resource();

    // Augment with Attribute so that we can listen for attribute change events.
    Y.augment(module.Entry, Y.Attribute);

    module.Entry.prototype.mark_as_dirty = function(event) {
        /* Respond to an event triggered by modification to an Entry's field. */
        if (event.newVal !== event.prevVal) {
            this.dirty_attributes.push(event.attrName);
        }
    };

    module.Entry.prototype.lp_save = function(config) {
        /* Write modifications to this entry back to the web service. */
        var representation = {};
        var entry = this;
        Y.each(this.dirty_attributes, function(attribute, key) {
                representation[attribute] = entry.get(attribute);
            });
        var headers = {};
        if (this.get('http_etag') !== undefined) {
            headers['If-Match'] = this.get('http_etag');
        }
        var uri = module.normalize_uri(this.get('self_link'));
        this.lp_client.patch(uri, representation, config, headers);
        this.dirty_attributes = [];
    };

    module.Entry.prototype.lookup_value = function(key) {
        /* A common getter interface between Entrys and non-Entrys. */
        return this.get(key);
    };

    module.Entry.prototype.getHTML = function(key) {
        var lp_html = this.get('lp_html');
        if (lp_html) {
            // First look for the key.
            var value = lp_html[key];
            if (value === undefined) {
                // now look for key_link
                value = lp_html[key + '_link'];
            }
            if (value !== undefined) {
                var result = Y.Node.create("<span/>");
                result.setContent(value);
                return result;
            }
        }
        return null;
    };

    // The Launchpad client itself.
    module.Launchpad = function(config) {
        /* A client that makes HTTP requests to Launchpad's web service. */
        this.io_provider = module.get_configured_io_provider(config);
        this.sync = (config ? config.sync : false);
    };

    module.Launchpad.prototype = {
        'get': function (uri, config) {
            /* Get the current state of a resource. */
            var on = Y.merge(config.on);
            var start = config.start;
            var size = config.size;
            var data = config.data;
            var headers = module.add_accept(config);
            uri = module.normalize_uri(uri);
            if (data === undefined) {
                data = "";
            }
            if (start !== undefined || size !== undefined) {
                data = module.start_and_size(data, start, size);
            }

            var old_on_success = on.success;
            var update_cache = false;
            on.success = module.wrap_resource_on_success;
            var client = this;
            var y_config = {
                on: on,
                'arguments': [
                    client, uri, old_on_success, update_cache, module.GET],
                'headers': headers,
                data: data,
                sync: this.sync
            };
            return this.io_provider.io(uri, y_config);
        },

        'named_get' : function(uri, operation_name, config) {
            /* Retrieve the value of a named GET operation on the given URI. */
            var parameters = config.parameters;
            var data = module.append_qs("", "ws.op", operation_name);
            var name;
            for (name in parameters) {
                if (parameters.hasOwnProperty(name)) {
                    data = module.append_qs(data, name, parameters[name]);
                }
            }
            config.data = data;
            return this.get(uri, config);
        },

        'named_post' : function (uri, operation_name, config) {
            /* Perform a named POST operation on the given URI. */
            var on = Y.merge(config.on);
            var parameters = config.parameters;
            var data;
            var name;
            uri = module.normalize_uri(uri);
            data = module.append_qs(data, "ws.op", operation_name);
            for (name in parameters) {
                if (parameters.hasOwnProperty(name)) {
                    data = module.append_qs(data, name, parameters[name]);
                }
            }

            var old_on_success = on.success;

            on.success = function(unknown, response, args) {
                if (response.status === module.HTTP_CREATED) {
                    // A new object was created as a result of the operation.
                    // Get that object and run the callback on it instead.
                    var new_location = response.getResponseHeader("Location");
                    return client.get(new_location,
                                      { on: { success: old_on_success,
                                              failure: on.failure } });
                }
                return module.wrap_resource_on_success(
                    undefined, response, args, module.POST);
            };
            var client = this;
            var update_cache = false;
            var y_config = {
                method: "POST",
                on: on,
                'arguments': [client, uri, old_on_success, update_cache],
                data: data,
                sync: this.sync
            };
            this.io_provider.io(uri, y_config);
        },

        'patch': function(uri, representation, config, headers) {
            var on = Y.merge(config.on);
            var data = Y.JSON.stringify(representation);
            uri = module.normalize_uri(uri);

            var old_on_success = on.success;
            var update_cache = true;
            on.success = module.wrap_resource_on_success;
            var args = [this, uri, old_on_success, update_cache, module.PATCH];

            var extra_headers = {
                "X-HTTP-Method-Override": "PATCH",
                "Content-Type": "application/json",
                "X-Content-Type-Override": "application/json"
            };
            var name;
            if (headers !== undefined) {
                for (name in headers) {
                    if (headers.hasOwnProperty(name)) {
                        extra_headers[name] = headers[name];
                    }
                }
            }
            extra_headers = module.add_accept(config, extra_headers);

            var y_config = {
                'method': "POST",
                'on': on,
                'headers': extra_headers,
                'arguments': args,
                'data': data,
                'sync': this.sync
            };
            this.io_provider.io(uri, y_config);
        },

        'wrap_resource': function(uri, representation) {
            var key;
            var new_representation;
            /* Given a representation, turn it into a subclass of Resource. */
            if (representation === null || representation === undefined) {
                return representation;
            }
            if (representation.resource_type_link === undefined) {
                // This is a non-entry object returned by a named operation.
                // It's either a list or a random JSON object.
                if (representation.total_size !== undefined
                    || representation.total_size_link !== undefined) {
                    // It's a list. Treat it as a collection;
                    // it should be slicable.
                    return new module.Collection(this, representation, uri);
                } else if (Y.Lang.isObject(representation)) {
                    // It's an Array or mapping.  Recurse into it.
                    if (Y.Lang.isArray(representation)) {
                        new_representation = [];
                    }
                    else {
                        new_representation = {};
                    }
                    for (key in representation) {
                        if (representation.hasOwnProperty(key)) {
                            var value = representation[key];
                            if (Y.Lang.isValue(value)) {
                                value = this.wrap_resource(
                                    value.self_link, value);
                            }
                            new_representation[key] = value;
                        }
                    }
                    return new_representation;
                } else {
                    // It's a random JSON object. Leave it alone.
                    return representation;
                }
            } else if (representation.resource_type_link.search(
                /\/#service-root$/) !== -1) {
                return new module.Root(this, representation, uri);
            } else if (representation.total_size === undefined) {
                return new module.Entry(this, representation, uri);
            } else {
                return new module.Collection(this, representation, uri);
            }
        }
    };

    /**
     * Helper object for handling XHR failures.
     * clearProgressUI() and showError() need to be defined by the callsite
     * using this object.
     *
     * @class ErrorHandler
     */
    module.ErrorHandler = Y.Base.create('client-error-handler', Y.Base, [], {
        /**
         * Clear the progress indicator.
         *
         * The default implementation does nothing. Override this to provide
         * an implementation to remove the UI elements used to indicate
         * progress. After this method is called, the UI should be ready for
         * repeating the interaction, allowing the user to retry submitting
         * the data.
         *
         * @method clearProgressUI
         */
        clearProgressUI: function () {},

        /**
         * Show the error message to the user.
         *
         * The default implementation does nothing. Override this to provide
         * an implementation to display the UI elements containing the error
         * message.
         *
         * @method showError
         * @param error_msg The error text to display.
         */
        showError: function (error_msg) {},

        /**
         * Handle an error from an XHR request.
         *
         * This method is invoked before any generic error handling is done.
         *
         * @method handleError
         * @param ioId The request id.
         * @param response The XHR call response object.
         * @return {Boolean} Return true if the error has been fully processed
         * and any further generic error handling is not required.
         */
        handleError: function(ioId, response) {
            return false;
        },

        /**
         * Return a failure handler function for XHR requests.
         *
         * Assign the result of this function as the failure handler when
         * doing an XHR request using the API client.
         *
         * @method getFailureHandler
         */
        getFailureHandler: function () {
            var self = this;
            return function(ioId, o) {
                self.clearProgressUI();
                // Perform any user specified error handling. If true is
                // returned, we do not do any further processing.
                if( self.handleError(ioId, o) ) {
                    return;
                }
                // If it was a timeout...
                if (o.status === 503) {
                    self.showError(
                        'Timeout error, please try again in a few minutes.');
                // If it was a server error...
                } else if (o.status >= 500) {
                    var server_error =
                        'Server error, please contact an administrator.';
                    var oops_id = self.get_oops_id(o);
                    if (oops_id) {
                        server_error = server_error + ' OOPS ID:' + oops_id;
                    }
                    self.showError(server_error);
                // Otherwise we send some sane text as an error
                } else if (o.status === 412){
                    self.showError(o.status + ' ' + o.statusText);
                } else {
                    self.showError(self.get_generic_error(o));
                }
            };
        },
        get_oops_id: function(response) {
            return response.getResponseHeader('X-Lazr-OopsId');
        },
        get_generic_error: function(response) {
            return response.responseText;
        }
    });

    module.FormErrorHandler = Y.Base.create('client-form-error-handler',
                                            module.ErrorHandler, [], {
        // Clear any errors on the form.
        clearFormErrors: function() {
            Y.all('.error.message').remove(true);
            Y.all('.error .message').remove(true);
            Y.all('div.error').removeClass('error');
        },

        // If the XHR call returns a form validation error, we display the
        // errors on the form.
        handleError: function(ioId, response) {
            if (response.status === 400
                    && response.statusText === 'Validation') {
                var response_info = Y.JSON.parse(response.responseText);
                var error_summary = response_info.error_summary;
                var form_wide_errors = response_info.form_wide_errors;
                var errors = response_info.errors;
                this.handleFormValidationError(
                    error_summary, form_wide_errors, errors);
                return true;
            }
            return false;
        },

        // Display the specified errors on the form. The errors are displayed in
        // the same way as is done by the Launchpad HTML form rendering
        // infrastructure using TAL templates.
        handleFormValidationError: function(error_summary,
                                            form_wide_errors, errors) {
            var form = this.get('form');
            if (!Y.Lang.isValue(form)) {
                form = Y.one("[name='launchpadform']");
            }
            if (!Y.Lang.isValue(form)) {
                return;
            }
            var form_content = form.one('table.form');
            if (!Y.Lang.isValue(form_content)) {
                form_content = form;
            }
            // Display the error summary information.
            var error_summary_node =
                Y.Node.create('<p class="error message"></p>')
                .set('text', error_summary);
            form_content.insertBefore(error_summary_node, form_content);
            // Display the form wide errors.
            if (form_wide_errors.length > 0) {
                var form_error_node =
                    Y.Node.create('<div class="error message"></div>');
                Y.Array.each(form_wide_errors, function(message) {
                    form_error_node.appendChild(Y.Node.create('<p></p>')
                        .set('text', message));
                });
                form_content.insertBefore(form_error_node, form_content);
            }
            // Display the field specific errors.
            Y.each(errors, function(message, field_name) {
                var label = Y.one('label[for="' + field_name + '"]');
                if (Y.Lang.isValue(label)) {
                    label.ancestor('div').addClass('error');
                    var field = label.next('div');
                    var error_node =
                        Y.Node.create('<div class="message"></div>')
                            .set('text', message);
                    field.insert(error_node, 'after');
                }
            });
        },

        get_oops_id: function(response) {
            var oops_re = /code class\="oopsid">(OOPS-[^<]*)/;
            var result = response.responseText.match(oops_re);
            if (result === null) {
                return null;
            }
            return result[1];
        },

        get_generic_error: function(response) {
            if (response.status !== 403){
                return "Sorry, you don't have permission to make this change.";
            }
            else {
                return response.status + ' ' + response.statusText;
            }
        }
   }, {
       ATTRS: {
           form: {
               value: null
           }
       }
   });

}, "0.1", {
    requires: ["attribute", "base", "io", "querystring", "json-parse",
        "json-stringify", "lp"]
});

YUI.add('lp.client.plugins', function (Y) {
    /**
     * A collection of plugins to hook lp.client into widgets.
     *
     * @module lp.client.plugins
     */
    var module = Y.namespace('lp.client.plugins');

    /**
     * This plugin overrides the widget _saveData method to update the
     * underlying model object using a PATCH call.
     *
     * @namespace lp.client.plugins
     * @class PATCHPlugin
     * @extends Widget
     */
    module.PATCHPlugin = Y.Base.create('client-plugin-patch',
                                       Y.Plugin.Base, [], {
        /**
         * Configuration parameters that will be passed through to the lp.client
         * call.
         *
         * @property extra_config
         * @type Hash
         */
        extra_config: null,

        /**
         * Constructor code.  Check that the required config parameters are
         * present and wrap the host _saveData method.
         *
         * @method initializer
         * @protected
         */
        initializer: function(config) {
            if (!Y.Lang.isString(config.patch)) {
                Y.error(
                    "missing config: 'patch' containing the attribute name");
            }

            if (!Y.Lang.isString(config.resource)) {
                Y.error(
                    "missing config: 'resource' containing the URL to patch");
            }

            // Save the config object that the user passed in so that we can
            // pass any extra parameters through to the lp.client constructor.
            this.extra_config = config || {};
            this.extra_config.accept = 'application/json;include=lp_html';

            // Save a reference to the original _saveData()
            //method before wrapping it.
            this.original_save = config.host._saveData;

            // We want to run our PATCH code instead of the original
            // 'save' method.  Using doBefore() means that
            // unplugging our code will leave the original
            // widget in a clean state.
            this.doBefore("_saveData", this.doPATCH);

            var self = this;
            this.error_handler = new Y.lp.client.ErrorHandler();
            this.error_handler.clearProgressUI = function () {
                config.host._uiClearWaiting();
            };
            this.error_handler.showError = function (error_msg) {
                config.host.showError(error_msg);
            };
        },

        /**
         * Send a PATCH request with the widget's input value for the
         * configured attribute.
         *
         * It will set the widget in waiting status, do the PATCH.
         * Success will call the original widget save method.
         *
         * Errors are reported through the widget's showError() method.
         *
         * @method doPATCH
         */
        doPATCH: function() {
            var owner = this.get("host"),
                original_save = this.original_save;

            // Set the widget in 'waiting' state.
            owner._uiSetWaiting();

            var client =  new Y.lp.client.Launchpad();
            var formatter = Y.bind(this.get('formatter'), this);
            var attribute = this.get('patch');

            var patch_payload;
            var val = owner.getInput();
            patch_payload = {};
            patch_payload[attribute] = val;

            var callbacks = {
                on: {
                    success: function (entry) {
                        owner._uiClearWaiting();
                        var new_value = formatter(entry, attribute);
                        original_save.apply(owner, [new_value]);
                    },
                    failure: this.error_handler.getFailureHandler()
                }
            };

            var cfg = Y.merge(callbacks, this.extra_config);

            client.patch(this.get('resource'), patch_payload, cfg);

            // Prevent the method we are hooking before from running.
            return new Y.Do.Halt();
        },

        /**
         * Return the webservice Entry object attribute that is to be shown in
         * the page DOM.
         *
         * This function may be overridden in various ways.
         *
         * @method _defaultFormatter
         * @protected
         * @param result {Entry|String} A Launchpad webservice Entry object, or
         * the unmodified result string if the default Content-Type wasn't used.
         * @param attribute {String} The resource attribute that the PATCH
         * request was sent to.
         * @return {String|Node} A string or Node instance to be inserted into
         * the DOM.
         */
        _defaultFormatter: function(result, attribute) {
            if (Y.Lang.isString(result)) {
                return result;
            } else {
              if (this.get('use_html')) {
                return result.getHTML(attribute).get('innerHTML');
              } else {
                return result.get(attribute);
              }
            }
        }
    }, {
        /**
         * The identity of the plugin.
         *
         * @property PATCHPlugin.NAME
         * @type String
         * @static
         */
        NAME: 'PATCHPlugin',

        /**
         * The namespace of the plugin.
         *
         * @property PATCHPlugin.NS
         * @type String
         * @static
         */
        NS: 'patcher',

        /**
         * Static property used to define the default attribute configuration of
         * this plugin.
         *
         * @property PATCHPlugin.ATTRS
         * @type Object
         * @static
         */
        ATTRS : {
            /**
             * Name of the attribute to patch.
             *
             * @attribute patch
             * @type String
             */
            patch: {},

            /**
             * URL of the resource to PATCH.
             *
             * @attribute resource
             * @type String
             */
            resource: {},

            /**
             * Should the resulting field get the value from the lp_html
             * attribute?
             *
             * @attribute use_html
             * @type Boolean
             */
            use_html: false,

            /**
             * The function to use to format the returned result into a form
             * that can be inserted into the page DOM.
             *
             * The default value is a function that simply returns the result
             * unmodified.
             *
             * @attribute formatter
             * @type Function
             * @default null
             */
            formatter: {
                valueFn: function() { return this._defaultFormatter; }
            }
        }
    });
}, "0.1", {
    requires: ["base", "plugin", "dump", "lp.client"]
});
