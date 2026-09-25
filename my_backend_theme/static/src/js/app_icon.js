/**
 * Normalise an Odoo app menu into what the theme needs to draw its icon.
 *
 * Menus carry either `webIconData` (an image URL or base64 image data) or
 * `webIcon` ("icon,color,background"), the same data Odoo's own menus use.
 *
 * @param {Object} menu an app menu from the menu service
 * @returns {{ src?: string, icon?: string, color?: string, background?: string }}
 */
export function getAppIcon(menu) {
    const data = menu.webIconData;
    if (data) {
        if (data.startsWith("data:image") || data.startsWith("/")) {
            return { src: data };
        }
        const prefix = data.startsWith("P") ? "data:image/svg+xml;base64," : "data:image/png;base64,";
        return { src: prefix + data.replace(/\s/g, "") };
    }
    const [icon, color, background] = (menu.webIcon || "").split(",");
    if (icon && background !== undefined) {
        return { icon, color, background };
    }
    return { src: "/web/static/img/default_icon_app.png" };
}
