import { Chatter } from "@mail/chatter/web_portal/chatter";
import { patch } from "@web/core/utils/patch";

import { ChatterPinnedBar } from "./pinned_bar/pinned_bar";

patch(Chatter, {
    components: { ...Chatter.components, ChatterPinnedBar },
});
