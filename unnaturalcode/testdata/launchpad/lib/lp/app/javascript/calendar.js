/* Copyright 2009-2013 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Adds a Calendar widget to any input with the class 'yui2-calendar'.
 * If the input also has the class 'withtime', it will include time
 * fields and behave slightly differently.

 * @module Y.lp.app.calendar
 * @requires node, calendar, lp.ui.overlay
 */

YUI.add('lp.app.calendar', function(Y) {

var namespace = Y.namespace('lp.app.calendar');

/**
 * Convert a number to a string padding single-digit numbers with a zero.
 *
 * Return a string version of the number.
 *
 * @method pad_with_zero
 * @param num {Number} the number to convert and possibly pad.
 */
var pad_with_zero = function(num) {
    num_as_string = String(num);
    if (num_as_string.length === 1) {
        num_as_string = "0" + num_as_string;
    }
    return num_as_string;
};

/**
 * Create an initial value for a calendar widget based on a date input node.
 *
 * Return a Date object initialized to the correct initial value.
 *
 * @method get_initial_value_for_input
 * @param date_input_node {Y.Node} the input node from which the value should
 *     be extracted.
 */
var get_initial_value_for_input = function(date_input_node) {
    var date_match = (/(\d{4})-(\d{1,2})-(\d{2})/g).exec(
        date_input_node.get('value'));
    var time_match = (/(\d{2}):(\d{2})/g).exec(date_input_node.get('value'));

    var initial_value = new Date();
    if (date_match !== null) {
        initial_value.setFullYear(date_match[1]);
        initial_value.setMonth(parseInt(date_match[2], 10) - 1);
        initial_value.setDate(date_match[3]);

        if (time_match) {
            initial_value.setHours(time_match[1]);
            initial_value.setMinutes(time_match[2]);
        }
    }
    return initial_value;
};

/**
 * Create a node representing a time selection.
 *
 * Return a Node instance representing the time selection initialized
 * to the provided time.
 *
 * @method create_time_selector_node
 * @param selected_time {Date} an optional Date instance for inititial
 *     time values. If not provided the current time will be used instead.
 */
var create_time_selector_node = function(selected_time) {
    if (selected_time === null) {
        selected_time = new Date();
    }

    var inner_html = [
        '<div class="yui3-u" style="margin-top:1em;text-align:center">Time ',
        '  <input class="hours" maxlength="2" size="2"',
        '    value="' + pad_with_zero(selected_time.getHours()) +'"/>',
        '  : ',
        '  <input class="minutes" maxlength="2" size="2" ',
        '    value="' + pad_with_zero(selected_time.getMinutes()) + '"/>',
        '  <button class="lazr-pos lazr-btn" type="button">OK</button>',
        '  </a>',
        '</div>'].join("\n");

    return Y.Node.create(inner_html);
};

/**
 * Create a calendar widget in a containing div for a given date input.
 *
 * Returns a Y.Calendar rendered into the containing div and linked to the
 * given date input node. The input node will be updated with widget
 * interactions.
 *
 * @method create_calendar
 * @param date_input_node {Y.Node} the input node with which the widget
 *     is associated.
 * @param containing_div_node {Y.Node} the div within which the calendar
 *     widget is rendered.
 */
var create_calendar = function(date_input_node, containing_div_node,
                               include_time, overlay) {
    var initial_value = get_initial_value_for_input(date_input_node);

    var calendar = new Y.Calendar({
        contentBox: containing_div_node,
        showPrevMonth: true,
        showNextMonth: true,
        width: '300px',
        date: initial_value}).render();

    if (include_time) {
        time_selector_node = create_time_selector_node(initial_value);
        containing_div_node.appendChild(time_selector_node);
        var ok_button = time_selector_node.one('.lazr-btn');
        ok_button.on("click", function(e) {
            var value = calendar._getSelectedDatesList();
            if (value.length === 0) {
                return;
            }
            calendar.fire('selectionChange', {newSelection: value});
            clean_up(calendar, overlay);
        });
    }

    calendar.on("selectionChange", function(e) {
        var newDate = Y.Date.format(e.newSelection[0]);
        if (include_time) {
            hours = pad_with_zero(
                time_selector_node.one('.hours').get('value'));
            minutes = pad_with_zero(
                time_selector_node.one('.minutes').get('value'));
            newDate += " " + hours + ":" + minutes;
        }
        date_input_node.set('value', newDate);
        if (!include_time) {
            clean_up(calendar, overlay);
        }
    });

    return calendar;
};

var clean_up = function(calendar, overlay) {
    calendar.hide();
    calendar.destroy();
    overlay.hide();
    overlay.destroy();
};

/**
 * Add any calendar widgets required by the current page.
 *
 * Append a 'choose' link after any date inputs linked to a new
 * calendar widget rendered into a div after the choose link.
 *
 * This method is automatically run by setup_calendar_widgets(), but it
 * can be manually run if new date fields are added to the page.
 *
 * @method setup_calendar_widgets.
 */
namespace.add_calendar_widgets = function() {
    var date_inputs = Y.all('input.yui2-calendar');

    if (date_inputs === null) {
        return;
    }

    date_inputs.each(function(date_input) {
        // For each date input, insert the Choose... link right after
        // the date input node.
        // Has the calendar already been added?
        if (date_input.hasClass('calendar-added')) {
            return;
            }
        var parent_node = date_input.ancestor();
        var choose_link = Y.Node.create(
            '<span>(<a class="js-action" href="#">Choose...</a>)</span>');
        parent_node.insertBefore(choose_link, date_input.next());

        // Add a class to flag that this date-input is setup.
        date_input.addClass('calendar-added');
        // Setup the on click event to display the overlay.
        Y.on("click", function(e) {
            e.preventDefault();
            var include_time = date_input.hasClass('withtime');
            var container = Y.Node.create('<div class="yui3-g"></div>');
            var calendar_div = Y.Node.create('<div></div>');
            container.prepend(calendar_div);
            var title = "Choose a date";
            if (include_time) {
                title = title + " and time";
            }
            var header = Y.Node.create('<h2>' + title + '</h2>');
            var overlay = new Y.lp.ui.PrettyOverlay({
                headerContent: header,
                bodyContent: container});
            overlay.centered(choose_link);
            overlay.render();
            var calendar = create_calendar(
                date_input, calendar_div, include_time, overlay);
            overlay.on('cancel', function(e) {
                clean_up(calendar, overlay);
            });
            overlay.show();
            calendar.show();
        }, choose_link);
    });
};


/**
 * Setup any calendar widgets required by the current page.
 *
 * Append a 'choose' link after any date inputs linked to a new
 * calendar widget rendered into a div after the choose link.
 *
 * @method setup_calendar_widgets.
 */
namespace.setup_calendar_widgets = function() {
    Y.on("domready", namespace.add_calendar_widgets);
};

}, "0.1", {
    'requires': ['date', 'node', 'calendar', 'lp.ui.overlay']
});
