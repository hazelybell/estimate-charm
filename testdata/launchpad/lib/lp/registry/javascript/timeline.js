/* Copyright 2009 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * TimelineGraph widget.
 *
 * @module timeline
 */

YUI.add('lp.registry.timeline', function(Y) {

var module = Y.namespace('lp.registry.timeline');

var TIMELINE_GRAPH = 'timelinegraph';
var OBSOLETE_SERIES_STATUS = 'Obsolete';
var getCN = Y.ClassNameManager.getClassName;
var C_ZOOM_BOX = getCN(TIMELINE_GRAPH, 'zoom-box');
var C_ZOOM_IN = getCN(TIMELINE_GRAPH, 'zoom-in');
var C_ZOOM_OUT = getCN(TIMELINE_GRAPH, 'zoom-out');
var SECOND_MOUSE_BUTTON = 2;
// px spacing and sizes.
var MARGIN_LEFT = 20;
var MARGIN_TOP = 25;
var MARGIN_BOTTOM = 10;
var MILESTONE_RADIUS = 5;
var RELEASE_RADIUS = 5;
var ARROW_HEIGHT = 10;
var ARROW_WIDTH = 15;
// Defines angle of vertical timeline.
var ANGLE_DEGREES = 84;
var ANGLE_RADIANS = ANGLE_DEGREES / 180 * Math.PI;
var ANGLE_TANGENT = Math.tan(ANGLE_RADIANS);
// Font size in em's.
var FONT_SIZE = 1;
// Colors.
var LINE_COLOR = 'darkgreen';
var OBSOLETE_SERIES_COLOR = '#777777';
var MILESTONE_LINE_COLOR = 'darkgray';
var MILESTONE_FILL_COLOR = 'white';
var RELEASE_COLOR = 'black';
var ARROW_COLOR = LINE_COLOR;
// Zoom level (increase/decrease 10%)
var ZOOM_JUMPS = 1.1;

/**
 * Draw lines between a list of points.
 *
 * @method draw_line
 * @protected
 */
var draw_line = function(canvas_context, points, fill) {
    canvas_context.beginPath();
    canvas_context.moveTo(points[0].x, points[0].y);
    Y.each(points.slice(1), function(point, i) {
        canvas_context.lineTo(point.x, point.y);
    });
    // Draw!
    if (fill === true) {
        canvas_context.fill();
    } else {
        canvas_context.stroke();
    }
};

/**
 * A single x and y coordinate.
 *
 * @class Position
 * @constructor
 */
Position = function(x, y) {
    this.x = x;
    this.y = y;
};

Position.prototype = {
    copy: function() {
        return new Position(this.x, this.y);
    }
};

/**
 * These objects draw a horizontal line for the series
 * and place the text for each milestone and release on
 * the line.
 *
 * @class SeriesLine
 * @constructor
 */
SeriesLine = function(timeline_graph, series, start) {
    this.timeline_graph = timeline_graph;
    this.series = series;
    this.start = start;
    var tooltip = this.series.status + ' Series';
    if (this.series.is_development_focus) {
        tooltip = 'Development Focus Series';
    }

    this.labels = {};
    Y.each(this.series.landmarks, function(landmark, i) {
        var landmark_tooltip =
            landmark.type.charAt(0).toUpperCase() + landmark.type.substr(1);
        if (Y.Lang.isString(landmark.code_name)) {
            landmark_tooltip += ': ' + landmark.code_name;
        }

        var cfg = {id: landmark.name};
        if (Y.Lang.isString(this.timeline_graph.resize_frame)) {
            cfg.second_line = landmark.date;
        }
        this.labels[landmark.name] = this.timeline_graph.make_label(
            landmark.name, landmark_tooltip, landmark.uri, cfg);
    }, this);

    // If the frame is not going to be resized, the dates are
    // not displayed under the landmarks, so a single date
    // is displayed at the end of the series line where it
    // will not increase the vertical spacing.
    this.series_date_label = null;
    if (!Y.Lang.isString(this.timeline_graph.resize_frame)) {
        var i;
        for (i=0; i < this.series.landmarks.length; i++) {
            var landmark = this.series.landmarks[i];
            if (landmark.date !== null) {
                this.series_date_label = this.timeline_graph.make_label(
                    '', 'Last date in series', this.series.uri,
                    {second_line: landmark.date,
                    id: series.name + '-' + landmark.date});
                break;
            }
        }
    }

    // Center series label.
    var label_text = Y.Node.create('<strong/>');
    label_text.appendChild(document.createTextNode(series.name));
    this.center_series_label = this.timeline_graph.make_label(
        label_text, tooltip, this.series.uri,
        {id: series.name});
    // Left label.
    this.left_series_label = this.timeline_graph.make_label(
        '', tooltip, this.series.uri,
        {second_line: series.name, id: series.name});
    // Right label.
    this.right_series_label = this.timeline_graph.make_label(
        '', tooltip, this.series.uri,
        {second_line: series.name, id: series.name});
};

SeriesLine.prototype = {

    /**
     * Calculate the length of the horizontal line.
     *
     * @method get_length
     */
    get_length: function() {
        // No arrow at the end of obsolete series lines.
        var length = 0;
        if (this.series.status === OBSOLETE_SERIES_STATUS) {
            length = this.series.landmarks.length *
                     this.timeline_graph.landmark_spacing;
        } else {
            length = (this.series.landmarks.length + 1) *
                     this.timeline_graph.landmark_spacing;
        }
        // Display a line stub for series without any landmarks.
        return Math.max(length, this.timeline_graph.min_series_line_length);
    },

    /**
     * Calculate the vertical spacing of the horizontal lines based on twice
     * the height of the series name, plus the height of the landmark text,
     * which may or may not have a second line for the date.
     *
     * @method get_y_spacing()
     */
    get_y_spacing: function() {
        var max_y = 0;
        Y.each(this.series.landmarks, function(landmark, i) {
            var label = this.labels[landmark.name];
            max_y = Math.max(label.get('offsetHeight'));
        }, this);
        return max_y + (2 * RELEASE_RADIUS) +
               this.center_series_label.get('offsetHeight');
    },


    /**
     * The main method which is called by the ProjectLine.draw()
     * method for each series in the project.
     *
     * @method draw
     */
    draw: function() {
        // Horizontal line.
        var context = this.timeline_graph.canvas_context;
        var stop = new Position(
            this.start.x + this.get_length(),
            this.start.y);

        var thickness, offset;
        // Draw a line of various thicknesses as a rectangle.
        if (this.series.status === OBSOLETE_SERIES_STATUS) {
            thickness = 2;
            offset = -1;
            context.fillStyle = OBSOLETE_SERIES_COLOR;
        } else if (this.series.is_development_focus) {
            thickness = 4;
            offset = -2;
            context.fillStyle = LINE_COLOR;
        } else {
            thickness = 1;
            offset = 0;
            context.fillStyle = LINE_COLOR;
        }
        context.fillRect(
            this.start.x,
            this.start.y + offset,
            stop.x - this.start.x,
            stop.y - this.start.y + thickness);

        // Arrow at end of series line.
        if (this.series.status !== OBSOLETE_SERIES_STATUS) {
            this.timeline_graph.make_landmark(stop, 'arrow');
        }

        // Center series label.
        var center_position = new Position(
            this.start.x + (this.get_length() / 2),
            this.start.y - RELEASE_RADIUS);
        this.timeline_graph.place_label(
            center_position, this.center_series_label, 'center', 'above');


        // Only show the left and right series labels if the
        // series line is wider than the viewport (iframe).
        var line_width = this.get_length() * this.timeline_graph.graph_scale;
        if (line_width < Y.DOM.winWidth()) {
            this.left_series_label.setStyle('display', 'none');
            this.right_series_label.setStyle('display', 'none');
        } else {
            this.left_series_label.setStyle('display', 'block');
            this.right_series_label.setStyle('display', 'block');

            // Left series label.
            var left_position = new Position(
                this.start.x + 10,
                this.start.y - RELEASE_RADIUS);
            this.timeline_graph.place_label(
                left_position, this.left_series_label, 'right', 'above');

            // Right series label.
            var right_position = new Position(
                this.start.x + this.get_length(),
                this.start.y - RELEASE_RADIUS);
            this.timeline_graph.place_label(
                right_position, this.right_series_label, 'left', 'above');
        }

        if (this.series_date_label !== null) {
            var label_position = new Position(
                stop.x + (ARROW_WIDTH / 2), this.start.y);
            this.timeline_graph.place_label(
                label_position, this.series_date_label, 'right', 'middle');
        }

        // Landmark labels.
        Y.each(this.series.landmarks, function(landmark, i) {
            // The newest milestones are at the beginning, and
            // they need to be placed at the end of the horizontal
            // line.
            var position_index = this.series.landmarks.length - i;
            var landmark_position = new Position(
                this.start.x +
                (position_index * this.timeline_graph.landmark_spacing),
                this.start.y);

            this.timeline_graph.make_landmark(
                landmark_position, landmark.type);
            // We use the RELEASE_RADIUS to space both the milestone and the
            // release labels, so that the labels line up.
            var landmark_label_position = new Position(
                landmark_position.x, landmark_position.y + RELEASE_RADIUS);
            this.timeline_graph.place_label(
                landmark_label_position, this.labels[landmark.name],
                'center', 'below');
        }, this);
    }
};

/**
 * Class which draws the slanted vertical line representing
 * the project timeline and which instantiates the SeriesLine
 * objects which draw the horizontal lines.
 *
 * @class ProjectLine
 * @constructor
 */
ProjectLine = function(timeline_graph, timeline) {
    if (timeline.length === 0) {
        throw new Error("The timeline array is empty.");
    }
    this.timeline_graph = timeline_graph;
    this.timeline = timeline;

    this.series_lines = [];
    this.initSeries();

    this.start = this.series_lines[0].start.copy();
    var last_series = this.series_lines[this.series_lines.length-1];
    this.stop = last_series.start.copy();
};

ProjectLine.prototype = {

    /**
     * Instantiate each SeriesLine object and place it at the
     * correct point on the slanted vertical line. The series aren't
     * actuall drawn yet, since we need to loop through these objects
     * to calculate the landmark_spacing.
     *
     * @method initSeries
     */
    initSeries: function() {
        var current = new Position(0, MARGIN_TOP);
        var reversed_timeline = this.timeline.slice().reverse();
        Y.each(reversed_timeline, function(series, i) {
            var series_line = new SeriesLine(
                this.timeline_graph, series, current.copy());
            this.series_lines.push(series_line);

            var height = series_line.get_y_spacing();
            current.x -= height / ANGLE_TANGENT;
            current.y += height;
        }, this);

        if (current.x < MARGIN_LEFT) {
            var shift_x = -current.x + MARGIN_LEFT;
            Y.each(this.series_lines, function(series_line, i) {
                series_line.start.x += shift_x;
            }, this);
        }
    },

    /**
     * Calculate the width based on the number of landmarks
     * and half the length of the label for the last landmark
     * on the right.
     *
     * @method get_width
     */
    get_width: function() {
        var max_x = 0;
        Y.each(this.series_lines, function(series_line, i) {
            var landmarks = series_line.series.landmarks;
            var text_beyond_last_landmark;
            if (landmarks.length === 0) {
                // Even a project with zero landmarks needs to have
                // its one empty series displayed.
                text_beyond_last_landmark = 0;
            } else {
                var landmark = landmarks[landmarks.length-1];
                var label = this.series_lines[i].labels[landmark.name];
                text_beyond_last_landmark = label.get('offsetWidth') / 2;
            }
            var series_width =
                this.series_lines[i].start.x +
                this.series_lines[i].get_length() +
                text_beyond_last_landmark;
            max_x = Math.max(max_x, series_width);
        }, this);
        return max_x;
    },

    /**
     * Calculate the height based on the stop.y value, which
     * is based on the number of series. It also adds the
     * distance for the labels below the bottom series line.
     *
     * @method get_height
     */
    get_height: function() {
        // Grab any landmark label to get its height.
        var bottom_label_height = 0;
        var last_series = this.series_lines[this.series_lines.length-1];
        var key;
        for (key in last_series.labels) {
            if (last_series.labels.hasOwnProperty(key)) {
                var label = last_series.labels[key];
                bottom_label_height = Math.max(
                    bottom_label_height, label.get('offsetHeight'));
            }
        }
        return this.stop.y + bottom_label_height + RELEASE_RADIUS;
    },

    /**
     * Draw the project line and have each SeriesLine object draw itself.
     *
     * @method draw
     */
    draw: function() {
        var context = this.timeline_graph.canvas_context;
        context.strokeStyle = LINE_COLOR;
        draw_line(context, [this.start, this.stop]);
        Y.each(this.series_lines, function(series_line, i) {
            series_line.draw();
        }, this);
    }
};


/**
 * Does the browser support cavas?
 *
 * @method isCanvasSupported
 */
module.isCanvasSupported = function() {
    var elem = document.createElement('canvas');
    return !!(elem.getContext && elem.getContext('2d'));
   };


/**
 * The TimelineGraph widget will display an HTML5 canvas of a
 * project's series, milestones, and releases.
 *
 * @class TimelineGraph
 * @constructor
 * @extends Widget
 */
module.TimelineGraph = function() {
    module.TimelineGraph.superclass.constructor.apply(this, arguments);
};

module.TimelineGraph.NAME = TIMELINE_GRAPH;
module.TimelineGraph.ATTRS = {
    /**
     * JSON data describing the timeline of series, milestones, and releases.
     *
     * @attribute timeline
     * @type Array
     */
    timeline: { value: [] }
};

Y.extend(module.TimelineGraph, Y.Widget, {

    /**
     * Initialize the widget.
     *
     * @method initializer
     * @protected
     */
    initializer: function(cfg) {
        if (cfg === undefined || cfg.timeline === undefined) {
            throw new Error(
                "Missing timeline config argument for TimelineGraph.");
        }
        if (cfg !== undefined && cfg.resize_frame !== undefined) {
            if (!Y.Lang.isString(cfg.resize_frame)) {
                throw new Error(
                    "resize_frame config argument must be a string.");
            }
            if (Y.Lang.trim(cfg.resize_frame) === '') {
                throw new Error("resize_frame must not be empty.");
            }
            this.resize_frame = cfg.resize_frame;
        }
        this.graph_scale = 1;
    },

    /**
     * Increase the graph scale and redraw.
     *
     * @method zoom_in
     */
    zoom_in: function() {
        this.graph_scale *= ZOOM_JUMPS;
        this.syncUI();
    },

    /**
     * Decrease the graph scale and redraw.
     *
     * @method zoom_out
     */
    zoom_out: function() {
        this.graph_scale /= ZOOM_JUMPS;
        this.syncUI();
    },

    /**
     * The canvas has to be recreated each time with the new size, since
     * WebKit browsers do not handle resizing the canvas well.
     *
     * @method recreate_canvas
     */
    recreate_canvas: function() {
        var width = Math.ceil(
            this.graph_scale * (this.project_line.get_width() + MARGIN_LEFT));

        // The get_height() method already includes the MARGIN_TOP, so that
        // gets multiplied by the graph_scale. Alternatively, we could have
        // made changes elsewhere so that MARGIN_LEFT and MARGIN_TOP are
        // not scaled at all.
        var height = Math.ceil(
            (this.graph_scale * this.project_line.get_height()) +
            MARGIN_BOTTOM);

        if (this.canvas) {
            this.get('contentBox').removeChild(this.canvas);
        }
        this.canvas = Y.Node.create(
            '<canvas width="' + width + '" height="' + height + '"/>');
        this.get('contentBox').insertBefore(
            this.canvas, this.get('contentBox').get('children').item(0));
        if (Y.Lang.isString(this.resize_frame)) {
            var frame = parent.document.getElementById(this.resize_frame);
            if (frame === null) {
                Y.log('Frame not found: ' + this.resize_frame);
            }
            else {
                // Opera's offsetHeight and scrollHeight don't work as
                // expected, but the canvas height can be used since it is
                // the only element.
                frame.height = height;
            }
        }
    },

    /**
     * Set the timeline_graph.landmark_spacing attribute, which is
     * used by the SeriesLine objects and is based on the width
     * of the longest landmark label.
     *
     * @method calculate_landmark_spacing
     */
    calculate_landmark_spacing: function() {
        var max_label_width = 0;
        var series_max_label_width = 0;
        Y.each(this.project_line.series_lines, function(series_line, i) {
            series_max_label_width = Math.max(
                series_max_label_width,
                series_line.center_series_label.get('offsetWidth'));
            Y.each(series_line.labels, function(label, j) {
                // We have to set the font size here so that
                // offsetWidth will be correct.
                this.set_font_size(label);
                max_label_width = Math.max(
                    max_label_width, label.get('offsetWidth'));
            }, this);
        }, this);
        this.landmark_spacing = max_label_width + 5;
        this.min_series_line_length = series_max_label_width + 5;
    },

    /**
     * Set the font size.
     *
     * @method set_font_size
     */
    set_font_size: function(label) {
        label.setStyle(
            'fontSize',
            (FONT_SIZE * this.graph_scale) + 'em');
    },

    /**
     * This should show the most recent milestones or releases
     * on the development focus series.
     *
     * @method scroll_to_last_development_focus_landmark
     */
    scroll_to_last_development_focus_landmark: function(label) {
        var series_line = this.project_line.series_lines[0];
        var landmark = series_line.series.landmarks[0];
        if (landmark) {
            var landmark_label = series_line.labels[landmark.name];
            var date_label_width = 0;
            if (series_line.series_date_label !== null) {
                date_label_width =
                    series_line.series_date_label.get('offsetWidth');
            }
            var scroll_x =
                series_line.start.x + series_line.get_length() +
                ARROW_WIDTH + date_label_width -
                Y.DOM.winWidth();
            // scrollBy is relative, so adjust it by
            // the current scroll position.
            scroll_x -= window.scrollX;
            window.scrollBy(scroll_x, 0);
        }
    },

    /**
     * Draw items that do not get recreated for each zoom level.
     *
     * @method renderUI
     */
    renderUI: function() {
        // Opera needs the "&nbsp;" so that it doesn't collapse
        // the height of the <a> and push the background image
        // above the div.
        this.zoom_in_button = Y.Node.create(
            '<a class="bg-image"  ' +
            '   style="background-image: url(/@@/zoom-in);' +
            '          height: 14px">&nbsp;</a>');
        this.zoom_in_button.addClass(C_ZOOM_IN);
        this.zoom_out_button = Y.Node.create(
            '<a class="bg-image" ' +
            '   style="background-image: url(/@@/zoom-out);' +
            '          height: 14px"></a>');
        this.zoom_out_button.addClass(C_ZOOM_OUT);
        var zoom_box = Y.Node.create(
            '<div style="' +
            'background-color: white; position: fixed; ' +
            'top: 0px; left: 0px; padding-left: 2px; ' +
            'cursor: pointer; z-index: 100"/>');
        zoom_box.addClass(C_ZOOM_BOX);
        zoom_box.appendChild(this.zoom_in_button);
        zoom_box.appendChild(this.zoom_out_button);
        var contentBox = this.get('contentBox');
        contentBox.appendChild(zoom_box);
        this.project_line = new ProjectLine(this, this.get('timeline'));
    },

    /**
     * Hook up UI events.
     *
     * @method bindUI
     */
    bindUI: function() {
        this.zoom_in_button.on('click', function() {
            this.zoom_in();
        }, this);
        this.zoom_out_button.on('click', function() {
            this.zoom_out();
        }, this);
    },

    /**
     * Redraw everything that changes at each zoom level.
     *
     * @method syncUI
     */
    syncUI: function() {
        // Resizing the canvas requires destroying the old canvas and
        // creating a new one due to rendering issues in WebKit.
        this.calculate_landmark_spacing();
        var contentBox = this.get('contentBox');
        this.recreate_canvas();
        var dom_canvas = Y.Node.getDOMNode(this.canvas);
        this.canvas_context = dom_canvas.getContext('2d');

        // Zoom in or out.
        this.canvas_context.scale(this.graph_scale, this.graph_scale);

        this.project_line.draw();
    },

    /**
     * Create the label for each landmark, but don't place them yet,
     * since we need to calculate the spacing between landmarks based
     * on the width of the longest label text.
     *
     * @method make_label
     */
    make_label: function(text, tooltip, uri, cfg) {
        if (cfg === undefined) {
            cfg = {};
        }
        var label = Y.Node.create(
            '<div style="white-space: nowrap; text-align: center"/>');
        if (Y.Lang.isString(cfg.id)) {
            label.set('id', cfg.id);
        }
        var text_node;
        if (text instanceof Y.Node || text instanceof Text) {
            text_node = text;
        } else {
            text_node = document.createTextNode(text);
        }
        if (uri) {
            var link = Y.Node.create('<a/>');
            link.appendChild(text_node);
            link.on('click', function(e) {
                // Safari also fires the click event for the 2nd mouse button,
                // and we don't want to prevent that default action.
                if (e.which !== SECOND_MOUSE_BUTTON) {
                    parent.location.href = uri;
                    e.preventDefault();
                }
            });
            // Middle-clicking to open a new tab still works if
            // the href is set.
            link.set('href', uri);
            label.appendChild(link);
        } else {
            var span = Y.Node.create('<span/>');
            span.appendChild(text_node);
            label.appendChild(span);
        }
        label.setStyle('position', 'absolute');
        if (tooltip) {
            label.set('title', tooltip);
        }
        if (Y.Lang.isString(cfg.second_line)) {
            var div = Y.Node.create(
                '<div style="color: #aaaaaa; font-size: 70%"/>');
            div.appendChild(document.createTextNode(cfg.second_line));
            label.appendChild(div);
        }
        this.get('contentBox').appendChild(label);
        return label;
    },

    /**
     * After this.landmark_spacing has been calculated,
     * we can place the label.
     *
     * @method place_label
     */
    place_label: function(position, label, x_align, y_align) {
        var graph_scale = this.graph_scale;
        var dom_canvas = Y.Node.getDOMNode(this.canvas);

        // Set the size here also, for any labels that are not
        // for landmarks, which are already set through
        // calculate_landmark_spacing.
        this.set_font_size(label);

        // Find where the canvas is placed on the page, and
        // center the text under the landmark.
        var label_height = label.get('offsetHeight');
        var y_align_offset;
        if (y_align === 'above') {
            y_align_offset = -label_height;
        } else if (y_align === 'below') {
            y_align_offset = 0;
        } else if (y_align === 'middle') {
            y_align_offset = -(label_height / 2);
        } else {
            throw "Invalid y_align argument: " + y_align;
        }

        var x_align_offset;
        if (x_align === 'left') {
            x_align_offset = -label.get('offsetWidth');
        } else if (x_align === 'center') {
            x_align_offset = -(label.get('offsetWidth') / 2);
        } else if (x_align === 'right') {
            x_align_offset = 0;
        } else {
            throw "Invalid x_align argument: " + x_align;
        }

        var scaled_position = new Position(
            position.x * graph_scale +
            dom_canvas.offsetLeft + x_align_offset,
            position.y * graph_scale +
            dom_canvas.offsetTop + y_align_offset);

        label.setStyle('left', scaled_position.x + "px");
        label.setStyle('top', scaled_position.y + "px");
    },

    /**
     * Draw a square for milestones and a circle for releases
     * on the series line. Also, place the name label
     * underneath the landmark.
     *
     * @method make_landmark
     */
    make_landmark: function(position, type) {
        var context = this.canvas_context;
        if (type === 'milestone') {
            // Fill circle first.
            context.fillStyle = MILESTONE_LINE_COLOR;
            context.beginPath();
            context.arc(
                position.x, position.y, MILESTONE_RADIUS, 0,
                (Math.PI*2), true);
            context.fill();
            // Overlay the fill color in the center.
            context.fillStyle = MILESTONE_FILL_COLOR;
            context.beginPath();
            context.arc(
                position.x, position.y, MILESTONE_RADIUS-2, 0,
                (Math.PI*2), true);
            context.fill();
        } else if (type === 'release') {
            context.fillStyle = RELEASE_COLOR;
            context.beginPath();
            context.arc(
                position.x, position.y, RELEASE_RADIUS, 0,
                (Math.PI*2), true);
            context.fill();
        } else if (type === 'arrow') {
            context.fillStyle = ARROW_COLOR;
            var point = position.copy();
            // Make sure the tip of the arrow isn't blunted by the
            // development focus series line.
            point.x += 3;
            var path = [point];

            point = point.copy();
            point.x -= ARROW_WIDTH / 2;
            point.y -= ARROW_HEIGHT / 2;
            path.push(point);

            point = point.copy();
            point.x += ARROW_WIDTH / 4;
            point.y += ARROW_HEIGHT / 2;
            path.push(point);

            point = point.copy();
            point.x -= ARROW_WIDTH / 4;
            point.y += ARROW_HEIGHT / 2;
            path.push(point);

            draw_line(context, path, true);
        }
        else {
            throw "Unknown landmark type: " + type;
        }
    }
});

}, "0.1", {"requires": ["oop", "node", "widget"]});
