/* Copyright 2011 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * A form overlay that can request builds for a recipe..
 *
 * @namespace Y.lp.code.recipebuild_overlay
 * @requires  dom, node, io-base, lp.anim, lp.ui.formoverlay
 */
YUI.add('lp.code.requestbuild_overlay', function(Y) {

var namespace = Y.namespace('lp.code.requestbuild_overlay');

var lp_client;
var request_build_overlay = null;
var request_build_submit_button;
var request_build_response_handler;
var request_daily_build_response_handler;

var DISABLED_DISTROSERIES_CHECKBOX_HTML =
    "<input type='checkbox' class='checkboxType' disabled='disabled'>" +
    "&nbsp;{distro} (build pending)";

var set_up_lp_client = function(io_provider) {
    if (lp_client === undefined) {
        lp_client = new Y.lp.client.Launchpad({io_provider: io_provider});
    } else {
        // io_provider may be a different instance of MockIo.
        lp_client.io_provider = io_provider;
    }
};

// This handler is used to process the results of form submission or other
// such operation (eg get, post). It provides some boiler plate and allows the
// developer to specify onSuccess and onError hooks. It is quite generic and
// perhaps could be moved to an infrastructure class.

var RequestResponseHandler = function () {};

RequestResponseHandler.prototype = new Y.lp.client.ErrorHandler();

RequestResponseHandler.prototype.getSuccessHandler = function(callback) {
    var self = this;
    return function (id, response) {
        self.clearProgressUI();
        callback(self, id, response);
    };
};

namespace.RequestResponseHandler = RequestResponseHandler;


namespace.hookUpDailyBuildsSchedule = function() {
    var logged_in = LP.links.me !== undefined;
    if (logged_in) {
        build_now_link = Y.one('#request-daily-build');
        if( build_now_link !== null ) {
          build_now_link.removeClass('hidden');
          Y.lp.code.requestbuild_overlay.connect_requestdailybuild();
        }
        Y.lp.code.requestbuild_overlay.connect_requestbuilds();
    }
    var form = Y.one('#request-daily-build-form');
    if (form) {
        form.addClass('hidden');
    }
};


namespace.connect_requestbuilds = function(config) {
    var io_provider = Y.lp.client.get_configured_io_provider(config),
        request_build_handle = Y.one('#request-builds');
    request_build_handle.addClass('js-action');
    request_build_handle.on('click', function(e) {
        e.preventDefault();
        if (request_build_overlay === null) {
            // Render the form and load the widgets to display
            var recipe_name = LP.cache.context.name;
            request_build_overlay = new Y.lp.ui.FormOverlay({
                headerContent: '<h2>Request builds for '
                                    + recipe_name + ' </h2>',
                form_submit_button: Y.Node.create(
                    '<button type="submit" name="field.actions.request" ' +
                    'value="Request builds">Request Builds</button>'),
                form_cancel_button: Y.Node.create(
                    '<button type="button" name="field.actions.cancel" ' +
                    '>Cancel</button>'),
                centered: true,
                form_submit_callback: do_request_builds,
                io_provider: io_provider,
                visible: false
            });
            Y.after(function() {
                disable_existing_builds(
                    request_build_submit_button, io_provider);
            }, request_build_overlay, "bindUI");
            request_build_overlay.render();
            request_build_submit_button =
                    Y.Node.one("[name='field.actions.request']");
        }
        request_build_submit_button.removeAttribute("disabled");
        request_build_overlay.clearError();
        var loading_spinner = [
            '<div id="temp-spinner">',
            '<img src="/@@/spinner"/>Loading...',
            '</div>'].join('');
        request_build_overlay.form_node.set("innerHTML", loading_spinner);
        request_build_overlay.loadFormContentAndRender('+builds/++form++');
        request_build_submit_button.show();
        request_build_overlay.show();
    });

    // Wire up the processing hooks
    request_build_response_handler = new RequestResponseHandler();
    request_build_response_handler.clearProgressUI = function() {
        destroy_temporary_spinner();
    };
    request_build_response_handler.showError = function(errormessage) {
        display_errors(null, errormessage);
    };
};

namespace.destroy_requestbuilds = function() {
    request_build_overlay.destroy();
    request_build_overlay = null;
};

var NO_BUILDS_MESSAGE = "All requested recipe builds are already queued.";
var ONE_BUILD_MESSAGE = "1 new recipe build has been queued.";
var MANY_BUILDS_MESSAGE = "{nr_new} new recipe builds have been queued.";

namespace.connect_requestdailybuild = function(config) {

    var request_daily_build_handle = Y.one('#request-daily-build');
    var display_message = function (message, css_class){
        var build_message_node = Y.Node.create('<div></div>')
            .set('id', 'new-builds-info')
            .addClass(css_class)
            .set('text', message)
            .append(Y.Node.create('<br />'))
            .append(Y.Node.create('<a></a>')
                .set('href', '#')
                .addClass('lesser')
                .addClass('js-action')
                .set('text', 'Dismiss'));
        build_message_node.one('a').on('click', function(e) {
            e.preventDefault();
            build_message_node.hide();
            if (css_class === 'build-error') {
                request_daily_build_handle.removeClass("hidden");
            }
        });
        request_daily_build_handle.insert(
                build_message_node,
                request_daily_build_handle);
    };
    request_daily_build_handle.on('click', function(e) {
        e.preventDefault();

        create_temporary_spinner(
                "Requesting build...", request_daily_build_handle);
        request_daily_build_handle.addClass("hidden");

        var base_url = LP.cache.context.web_link;
        var submit_url = base_url+"/+request-daily-build";
        var current_builds = harvest_current_build_records();

        var qs = Y.lp.client.append_qs(
                            '', 'field.actions.build', 'Build now');
        var y_config = {
            method: "POST",
            headers: {'Accept': 'application/xhtml'},
            on: {
                failure:
                    request_daily_build_response_handler.getFailureHandler(),
                success:
                    request_daily_build_response_handler.getSuccessHandler(
                    function(handler, id, response) {
                        var nr_new = display_build_records(
                                response.responseText, current_builds);
                        var new_builds_message;
                        switch (nr_new) {
                            case 0:
                                new_builds_message = NO_BUILDS_MESSAGE;
                                break;
                            case 1:
                                new_builds_message = ONE_BUILD_MESSAGE;
                                break;
                            default:
                                new_builds_message =
                                        Y.Lang.sub(
                                                MANY_BUILDS_MESSAGE,
                                                {nr_new: nr_new});
                        }
                        display_message(
                            new_builds_message, 'build-informational');
                    }
                  )
            },
            data: qs
        };
        var io_provider = Y.lp.client.get_configured_io_provider(config);
        io_provider.io(submit_url, y_config);
    });

    // Wire up the processing hooks
    request_daily_build_response_handler = new RequestResponseHandler();
    request_daily_build_response_handler.clearProgressUI = function() {
        destroy_temporary_spinner();
    };
    request_daily_build_response_handler.showError = function(message) {
        display_message(message, 'build-error');
        Y.log(message);
    };
};

/*
 * A function to return the current build records as displayed on the page
 */
var harvest_current_build_records = function() {
    var row_classes = ['package-build', 'binary-build'];
    var builds = [];
    Y.Array.each(row_classes, function(row_class) {
        Y.all('.'+row_class).each(function(row) {
            var row_id = row.getAttribute('id');
            if (Y.Array.indexOf(builds, row_id)<0) {
                builds.push(row_id);
            }
        });
    });
    return builds;
};

/*
 * Render build records and flash the new ones
 */
var display_build_records = function (build_records_markup, current_builds) {
    var target = Y.one('#builds-target');
    target.set('innerHTML', build_records_markup);
    var new_builds = harvest_current_build_records();
    var nr_new_builds = 0;
    Y.Array.each(new_builds, function(row_id) {
        if( Y.Array.indexOf(current_builds, row_id)>=0 ) {
            return;
        }
        nr_new_builds += 1;
        var row = Y.one('#'+row_id);
        var anim = Y.lp.anim.green_flash({node: row});
        anim.run();
    });
    return nr_new_builds;
};

/*
 * Perform any client side validation
 * Return: true if data is valid
 */
var validate = function(data) {
    var distros = data['field.distroseries'];
    if (Y.Object.size(distros) === 0) {
        request_build_response_handler.showError(
                "You need to specify at least one distro series for " +
                "which to build.", null);
        return false;
    }
    return true;
};

var get_new_builds_message = function(build_html, current_builds) {
    var nr_new;
    if (build_html === null) {
        return null;
    }
    nr_new = display_build_records(build_html, current_builds);
    if (nr_new > 1) {
        return Y.Lang.sub(MANY_BUILDS_MESSAGE, {nr_new: nr_new});
    }
    return ONE_BUILD_MESSAGE;
};

var get_info_header = function(new_builds_message, pending_build_info) {
    var info_header = Y.Node.create('<div></div>')
        .addClass('popup-build-informational');
    if (new_builds_message !== null) {
        info_header.append(Y.Node.create('<p></p>')
                .set('text', new_builds_message));
    }
    if (pending_build_info !== null) {
        info_header.append(Y.Node.create('<p></p>')
                .set('text', pending_build_info));
    }
    if (info_header.hasChildNodes()) {
        return info_header;
    }
    return null;
};

/*
 * The form submit function
 */
var do_request_builds = function(data, io_provider) {
    if (!validate(data)) {
        return;
    }
    request_build_submit_button.setAttribute("disabled", "disabled");
    var spinner_location = Y.one('.yui3-lazr-formoverlay-actions');
    create_temporary_spinner("Requesting builds...", spinner_location);

    var base_url = LP.cache.context.web_link;
    var submit_url = base_url+"/+builds";
    var current_builds = harvest_current_build_records();
    var y_config = {
        method: "POST",
        headers: {'Accept': 'application/json; application/xhtml'},
        on: {
            failure: request_build_response_handler.getFailureHandler(),
            success: request_build_response_handler.getSuccessHandler(
                function(handler, id, response) {
                var errors = [],
                    error_header = null,
                    error_header_text = "",
                    build_info, build_html, error_info,
                    nr_new, info_header, field_name;
                // The content type is used to tell a fully successful
                // request from a partially successful one. Successful
                // responses simply return the HTML snippet for the builds
                // table. If this ever causes problems, the view should
                // be changed to always return JSON and to provide an
                // attribute that identifies the type of response.
                content_type = response.getResponseHeader('Content-type');
                if( content_type !== 'application/json' ) {
                    // We got the HTML for the builds back, we're done.
                    request_build_overlay.hide();
                    display_build_records(
                            response.responseText, current_builds);
                } else {
                    // The response will be a json data object containing
                    // info about what builds there are, informational
                    // text about any builds already pending, plus any
                    // errors. The FormOverlay infrastructure only
                    // supports displaying errors so we will construct
                    // our own HTML where the informational text will be
                    // appropriately displayed.
                    build_info = Y.JSON.parse(response.responseText);

                    // The result of rendering the +builds view
                    build_html = build_info.builds;
                    // Any builds already pending (informational only)
                    pending_build_info = build_info.already_pending;
                    // Other more critical errors
                    error_info = build_info.errors;

                    info_header = get_info_header(
                        get_new_builds_message(
                            build_html, current_builds),
                            pending_build_info);

                    for (field_name in error_info) {
                        if (error_info.hasOwnProperty(field_name)) {
                            errors.push(error_info[field_name]);
                        }
                    }
                    error_container = Y.Node.create('<div></div>');
                    if (info_header !== null) {
                        error_container.append(info_header);
                        if (errors.length > 0) {
                            error_container.append(
                                Y.Node.create('<p></p>')
                                    .set(
                                        'text',
                                        "There were also some errors:"));
                        }
                    } else {
                        error_container.set(
                            'text', "There were some errors:");
                    }
                    display_errors(error_container, errors);
                }
            })
        },
        form: {
            id: request_build_overlay.form_node,
            useDisabled: true
        }
    };
    io_provider.io(submit_url, y_config);
};

/*
 * Show the temporary "Requesting..." text
 */
var create_temporary_spinner = function(text, node) {
    // Add the temp "Requesting build..." text
    var temp_spinner = Y.Node.create([
        '<div id="temp-spinner">',
        '<img src="/@@/spinner"/>',
        text,
        '</div>'].join(''));
    node.insert(temp_spinner, node);
};

/*
 * Destroy the temporary "Requesting..." text
 */
var destroy_temporary_spinner = function() {
    var temp_spinner = Y.one('#temp-spinner');
    var spinner_parent = temp_spinner.get('parentNode');
    spinner_parent.removeChild(temp_spinner);
};


//****************************************************************************
// This section contains code to manage the disabling of distro series
// selection on the request build form where there are already pending builds.
//****************************************************************************

var last_known_pending_builds;
// We store the original html for the distro series checkboxes so we can
// restore it when needed.
var distroseries_node_html;

var get_distroseries_nodes = function() {
    return request_build_overlay.form_node.all(
            "label[for^='field.distroseries.']");
};

var display_errors = function(container, error_msgs) {
    var errors_list, header;
    if (container === null) {
        if (error_msgs === null) {
            header = "An error occurred, please contact an administrator.";
        } else {
            header = "The following errors occurred:";
        }
        container = Y.Node.create('<div></div>')
            .set('text', header);
    }
    if (error_msgs !== null) {
        errors_list = Y.Node.create('<ul></ul>');
        if (Y.Lang.isString(error_msgs)){
            error_msgs = [error_msgs];
        }
        Y.each(error_msgs, function(error_msg){
            errors_list.append(Y.Node.create('<li></li>')
                .set('text', error_msg));
        });
        container.append(errors_list);
    }
    request_build_overlay.error_node.setContent(container);
};

/*
 * Callback used to enable/disable distro series selection when a different
 * ppa is selected.
 */
var ppa_changed = function(ppa_value, submit_button) {
    // Reset the disro series checkboxs to their default html.
    var distroseries_nodes = get_distroseries_nodes(),
        distroseries_node, distro, escaped_distro,
        disabled_checkbox_html, i;
    for (i = 0; i < distroseries_nodes.size(); i++) {
        distroseries_node = distroseries_nodes.item(i);
        distroseries_node.set("innerHTML", distroseries_node_html[i]);
        distroseries_node.removeClass("lowlight");
    }

    var nr_matches = 0;
    Y.Array.each(last_known_pending_builds, function(distroarchive) {
        if (ppa_value !== distroarchive[1]) {
            return;
        }

        for (i = 0; i < distroseries_nodes.size(); i++) {
            distroseries_node = distroseries_nodes.item(i);
            distro = distroseries_node.get("text").trim();
            if (distro === distroarchive[0]) {
                nr_matches += 1;
                escaped_distro = Y.Escape.html(distro);
                disabled_checkbox_html = Y.Lang.sub(
                    DISABLED_DISTROSERIES_CHECKBOX_HTML,
                    {distro: escaped_distro});
                distroseries_node.set("innerHTML", disabled_checkbox_html);
                distroseries_node.addClass("lowlight");
                break;
            }
        }
    });
    // If no distro series can be selected, no need to show the submit btn.
    if (nr_matches>0 && nr_matches === distroseries_nodes.size()) {
        submit_button.hide();
    } else {
        submit_button.show();
    }
};

var disable_existing_builds = function(submit_button, io_provider) {
    // Lookup a the exiting builds and parse the info into a data structure so
    // so that we can attempt to prevent the user from requesting builds
    // which are already pending. It's not foolproof since a build may finish
    // or be initiated after this initial lookup, but we do handle that
    // situation in the error handling.
    var ppa_selector, y_config;

    // The ui may not be ready yet.
    ppa_selector = request_build_overlay.form_node.one(
            "[name='field.archive']");
    if (ppa_selector === null) {
        return;
    }
    distroseries_node_html = [];
    last_known_pending_builds = [];
    y_config = {
        headers: {'Accept': 'application/json;'},
        on: {
            success:
                function(build_info) {
                    var distro_nodes,
                        size, build_record, distro_name, archive_token;
                    // We save the inner html of each distro series checkbox
                    // so we can restore it when required.
                    distro_nodes = get_distroseries_nodes();
                    distro_nodes.each(function(distro_node) {
                        distroseries_node_html.push(
                                distro_node.get("innerHTML"));
                    });

                    // We have a collection of the pending build info.
                    // The info is the distroseries displayname and archive
                    // token.
                    size = build_info.length;
                    for ( i = 0; i < size; i++ ) {
                        build_record = build_info[i];
                        distro_name = build_record.distroseries;
                        archive_token = build_record.archive;
                        last_known_pending_builds.push(
                                [distro_name, archive_token]);
                    }
                    ppa_selector.on("change", function(e) {
                        ppa_changed(ppa_selector.get("value"), submit_button);
                    });
                    ppa_changed(ppa_selector.get("value"), submit_button);
                }
        }
    };
    set_up_lp_client(io_provider);
    lp_client.named_get(
            LP.cache.context.self_link, 'getPendingBuildInfo', y_config);
};
}, "0.1", {"requires": [
    "dom", "node", "escape", "io-base", "lp.anim", "lp.ui.formoverlay",
    "lp.client"]});
