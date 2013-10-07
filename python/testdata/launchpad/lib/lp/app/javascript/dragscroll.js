/* Copyright 2010 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * A milestone form overlay that can create a milestone within any page.
 *
 * @module Y.lp.app.dragscroll
 *
 * Based on dragscroll script by Nicolas Mendoza <nicolasm@opera.com>.
 * http://people.opera.com/nicolasm/userjs/dragscroll
 */

/**
 * This class allows you to scroll a page by dragging it.
 *
 * @class DragScrollEventHandler
 * @constructor
 */
YUI.add('lp.app.dragscroll', function(Y) {
    var namespace = Y.namespace('lp.app.dragscroll');

    namespace.DragScrollEventHandler = function() {
        this.dragging = false;
        this.last_position = null;
        this.event_listeners = [];
    };

    namespace.DragScrollEventHandler.prototype = {
        /**
        * Add the event handlers and change the cursor to indicate
        * that drag scrolling is active.
        *
        * @method activate
        */
        activate: function() {
            this._addEventListener("mousedown", this._startDragScroll);
            this._addEventListener("mouseup", this._stopDragScroll);
            this._addEventListener("mouseout", this._stopDragScroll);
            this._addEventListener("mousemove", this._dragScroll);
            this._setGrabCursor();
        },

        /**
        * Remove the event handlers and change the cursor to indicate
        * that drag scrolling is inactive.
        *
        * @method deactivate
        */
        deactivate: function() {
            document.removeEventListener(
                "mousedown", this._startDragScroll, false);
            this._removeEventListeners();
            this._unsetCursor();
        },

        _addEventListener: function(event_type, action) {
            // Wrap the method in a different function that forces
            // `this` to be the `DragScrollEventHandler` object.
            var self = this;
            var event_listener = function(e) {
                action.call(self, e);
            };
            var event_args = [event_type, event_listener, false];
            this.event_listeners.push(event_args);
            document.addEventListener.apply(document, event_args);
        },

        _removeEventListeners: function() {
            for (var i=0; i<this.event_listeners.length; i++) {
                var event_args = this.event_listeners[i];
                document.removeEventListener.apply(document, event_args);
            }
        },

        _unsetCursor: function() {
            document.body.style.cursor = '';
        },

        _setGrabCursor: function() {
            // Styles for W3C, IE, Mozilla, Webkit.
            // Unknown styles will fail to change the value.
            document.body.style.cursor = 'move';
            document.body.style.cursor = 'grab';
            document.body.style.cursor = '-moz-grab';
            document.body.style.cursor = '-webkit-grab';
        },

        _setGrabbingCursor: function() {
            // Styles for IE, Mozilla, and Webkit.
            // Unknown styles will fail to change the value.
            document.body.style.cursor = 'grabbing';
            document.body.style.cursor = '-moz-grabbing';
            document.body.style.cursor = '-webkit-grabbing';
        },

        /**
        * MouseDown event handler that causes _dragScroll to
        * take action when it receives a MouseMove event.
        *
        * @method _startDragScroll
        */
        _startDragScroll: function(e) {
            if (e.button === 0) {
                this.dragging = true;
                this.last_position = e;
                this._setGrabbingCursor();
            }
            e.preventDefault();
            e.stopPropagation();
        },

        /**
        * MouseUp & MouseOut event handler that causes _dragScroll to
        * once again ignore MouseMove events. Stopping dragging when
        * the MouseOut event occurs is helpful, since the MouseUp event
        * is not reliable, when the mouse is outside the window.
        *
        * @method _stopDragScroll
        */
        _stopDragScroll: function(e) {
            this.dragging = false;
            this._setGrabCursor();
            e.preventDefault();
            e.stopPropagation();
        },

        /**
        * MouseMove event handler that calculates the movement
        * by comparing the mouse positions in the current event and
        * the previous event.
        *
        * @method _dragScroll
        */
        _dragScroll: function(e) {
            if (this.dragging) {
                window.scrollBy(
                    this.last_position.clientX - e.clientX,
                    this.last_position.clientY - e.clientY);
                this.last_position = e;
                e.preventDefault();
                e.stopPropagation();
            }
        }
    };
}, "0.1", {"requires": []});
