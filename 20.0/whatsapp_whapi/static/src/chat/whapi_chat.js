import { BusPlugin } from "@bus/services/bus_plugin";
import { Component, onMounted, onWillStart, onWillUnmount, proxy, signal, usePlugin, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { NotificationPlugin } from "@web/core/notifications/notification_plugin";
import { registry } from "@web/core/registry";
import { useDebounced } from "@web/core/utils/timing";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const { DateTime } = luxon;

const EMOJIS = [
    "😀", "😂", "😊", "😍", "😘", "😎", "🤔", "😅", "😢", "😡", "👍", "👎", "👏", "🙏", "💪", "👌",
    "✌️", "🤝", "🎉", "🔥", "✅", "❌", "⭐", "❤️", "💚", "📦", "🚚", "📅", "⏰", "💶", "🧾", "📎",
    "📞", "📍", "🙂", "😉", "🤩", "🥳", "😴", "🤷",
];

function readFile(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

export class WhapiChat extends Component {
    static template = "whatsapp_whapi.Chat";
    props = useProps({ ...standardActionServiceProps });

    setup() {
        this.orm = useService("orm");
        this.notification = usePlugin(NotificationPlugin);
        this.actionService = useService("action");
        this.busService = usePlugin(BusPlugin);
        this.messagesRef = signal.ref();
        this.fileRef = signal.ref();
        this.emojis = EMOJIS;
        const params = this.props.action.params || {};
        this.state = proxy({
            accounts: [],
            accountId: params.account_id || false,
            chats: [],
            search: "",
            mode: "all",
            chatId: params.chat_id || false,
            chat: null,
            messages: [],
            more: false,
            body: "",
            files: [],
            replyTo: null,
            panel: false,
            info: null,
            menuFor: false,
            emoji: false,
            templates: null,
            forward: null,
            messageInfo: null,
            recording: false,
            sending: false,
            addPhones: "",
        });
        this.reloadChats = useDebounced(() => this.loadChats(), 300);
        this.onBus = (payload) => this.onUpdate(payload);
        onWillStart(async () => {
            await this.loadChats();
            if (this.state.chatId) {
                await this.openChat(this.state.chatId);
            }
        });
        onMounted(() => {
            this.busService.subscribe("whapi/update", this.onBus);
            this.scrollToBottom();
        });
        onWillUnmount(() => {
            this.busService.unsubscribe("whapi/update", this.onBus);
            this.stopRecorder(true);
        });
    }

    // ------------------------------------------------------------------
    // data
    // ------------------------------------------------------------------
    async loadChats() {
        const result = await this.orm.call("whapi.chat", "whapi_load_chats", [], {
            account_id: this.state.accountId,
            search: this.state.search,
            mode: this.state.mode,
        });
        this.state.accounts = result.accounts;
        this.state.chats = result.chats;
    }

    async openChat(chatId) {
        this.state.chatId = chatId;
        this.state.replyTo = null;
        this.state.menuFor = false;
        this.state.templates = null;
        const result = await this.orm.call("whapi.chat", "whapi_load_messages", [[chatId]]);
        this.state.chat = result.chat;
        this.state.messages = result.messages;
        this.state.more = result.more;
        if (this.state.panel) {
            await this.loadInfo();
        }
        this.scrollToBottom();
        if (result.chat.unread) {
            await this.orm.call("whapi.chat", "whapi_mark_read", [[chatId]]);
            const chat = this.state.chats.find((c) => c.id === chatId);
            if (chat) {
                chat.unread = 0;
            }
        }
    }

    async loadOlder() {
        const first = this.state.messages[0];
        const result = await this.orm.call("whapi.chat", "whapi_load_messages", [[this.state.chatId]], {
            before_id: first && first.id,
        });
        this.state.messages = [...result.messages, ...this.state.messages];
        this.state.more = result.more;
    }

    async refreshMessages() {
        if (!this.state.chatId) {
            return;
        }
        const el = this.messagesRef();
        const atBottom = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        const result = await this.orm.call("whapi.chat", "whapi_load_messages", [[this.state.chatId]], {
            limit: Math.max(this.state.messages.length + 5, 60),
        });
        this.state.chat = result.chat;
        this.state.messages = result.messages;
        if (atBottom) {
            this.scrollToBottom();
        }
    }

    async onUpdate(payload) {
        if (this.state.accountId && payload.account_id !== this.state.accountId) {
            return;
        }
        this.reloadChats();
        if (payload.chat_id === this.state.chatId) {
            await this.refreshMessages();
            if (payload.incoming && !document.hidden) {
                this.orm.call("whapi.chat", "whapi_mark_read", [[this.state.chatId]]);
            }
            if (payload.group && this.state.panel) {
                this.loadInfo();
            }
        }
        if (payload.incoming && payload.notify && (payload.chat_id !== this.state.chatId || document.hidden)) {
            const title = payload.author || "WhatsApp";
            this.notification.add(payload.preview || "", { title, type: "info" });
            if (document.hidden && browser.Notification && browser.Notification.permission === "granted") {
                new browser.Notification(title, { body: payload.preview || "" });
            }
        }
    }

    scrollToBottom() {
        const scroll = () => {
            const el = this.messagesRef();
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        };
        browser.requestAnimationFrame(scroll);
        // pictures change the height once loaded
        browser.setTimeout(scroll, 400);
    }

    // ------------------------------------------------------------------
    // chat list
    // ------------------------------------------------------------------
    onSearch(ev) {
        this.state.search = ev.target.value;
        this.reloadChats();
    }

    setMode(mode) {
        this.state.mode = mode;
        this.loadChats();
    }

    onAccount(ev) {
        this.state.accountId = parseInt(ev.target.value) || false;
        this.state.chatId = false;
        this.state.chat = null;
        this.loadChats();
    }

    askNotifications() {
        if (browser.Notification && browser.Notification.permission === "default") {
            browser.Notification.requestPermission();
        }
    }

    get notificationsAsked() {
        return !browser.Notification || browser.Notification.permission !== "default";
    }

    initials(name) {
        return (name || "?")
            .replace(/[^\p{L}\p{N} ]/gu, "")
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2)
            .map((part) => part[0])
            .join("")
            .toUpperCase() || "#";
    }

    avatarColor(name) {
        const colors = ["#25a07b", "#3b82f6", "#a855f7", "#e11d48", "#f59e0b", "#0ea5e9", "#14b8a6", "#6366f1"];
        let hash = 0;
        for (const char of name || "") {
            hash = (hash * 31 + char.charCodeAt(0)) % 997;
        }
        return colors[hash % colors.length];
    }

    shortDate(value) {
        if (!value) {
            return "";
        }
        const date = deserializeDateTime(value);
        const now = DateTime.local();
        if (date.hasSame(now, "day")) {
            return date.toFormat("HH:mm");
        }
        if (now.diff(date, "days").days < 6) {
            return date.toFormat("ccc");
        }
        return date.toFormat("dd/MM/yy");
    }

    time(value) {
        return value ? deserializeDateTime(value).toFormat("HH:mm") : "";
    }

    // ------------------------------------------------------------------
    // messages
    // ------------------------------------------------------------------
    get blocks() {
        const blocks = [];
        let day = null;
        for (const message of this.state.messages) {
            const date = deserializeDateTime(message.date);
            const label = date.hasSame(DateTime.local(), "day")
                ? "Today"
                : date.toLocaleString(DateTime.DATE_MED_WITH_WEEKDAY);
            if (label !== day) {
                blocks.push({ key: `day-${message.id}`, kind: "day", label });
                day = label;
            }
            const last = blocks[blocks.length - 1];
            const isPicture =
                message.type === "image" && !message.deleted && !message.body && !message.reply;
            if (
                isPicture &&
                last.kind === "album" &&
                last.direction === message.direction &&
                last.author === message.author &&
                date.diff(last.date, "minutes").minutes < 3
            ) {
                last.messages.push(message);
                last.date = date;
                continue;
            }
            if (
                isPicture &&
                last.kind === "message" &&
                last.message.type === "image" &&
                !last.message.deleted &&
                !last.message.body &&
                !last.message.reply &&
                last.message.direction === message.direction &&
                last.message.author === message.author &&
                date.diff(deserializeDateTime(last.message.date), "minutes").minutes < 3
            ) {
                blocks[blocks.length - 1] = {
                    key: `album-${last.message.id}`,
                    kind: "album",
                    direction: message.direction,
                    author: message.author,
                    date,
                    messages: [last.message, message],
                };
                continue;
            }
            blocks.push({ key: `m-${message.id}`, kind: "message", message });
        }
        return blocks;
    }

    isImage(attachment) {
        return attachment.mimetype.startsWith("image/");
    }

    isAudio(attachment) {
        return attachment.mimetype.startsWith("audio/");
    }

    isVideo(attachment) {
        return attachment.mimetype.startsWith("video/");
    }

    statusIcon(message) {
        return (
            {
                draft: "schedule",
                sent: "check",
                delivered: "fa-check o_whapi_double",
                read: "fa-check o_whapi_double o_whapi_read",
                failed: "fa-exclamation-circle text-danger",
            }[message.state] || ""
        );
    }

    menuUp(message) {
        const index = this.state.messages.findIndex((m) => m.id === message.id);
        return index >= this.state.messages.length - 3 && this.state.messages.length > 4;
    }

    showGroupAuthor(message) {
        return this.state.chat && this.state.chat.type === "group" && message.direction === "in";
    }

    toggleMenu(message) {
        this.state.menuFor = this.state.menuFor === message.id ? false : message.id;
    }

    reply(message) {
        this.state.replyTo = message;
        this.state.menuFor = false;
    }

    async toggleStar(message) {
        message.starred = await this.orm.call("whapi.message", "whapi_toggle_star", [[message.id]]);
        this.state.menuFor = false;
    }

    async deleteMessage(message) {
        this.state.menuFor = false;
        await this.orm.call("whapi.message", "whapi_delete", [[message.id]]);
        await this.refreshMessages();
    }

    async showInfo(message) {
        this.state.menuFor = false;
        this.state.messageInfo = await this.orm.call("whapi.message", "whapi_info", [[message.id]]);
    }

    async startForward(message) {
        this.state.menuFor = false;
        const result = await this.orm.call("whapi.chat", "whapi_load_chats", [], {
            account_id: this.state.accountId,
            limit: 200,
        });
        this.state.forward = { message, chats: result.chats, selected: [], search: "" };
    }

    toggleForward(chatId) {
        const selected = this.state.forward.selected;
        const index = selected.indexOf(chatId);
        if (index >= 0) {
            selected.splice(index, 1);
        } else {
            selected.push(chatId);
        }
    }

    get forwardChats() {
        const search = (this.state.forward.search || "").toLowerCase();
        return this.state.forward.chats.filter((c) => !search || c.name.toLowerCase().includes(search));
    }

    async confirmForward() {
        const { message, selected } = this.state.forward;
        const count = await this.orm.call("whapi.message", "whapi_forward", [[message.id], selected]);
        this.state.forward = null;
        this.notification.add(`Forwarded to ${count} chat(s).`, { type: "success" });
        await this.loadChats();
        await this.refreshMessages();
    }

    // ------------------------------------------------------------------
    // composer
    // ------------------------------------------------------------------
    onBody(ev) {
        this.state.body = ev.target.value;
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    addEmoji(emoji) {
        this.state.body += emoji;
        this.state.emoji = false;
    }

    async toggleTemplates() {
        if (this.state.templates) {
            this.state.templates = null;
            return;
        }
        this.state.templates = await this.orm.call("whapi.chat", "whapi_render_templates", [[this.state.chatId]]);
    }

    useTemplate(template) {
        this.state.body = template.body;
        this.state.templates = null;
    }

    pickFiles() {
        this.fileRef().click();
    }

    async onFiles(ev) {
        for (const file of ev.target.files) {
            const url = await readFile(file);
            this.state.files.push({
                name: file.name,
                mimetype: file.type || "application/octet-stream",
                data: url.split(",")[1],
                url,
            });
        }
        ev.target.value = "";
    }

    removeFile(index) {
        this.state.files.splice(index, 1);
    }

    async send(voice = false) {
        if (this.state.sending || (!this.state.body.trim() && !this.state.files.length)) {
            return;
        }
        this.state.sending = true;
        try {
            await this.orm.call("whapi.chat", "whapi_send", [[this.state.chatId]], {
                body: this.state.body,
                attachments: this.state.files.map(({ name, mimetype, data }) => ({ name, mimetype, data })),
                reply_to_id: this.state.replyTo && this.state.replyTo.id,
                voice,
            });
            this.state.body = "";
            this.state.files = [];
            this.state.replyTo = null;
            await this.refreshMessages();
            this.scrollToBottom();
            this.loadChats();
        } finally {
            this.state.sending = false;
        }
    }

    async toggleRecording() {
        if (this.state.recording) {
            this.stopRecorder(false);
            return;
        }
        if (!browser.navigator.mediaDevices || !browser.MediaRecorder) {
            this.notification.add("Voice recording is not available in this browser.", { type: "warning" });
            return;
        }
        let stream;
        try {
            stream = await browser.navigator.mediaDevices.getUserMedia({ audio: true });
        } catch {
            this.notification.add("No microphone available.", { type: "warning" });
            return;
        }
        const mimeType = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus"].find((t) =>
            browser.MediaRecorder.isTypeSupported(t)
        );
        const recorder = new browser.MediaRecorder(stream, mimeType ? { mimeType } : {});
        const chunks = [];
        recorder.ondataavailable = (ev) => chunks.push(ev.data);
        recorder.onstop = async () => {
            stream.getTracks().forEach((track) => track.stop());
            if (this.recorderCancelled || !chunks.length) {
                return;
            }
            const type = (recorder.mimeType || "audio/ogg").split(";")[0];
            const blob = new Blob(chunks, { type });
            const url = await readFile(blob);
            this.state.files = [
                { name: `voice.${type.split("/")[1]}`, mimetype: type, data: url.split(",")[1], url },
            ];
            await this.send(true);
        };
        this.recorder = recorder;
        this.recorderCancelled = false;
        recorder.start();
        this.state.recording = true;
    }

    stopRecorder(cancel) {
        if (this.recorder && this.recorder.state !== "inactive") {
            this.recorderCancelled = cancel;
            this.recorder.stop();
        }
        this.state.recording = false;
    }

    // ------------------------------------------------------------------
    // side panel
    // ------------------------------------------------------------------
    async togglePanel() {
        this.state.panel = !this.state.panel;
        if (this.state.panel) {
            await this.loadInfo();
        }
    }

    async loadInfo() {
        this.state.info = await this.orm.call("whapi.chat", "whapi_group_info", [[this.state.chatId]]);
    }

    onAddPhones(ev) {
        this.state.addPhones = ev.target.value;
    }

    async addParticipants() {
        const phones = this.state.addPhones.split(/[,;\n]/).map((p) => p.trim()).filter(Boolean);
        this.state.info = await this.orm.call("whapi.chat", "whapi_add_participants", [[this.state.chatId], phones]);
        this.state.addPhones = "";
    }

    async removeParticipant(participant) {
        this.state.info = await this.orm.call("whapi.chat", "whapi_remove_participant", [
            [this.state.chatId],
            participant.id,
        ]);
    }

    async setAdmin(participant, admin) {
        this.state.info = await this.orm.call("whapi.chat", "whapi_set_admin", [
            [this.state.chatId],
            participant.id,
            admin,
        ]);
    }

    openPartner(partnerId) {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "res.partner",
            res_id: partnerId,
            views: [[false, "form"]],
        });
    }

    openChatRecord() {
        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "whapi.chat",
            res_id: this.state.chatId,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("whatsapp_whapi.chat", WhapiChat);
