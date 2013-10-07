/* Copyright 2012 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE). */

YUI().use('lp.testing.runner', 'test', 'console',
          'lp.registry.timeline', function(Y) {

var Assert = Y.Assert;  // For easy access to isTrue(), etc.

var suite = new Y.Test.Suite("TimelineGraph Tests");

var MINIMAL_CONFIG = {
    timeline: [{
        name: 'trunk',
        uri: 'file:///firefox/trunk',
        is_development_focus: true,
        landmarks: []
    }]
};

var MEDIUM_CONFIG = {
    timeline: [
        {
            'name': 'testing',
            'uri': 'file:///firefox/1.0',
            'is_development_focus': true,
            'landmarks': [
                {
                    'code_name': 'warthog',
                    'date': '2056-10-16',
                    'name': 'alpha',
                    'type': 'milestone',
                    'uri': 'file:///firefox/+milestone/alpha'
                },
                {
                    'code_name': 'One (secure) Tree Hill',
                    'date': '2004-10-15',
                    'name': 'beta',
                    'type': 'release',
                    'uri': 'file:///firefox/trunk/beta'
                }
            ]
        }
    ]
};

var RESIZING_CONFIG = {
    timeline: [
        {name: '1', landmarks: [], is_development_focus: true},
        {name: '2', landmarks: [], is_development_focus: false},
        {name: '3', landmarks: [], is_development_focus: false},
        {name: '4', landmarks: [], is_development_focus: false},
        {name: '5', landmarks: [], is_development_focus: false},
        {name: '6', landmarks: [], is_development_focus: false},
        {name: '7', landmarks: [], is_development_focus: false},
        {name: '8', landmarks: [], is_development_focus: false},
        {name: '9', is_development_focus: false,
            landmarks: [
                {
                    'code_name': 'zamboni',
                    'date': '2200-05-26',
                    'name': 'ski',
                    'type': 'milestone',
                    'uri': 'file:///firefox/+milestone/alpha'
                }
            ]
         }
        ],
    resize_frame: 'timeline-iframe'
};

/*
 * A wrapper for the Y.Event.simulate() function.  The wrapper accepts
 * CSS selectors and Node instances instead of raw nodes.
 */
function simulate(widget, selector, evtype, options) {
    var bounding_box = widget.get('boundingBox');
    var rawnode = Y.Node.getDOMNode(bounding_box.one(selector));
    Y.Event.simulate(rawnode, evtype, options);
}

suite.add(new Y.Test.Case({

    name: 'minimal-config',

    setUp: function() {
        this.timeline_graph = new Y.lp.registry.timeline.TimelineGraph(
            MINIMAL_CONFIG);
        this.timeline_graph.render();
        this.content_box = this.timeline_graph.get('contentBox');
    },

    tearDown: function() {
        var bounding_box = this.timeline_graph.get('boundingBox');
        bounding_box.get('parentNode').removeChild(bounding_box);
        this.timeline_graph.destroy();
    },

    test_canvas_creation: function() {
        Assert.isInstanceOf(
            Y.lp.registry.timeline.TimelineGraph,
            this.timeline_graph,
            "TimelineGraph was not created.");

        Assert.isNotNull(
            this.content_box.one('canvas'),
            "A canvas should have been created.");
    },

    test_zoom_buttons: function() {
        var zoom_in = this.content_box.one('a.yui3-timelinegraph-zoom-in');
        Assert.isNotNull(
            zoom_in,
            'zoom_in link not found.');

        var zoom_out = this.content_box.one('a.yui3-timelinegraph-zoom-out');
        Assert.isNotNull(
            zoom_in,
            'zoom_out link not found.');
    },

    test_series_label: function() {
        var label = this.content_box.one('div#trunk');
        Assert.isNotNull(
            label,
            "Series label not found.");
        Assert.areEqual(
            'Development Focus Series',
            label.get('title'),
            "Unexpected series label title.");

        var link = label.one('a');
        Assert.isNotNull(
            link,
            "Series label does not contain a link.");
        Assert.areEqual(
            '<strong>trunk</strong>',
            link.get('innerHTML'),
            "Unexpected series link text.");
        Assert.areEqual(
            'file:///firefox/trunk',
            link.get('href'),
            "Unexpected series link href.");
    }
}));

// XXX sinzui 2011-06-07 bug=794597: This test requires a running server
// to pass the browser's js frame access rules.
//suite.add(new Y.Test.Case({

//    name: 'resizing-config',

//    setUp: function() {
//        this.timeline_graph = new Y.lp.registry.timeline.TimelineGraph(
//            RESIZING_CONFIG);
//        this.timeline_graph.render();
//        this.content_box = this.timeline_graph.get('contentBox');
//    },

//    tearDown: function() {
//        var bounding_box = this.timeline_graph.get('boundingBox');
//        bounding_box.get('parentNode').removeChild(bounding_box);
//        this.timeline_graph.destroy();
//    },

//    test_milestone_label_second_line: function() {
//        var label = this.content_box.one('div#ski');
//        var second_line = label.one('div');
//        Assert.areEqual(
//            '2200-05-26',
//            second_line.get('innerHTML'),
//            "Unexpected milestone date.");
//    },

//    test_resize_frame: function() {
//        var frame = parent.document.getElementById(
//            this.timeline_graph.resize_frame);

//        Assert.isNotNull(
//            frame,
//            'This test must be run in an iframe with id=' +
//            this.timeline_graph.resize_frame + '.');

//        var canvas = this.content_box.one('canvas');
//        var first_canvas_height = canvas.get('offsetHeight');
//        Assert.areEqual(1, this.timeline_graph.graph_scale);
//        Assert.areEqual(
//            canvas.get('offsetHeight'), frame.height,
//            '(1st) The frame was not resized to match the canvas.');

//        simulate(
//            this.timeline_graph, '.yui3-timelinegraph-zoom-in', 'click');

//        // The canvas is recreated in order to
//        // resize correctly in all browsers.
//        canvas = this.content_box.one('canvas');
//        Assert.areEqual(1.1, this.timeline_graph.graph_scale);
//        Assert.areEqual(
//            canvas.get('offsetHeight'), frame.height,
//            '(2nd) The frame was not resized to match the canvas.');
//        Assert.isTrue(
//            canvas.get('offsetHeight') > first_canvas_height,
//            'The canvas did not get scaled.');

//        simulate(
//            this.timeline_graph, '.yui3-timelinegraph-zoom-out', 'click');

//        canvas = this.content_box.one('canvas');
//        Assert.areEqual(1, this.timeline_graph.graph_scale);
//        Assert.areEqual(
//            canvas.get('offsetHeight'), frame.height,
//            '(3rd) The frame was not resized to match the canvas.');
//    }
//}));

suite.add(new Y.Test.Case({

    name: 'medium-config',

    setUp: function() {
        this.timeline_graph = new Y.lp.registry.timeline.TimelineGraph(
            MEDIUM_CONFIG);
        this.timeline_graph.render();
        this.content_box = this.timeline_graph.get('contentBox');
    },

    tearDown: function() {
        var bounding_box = this.timeline_graph.get('boundingBox');
        bounding_box.get('parentNode').removeChild(bounding_box);
        this.timeline_graph.destroy();
    },

    test_milestone_label: function() {
        var label = this.content_box.one('div#alpha');
        Assert.isNotNull(
            label,
            "Milestone label not found.");
        Assert.areEqual(
            'Milestone: warthog',
            label.get('title'),
            "Unexpected milestone label title.");

        var link = label.one('a');
        Assert.isNotNull(
            link,
            "Milestone label does not contain a link.");

        Assert.areEqual(
            'alpha',
            link.get('innerHTML'),
            "Unexpected milestone link text.");
        Assert.areEqual(
            'file:///firefox/+milestone/alpha',
            link.get('href'),
            "Unexpected milestone link href.");

        var second_line = label.one('div');
        Assert.isNull(
            second_line,
            "There should be no second line for landmarks when " +
            "resize_frame is false.");
    }
}));


suite.add(new Y.Test.Case({

    name: 'utils',

    test_isCanvasSupported: function() {
        supported = Y.lp.registry.timeline.isCanvasSupported();
        Assert.isTrue(supported);
        }
    }));

Y.lp.testing.Runner.run(suite);
});
