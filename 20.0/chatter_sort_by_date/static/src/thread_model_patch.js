import { Thread } from "@mail/core/common/thread_model";
import { patch } from "@web/core/utils/patch";

/**
 * "Oldest first" in the chatter: load the thread from its first message instead of the newest ones,
 * newer messages come when scrolling down.
 */
patch(Thread.prototype, {
    setup() {
        super.setup();
        this.chatterOldestFirst = false;
    },

    get isChatterThread() {
        return Boolean(this.id && this.model && !this.channel && this.model !== "mail.box");
    },

    async fetchNewMessages() {
        if (this.chatterOldestFirst && this.isChatterThread && !this.isLoaded) {
            return this.chatterLoadOldest();
        }
        return super.fetchNewMessages(...arguments);
    },

    async chatterLoadOldest() {
        if (!this.isChatterThread || this.status === "loading") {
            return;
        }
        this.scrollTop = undefined;
        // "after -1": the server returns the first messages of the thread
        const fetched = await this.fetchMessages({
            fetchParams: { after: -1, limit: this.initialFetchLimit },
        });
        this.messages = fetched;
        this.loadOlder = false;
        this.loadNewer = fetched.length >= this.initialFetchLimit;
    },

    async chatterLoadNewest() {
        if (!this.isChatterThread) {
            return;
        }
        Object.assign(this, {
            messages: [],
            isLoaded: false,
            loadOlder: false,
            loadNewer: false,
            scrollTop: "bottom",
        });
        await this.fetchNewMessages();
    },
});
