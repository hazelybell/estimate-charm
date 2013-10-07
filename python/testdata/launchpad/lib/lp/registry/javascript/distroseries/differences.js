/**
 * Copyright 2011 Canonical Ltd. This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * DistroSeries Differences.
 *
 * @module lp.registry.distroseries
 * @submodule differences
 */

YUI.add('lp.registry.distroseries.differences', function(Y) {

Y.log('loading lp.registry.distroseries.differences');

var namespace = Y.namespace('lp.registry.distroseries.differences'),
    testspace = Y.namespace('lp.registry.distroseries.differences.test'),
    formwidgets = Y.lp.app.formwidgets,
    widgets = Y.lp.registry.distroseries.widgets;

var PACKAGESET_FIELD = "field.packageset",
    PACKAGESET_FIELD_SELECTOR = "input[name=" + PACKAGESET_FIELD + "]",
    CHANGED_BY_FIELD = "field.changed_by",
    CHANGED_BY_FIELD_SELECTOR = "input[name=" + CHANGED_BY_FIELD + "]";


/**
 * Return an array of the packageset IDs that are configured in the
 * current window's query string.
 *
 * @param {String} qs The query string, typically obtained from
 *     window.location.search.
 */
var get_packagesets_in_query = function(qs) {
    var query = Y.QueryString.parse(qs.replace(/^[?]/, ""));
    /* Y.QueryString.parse() tries to be helpful and convert
       numeral strings into numbers... but we don't want that,
       so we have to convert back again. */
    var packagesets = query[PACKAGESET_FIELD];
    var n2s = function(n) { return n.toString(10); };
    /* Y.QueryString.parse() tries to be even more helpful by
       returning multiple values in an array but single values *not*
       in an array... I wonder why I'm using Y.QueryString.parse() at
       all. */
    if (Y.Lang.isArray(packagesets)) {
        return packagesets.map(n2s);
    }
    else if (Y.Lang.isValue(packagesets)) {
        return [n2s(packagesets)];
    }
    else {
        return [];
    }
};


/**
 * Return the first field.changed_by value from the current window's
 * query string.
 *
 * @param {String} qs The query string, typically obtained from
 *     window.location.search.
 */
var get_changed_by_in_query = function(qs) {
    var query = Y.QueryString.parse(qs.replace(/^[?]/, ""));
    var changed_by = query[CHANGED_BY_FIELD];
    if (Y.Lang.isArray(changed_by)) {
        return changed_by[0];
    }
    else if (Y.Lang.isValue(changed_by)) {
        return changed_by;
    }
    else {
        return null;
    }
};


/**
 * Convert the content of the given node into a js-action link.
 *
 * I would rather not do this with innerHTML, but I can't figure out
 * how to get YUI3 to wrap the contents of a node with another node,
 * including text nodes*.
 *
 * Also, node.get("text") is broken; given <a>foo<b/>bar</a>,
 * a.get("text") will return "foobar".
 *
 * @param {Y.Node} node The node to linkify.
 *
 */
var linkify = function(node) {
    /* Set the href so that the visual display is consistent with
       other links (cursor most notably). */
    var link = Y.Node.create(
        '<a href="#" class="js-action sprite edit" />');
    link.set("innerHTML", node.get("innerHTML"));
    node.empty().append(link);
    return link;
};


/**
 * Wire up a packageset picker that updates the given form.
 *
 * @param {Y.Node} origin The node that, when clicked, should activate
 *     the picker.
 * @param {Y.Node} form The form that the picker should update.
 */
var connect_packageset_picker = function(origin, form) {
    var picker_table =
        Y.Node.create("<table><tbody /></table>");
    var picker =
        new widgets.PackagesetPickerWidget()
            .set("name", "packagesets")
            .set("size", 5)
            .set("multiple", true)
            .render(picker_table.one("tbody"));

    picker.add_distroseries({
        api_uri: LP.cache.context.self_link,
        title: LP.cache.context.title,
        value: LP.cache.context.self_link
    });

    /* Buttons */
    var submit_button = Y.Node.create(
        '<button type="submit"/>')
           .set("text", "OK");
    var cancel_button = Y.Node.create(
        '<button type="button"/>')
           .set("text", "Cancel");

    /* When the form overlay is submitted the search filter form is
       modified and submitted. */
    var submit_callback = function(data) {
        // Remove all packagesets information previously recorded.
        form.all(PACKAGESET_FIELD_SELECTOR).remove();
        if (data.packagesets !== undefined) {
            Y.each(data.packagesets, function(packageset) {
                form.append(
                    Y.Node.create('<input type="hidden" />')
                        .set("name", PACKAGESET_FIELD)
                        .set("value", packageset));
            });
        }
        form.submit();
    };

    /* Form overlay. */
    var overlay = new Y.lp.ui.FormOverlay({
        align: {
            /* Align the centre of the overlay with the centre of the
               origin node. */
            node: origin,
            points: [
                Y.WidgetPositionAlign.CC,
                Y.WidgetPositionAlign.CC
            ]
        },
        headerContent: "<h2>Select package sets</h2>",
        form_content: picker_table,
        form_submit_button: submit_button,
        form_cancel_button: cancel_button,
        form_submit_callback: submit_callback,
        visible: false
    });
    overlay.render();

    var reposition_overlay = function() {
        /* Trigger alignment and constrain to the viewport. Should
           these not be automatic? Perhaps a bad interaction between
           widget-position-align and widget-positionposition-constrain? Only
           reposition when overlay is visible. */
        if (overlay.get("visible")) {
            overlay.set("align", overlay.get("align"));
            overlay.constrain(null, true);
        }
    };
    overlay.after("visibleChange", reposition_overlay);
    Y.on("windowresize", reposition_overlay);

    var packagesets_in_query =
        get_packagesets_in_query(window.location.search);
    var initialize_picker = function() {
        /* Set the current selection from the query string. Only
           initialize when overlay is visible. */
        if (overlay.get("visible")) {
            picker.set("choice", packagesets_in_query);
        }
    };
    /* XXX: GavinPanella 2011-07-20 bug=814531: We should be able to
       listen to choicesChange events from the picker widget but
       they're not fired consistently. Instead we initialize when
       showing the overlay, which is prone to a race condition (it may
       update the selection before the packageset picker has been
       populated with choices). */
    overlay.after("visibleChange", initialize_picker);

    /* Linkify the origin and show the overlay when it's clicked. */
    linkify(origin).on("click", function(e) {
        e.halt();
        overlay.show();
    });
};


/**
 * Wire up a person picker that updates the given form.
 *
 * @param {Y.Node} origin The node that, when clicked, should activate
 *     the picker.
 * @param {Y.Node} form The form that the picker should update.
 */
var connect_last_changed_picker = function(origin, form) {
    var config = {
        picker_type: "person",
        header: "Choose a person or a team",
        visible: false
    };
    var picker = new Y.lp.app.picker.create("ValidPersonOrTeam", config);

    /* Align the centre of the overlay with the centre of the origin
       node. */
    var align = {
        node: origin,
        points: [
            Y.WidgetPositionAlign.CC,
            Y.WidgetPositionAlign.CC
        ]
    };

    /* XXX: GavinPanella 2011-07-27 bug=817091: Alignment must be done
       after creating the picker because lp.app.picker.create()
       clobbers the passed configuration. */

    /* Pre-fill the search box with an existing selection. */
    picker.after("visibleChange", function(e) {
        if (e.newVal) {
            picker.set("align", align);  // Arg.
            var changed_by = get_changed_by_in_query(window.location.search);
            if (Y.Lang.isValue(changed_by)) {
                picker.set("selected_value", changed_by);
            }
        }
    });

    /* Update the search box. XXX: GavinPanella 2011-08-01 bug=819274:
       This should probably be handled by the picker itself. There is
       code in TextFieldPickerPlugin to do something similar, but
       that's probably not the right place either. */
    picker.after("selected_valueChange", function(e) {
        picker._search_input.set("value", e.newVal);
    });

    /* When the picker is saved the search filter form is modified and
       submitted. */
    picker.on("save", function(e) {
        form.all(CHANGED_BY_FIELD_SELECTOR).remove();
        if (e.value) {
            form.append(
                Y.Node.create('<input type="hidden" />')
                    .set("name", CHANGED_BY_FIELD)
                    .set("value", e.value));
        }
        form.submit();
    });

    /* Linkify the origin and show the picker when it's clicked. */
    linkify(origin).on("click", function(e) {
        e.halt();
        picker.show();
    });

    return picker;
};


// Exports.
namespace.connect_packageset_picker = connect_packageset_picker;
namespace.connect_last_changed_picker = connect_last_changed_picker;


// Exports for testing.
testspace.get_packagesets_in_query = get_packagesets_in_query;
testspace.get_changed_by_in_query = get_changed_by_in_query;
testspace.linkify = linkify;


}, "0.1", {"requires": [
               "lp.ui.formoverlay", "lp.app.formwidgets",
               "lp.app.picker", "lp.registry.distroseries.widgets",
               "node", "querystring-parse"]});
