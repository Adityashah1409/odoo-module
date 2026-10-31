import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("short_urls_snippet_tour", {
    url: "/share-me",
    steps: () => [
        {
            content: "The short link of the page is filled in",
            trigger: ".s_short_url_value:value(/\\/s\\/share$/)",
        },
        {
            content: "The QR code points to it",
            trigger: ".s_short_url_qr_img[src='/short_urls/qr/share.png']",
        },
        {
            content: "Copy",
            trigger: ".s_short_url_copy",
            run: "click",
        },
    ],
});
