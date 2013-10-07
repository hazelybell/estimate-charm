YUI.add('lp.app.comment', function(Y) {

var namespace = Y.namespace('lp.app.comment');

namespace.CommentList = Y.Base.create('commentlist', Y.Widget, [], {

    /**
     * Update a comment appearance on hide commands.
     *
     * @method update_comment
     */
    update_comment: function (link, comment) {
        var text = link.get('text').trim();
        if (text === this.get('hide_text')) {
            comment.removeClass(this.get('hidden_class'));
            link.set('text', this.get('unhide_text'));
        } else {
            comment.addClass(this.get('hidden_class'));
            link.set('text', this.get('hide_text'));
        }
    },

    /**
     * Set the comment visibility.
     *
     * @method set_visibility
     */
    set_visibility: function (parameters, callbacks) {
        // comment_context must be setup on pages using this js, and is the
        // context for a comment (e.g. bug).
        var comment_context = LP.cache.comment_context;
        var lp_client = new Y.lp.client.Launchpad();
        var config = {
            on: {
                success: callbacks.success,
                failure: callbacks.failure
                },
            parameters: parameters
            };
        lp_client.named_post(
            comment_context.self_link, 'setCommentVisibility', config);
    },

    /**
     * toggle the hidden status of the comment.
     *
     * @method toggle_hidden
     */
    toggle_hidden: function (e) {
        e.halt();
        var link = e.target;
        var comment = link.get('parentNode').get('parentNode');
        var visible = comment.hasClass('adminHiddenComment');
        var that = this;
        var comment_number = parseInt(
                link.get('id').replace('mark-spam-', ''), 10);
        parameters = {
            visible: visible,
            comment_number: comment_number
            };
        this.set_visibility(parameters, {
            // We use red flash on failure so admins know it didn't work.
            // There's no green flash on success, b/c the change in bg
            // color provides an immediate visual cue.
            success: function () {
                that.update_comment(link, comment);
                comment.toggleClass(that.get('hidden_class'));
            },
            failure: function () {
                Y.lp.anim.red_flash({node:comment});
            }
        });
    },

    destructor: function() {
        var comment_list_container = this.get('comment_list_container');
        comment_list_container.detachAll();
    },

    bindUI: function () {
        var comment_list_container = this.get('comment_list_container');
        comment_list_container.delegate(
            'click', this.toggle_hidden, 'a.mark-spam', this);
    }
}, {
    ATTRS: {
        hidden_class: { value: "adminHiddenComment" },
        hide_text: { value: "Hide comment" },
        unhide_text: { value: "Unhide comment" },
        comment_list_container: {
            valueFn: function () {
                return Y.one('#maincontentsub');
            }
        }
    }
});

namespace.Comment = Y.Base.create('comment', Y.Widget, [], {
    /**
     * Initialize the Comment
     *
     * @method initializer
     */
    initializer: function(cfg) {
        this.submit_button = this.get_submit();
        this.comment_input = Y.one(
            '#add-comment-form [id="field.comment"]');
        this.error_handler = new Y.lp.client.ErrorHandler();
        this.error_handler.clearProgressUI = Y.bind(
            this.clearProgressUI, this);
        this.error_handler.showError = Y.bind(function (error_msg) {
            Y.lp.app.errors.display_error(this.submit_button, error_msg);
        }, this);
        this.progress_message = Y.Node.create(
            '<span class="update-in-progress-message">Saving...</span>');
    },

    /**
     * Return the Submit button.
     *
     * This is provided so that it can be overridden in subclasses.
     *
     * @method get_submit
     */
    get_submit: function(){
        return Y.one('#add-comment-form input[id="field.actions.save"]');
    },
    /**
     * Implementation of Widget.renderUI.
     *
     * This redisplays the submit button, in case it has been hidden by
     * the web page.
     *
     * @method renderUI
     */
    renderUI: function() {
        this.submit_button.addClass('js-action');
        this.submit_button.setStyle('display', 'inline');
    },
    /**
     * Ensure that the widget's values are suitable for submission.
     *
     * The contents of the comment field must contain at least one
     * non-whitespace character.
     *
     * @method validate
     */
    validate: function() {
        return Y.Lang.trim(this.comment_input.get('value')) !== '';
    },
    /**
     * Make the widget enabled or disabled.
     *
     * @method set_disabled
     * @param disabled A boolean, true if the widget is disabled.
     */
    set_disabled: function(disabled){
        this.comment_input.set('disabled', disabled);
    },
    /**
     * Add the widget's comment as a new comment, updating the display.
     *
     * @method add_comment
     * @param e An event
     */
    add_comment: function(e){
        e.halt();
        /* Don't try to add an empty comment. */
        if (!this.validate()) {
            return;
        }
        this.activateProgressUI('Saving...');
        this.post_comment(Y.bind(function(message_entry) {
            this.get_comment_HTML(
                message_entry, Y.bind(this.insert_comment_HTML, this));
            this._add_comment_success();
        }, this));
    },
    /**
     * A callable hook for firing extra events.
     */
    _add_comment_success: function() {},
    /**
     * Post the comment to the Launchpad API
     *
     * @method post_comment
     * @param callback A callable to call if the post is successful.
     */
    post_comment: function(callback) {
        var config = {
            on: {
                success: callback,
                failure: this.error_handler.getFailureHandler()
            },
            parameters: {content: this.comment_input.get('value')}
        };
        this.get('lp_client').named_post(
            LP.cache.bug.self_link, 'newMessage', config);
    },
    /**
     * Retrieve the HTML of the specified message entry.
     *
     * @method get_comment_HTML
     * @param message_entry The comment to get the HTML for.
     * @param callback On success, call this with the HTML of the comment.
     */
    get_comment_HTML: function(message_entry, callback){
        var config = {
            on: {
                success: callback
            },
            accept: Y.lp.client.XHTML
        };
        // Randomize the URL to fake out bad XHR caching.
        var randomness = '?' + Math.random();
        var message_entry_url = message_entry.get('self_link') + randomness;
        this.get('lp_client').get(message_entry_url, config);
    },
    /**
     * Insert the specified HTML into the page.
     *
     * @method insert_comment_HTML
     * @param message_html The HTML of the comment to insert.
     */
    insert_comment_HTML: function(message_html) {
        var fieldset = Y.one('#add-comment-form');
        var comment = Y.Node.create(message_html);
        fieldset.get('parentNode').insertBefore(comment, fieldset);
        this.reset_contents();
        if (this.get('animate')) {
            Y.lp.anim.green_flash({node: comment}).run();
        }
    },
    /**
     * Reset the widget to a blank state.
     *
     * @method reset_contents
     */
    reset_contents: function() {
          this.clearProgressUI();
          this.comment_input.set('value', '');
          this.syncUI();
    },
    /**
     * Activate indications of an operation in progress.
     *
     * @param message A user message describing the operation in progress.
     */
    activateProgressUI: function(message){
        this.progress_message.set('innerHTML', message);
        this.set_disabled(true);
        this.submit_button.get('parentNode').replaceChild(
            this.progress_message, this.submit_button);
    },
    /**
     * Stop indicating that an operation is in progress.
     *
     * @method clearProgressUI
     */
    clearProgressUI: function(){
          this.progress_message.get('parentNode').replaceChild(
              this.submit_button, this.progress_message);
          this.set_disabled(false);
    },


    /**
     * Implementation of Widget.bindUI: Bind events to methods.
     *
     * Key and mouse presses (e.g. mouse paste) call syncUI, in case the submit
     * button needs to be updated.  Clicking on the submit button invokes
     * add_comment.
     *
     * @method bindUI
     */
    bindUI: function(){
        this.comment_input.on('keyup', this.syncUI, this);
        this.comment_input.on('mouseup', this.syncUI, this);
        this.submit_button.on('click', this.add_comment, this);
    },
    /**
     * Implementation of Widget.syncUI: Update appearance according to state.
     *
     * This just updates the submit button.
     *
     * @method syncUI
     */
    syncUI: function(){
        this.submit_button.set('disabled', !this.validate());
    }
}, {
    ATTRS: {
        lp_client: {
            valueFn: function() { return new Y.lp.client.Launchpad() } 
        },
        animate: { value: true }
    }
});

namespace.CodeReviewComment = Y.Base.create(
    'codereviewcomment', namespace.Comment, [],
{
    /**
     * Initialize the CodeReviewComment
     *
     * @method initializer
     */
    initializer: function() {
        this.vote_input = Y.one('[id="field.vote"]');
        this.review_type = Y.one('[id="field.review_type"]');
        this.in_reply_to = null;
    },
    /**
     * Return the Submit button.
     *
     * @method get_submit
     */
    get_submit: function(){
        return Y.one('[id="field.actions.add"]');
    },
    /**
     * Return the vote value selected, or null if none is selected.
     *
     * @method get_vote
     */
    get_vote: function() {
        var selected_idx = this.vote_input.get('selectedIndex');
        var selected = this.vote_input.get('options').item(selected_idx);
        if (selected.get('value') === ''){
            return null;
        }
        return selected.get('innerHTML');
    },
    /**
     * Ensure that the widget's values are suitable for submission.
     *
     * This allows the vote to be submitted, even when no text is specified
     * for the comment.
     *
     * @method validate
     */
    validate: function(){
        if (this.get_vote() !== null) {
            return true;
        }
        return namespace.Comment.prototype.validate.apply(this);
    },
    /**
     * Make the widget enabled or disabled.
     *
     * @method set_disabled
     * @param disabled A boolean, true if the widget is disabled.
     */
    set_disabled: function(disabled){
        namespace.Comment.prototype.set_disabled.call(this, disabled);
        this.vote_input.set('disabled', disabled);
        this.review_type.set('disabled', disabled);
    },
    /**
     * Post the comment to the Launchpad API
     *
     * @method post_comment
     * @param callback A callable to call if the post is successful.
     */
    post_comment: function(callback) {
        var config = {
            on: {
                success: callback,
                failure: this.error_handler.getFailureHandler()
            },
            parameters: {
                content: this.comment_input.get('value'),
                subject: '',
                review_type: this.review_type.get('value'),
                vote: this.get_vote()
            }
        };
        if (this.in_reply_to !== null) {
            config.parameters.parent = this.in_reply_to.get('self_link');
        }
        this.get('lp_client').named_post(
            LP.cache.context.self_link, 'createComment', config);
    },
    /**
     * Retrieve the HTML of the specified message entry.
     *
     * @method get_comment_HTML
     * @param message_entry The comment to get the HTML for.
     * @param callback On success, call this with the HTML of the comment.
     */
    get_comment_HTML: function(comment_entry, callback) {
        fragment_url = 'comments/' + comment_entry.get('id') + '/+fragment';
        Y.io(fragment_url, {
            on: {
                success: function(id, response){
                    callback(response.responseText);
                },
                failure: this.error_handler.getFailureHandler()
            }
        });
    },
    /**
     * Event handler when a "Reply" link is clicked.
     *
     * @param e The Event object representing the click.
     */
    reply_clicked: function(e){
        e.halt();
        var reply_link = Y.lp.client.normalize_uri(e.target.get('href'));
        var root_url = reply_link.substr(0,
            reply_link.length - '+reply'.length);
        var object_url = '/api/devel' + root_url;
        this.activateProgressUI('Loading...');
        window.scrollTo(0, Y.one('#add-comment').getY());
        this.get('lp_client').get(object_url, {
            on: {
                success: Y.bind(function(comment){
                    this.set_in_reply_to(comment);
                    this.clearProgressUI();
                    this.syncUI();
                }, this),
                failure: this.error_handler.getFailureHandler()
            }
        });
    },
    /**
     * Set the comment that the new comment will be in reply to.
     *
     * @param comment The comment to be in reply to.
     */
    set_in_reply_to: function(comment) {
        this.in_reply_to = comment;
        this.comment_input.set('value', comment.get('as_quoted_email'));
    },
    /**
     * Reset the widget to a blank state.
     *
     * @method reset_contents
     */
    reset_contents: function() {
          this.review_type.set('value', '');
          this.vote_input.set('selectedIndex', 0);
          this.in_reply_to = null;
          namespace.Comment.prototype.reset_contents.apply(this);
    },
    /**
     * Insert the specified HTML into the page.
     *
     * @method insert_comment_HTML
     * @param message_html The HTML of the comment to insert.
     */
    insert_comment_HTML: function(message_html){
        var conversation = Y.one('[id=conversation]');
        var comment = Y.Node.create(message_html);
        conversation.appendChild(comment);
        this.reset_contents();
        Y.lp.anim.green_flash({node: comment}).run();
    },
    

    /**
     * Implementation of Widget.bindUI: Bind events to methods.
     *
     * In addition to Comment behaviour, mouseups and keyups on the vote and
     * review type cause a sync.
     *
     * @method bindUI
     */
    bindUI: function() {
        namespace.Comment.prototype.bindUI.apply(this);
        this.vote_input.on('keyup', this.syncUI, this);
        this.vote_input.on('change', this.syncUI, this);
        this.review_type.on('keyup', this.syncUI, this);
        this.review_type.on('mouseup', this.syncUI, this);
        Y.all('a.menu-link-reply').on('click', this.reply_clicked, this);
    },
    /**
     * Implementation of Widget.syncUI: Update appearance according to state.
     *
     * This enables and disables the review type, in addition to Comment
     * behaviour.
     *
     * @method syncUI
     */
    syncUI: function() {
        namespace.Comment.prototype.syncUI.apply(this);
        var review_type_disabled = (this.get_vote() === null);
        this.review_type.set('disabled', review_type_disabled);
    },
    /**
     * A callable hook for firing extra events.
     */
    _add_comment_success: function() {
        var VOTES_TABLE_PATH = '+votes';
        Y.io(VOTES_TABLE_PATH, {
            on: {
                success: function(id, response) {
                    var target = Y.one('#votes-target');
                    target.set('innerHTML', response.responseText);

                    var username = LP.links.me.substring(2);
                    var new_reviewer = Y.one('#review-' + username);
                    if (Y.Lang.isValue(new_reviewer)) {
                        var anim = Y.lp.anim.green_flash({
                            node: new_reviewer});
                        anim.run();
                    }
                },
                failure: function() {}
            }
        });
    }
}, {});

}, "0.1" ,{"requires":["base", "oop", "io", "widget", "node", "lp.client",
                       "lp.client.plugins", "lp.app.errors"]});
