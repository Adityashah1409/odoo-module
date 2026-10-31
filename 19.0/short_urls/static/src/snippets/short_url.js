import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

export class ShortUrlSnippet extends Interaction {
    static selector = ".s_short_url, .s_short_url_qr";
    dynamicContent = {
        ".s_short_url_copy": { "t-on-click": this.onCopy },
    };

    async willStart() {
        this.link = await this.waitFor(rpc("/short_urls/page_link", { path: window.location.pathname }));
    }

    start() {
        if (!this.link) {
            this.el.classList.add("d-none");
            return;
        }
        const input = this.el.querySelector(".s_short_url_value");
        if (input) {
            input.value = this.link.short_url;
        }
        const image = this.el.querySelector(".s_short_url_qr_img");
        if (image) {
            image.src = this.link.qr_url;
            image.alt = this.link.short_url;
        }
    }

    async onCopy() {
        if (!this.link) {
            return;
        }
        try {
            await navigator.clipboard.writeText(this.link.short_url);
        } catch {
            // clipboard API refused (no permission / not https): select the text instead
            const input = this.el.querySelector(".s_short_url_value");
            input.select();
        }
        this.el.querySelector(".s_short_url_copy").classList.replace("btn-primary", "btn-success");
    }
}

registry.category("public.interactions").add("short_urls.short_url_snippet", ShortUrlSnippet);
