import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";

const pad = (n) => String(n).padStart(2, "0");

/** "YYYY-MM-DD" in the register's local time. */
export function localDate(now) {
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** Happy-hour window: [hour_from, hour_to[, crossing midnight when the end is before the start. */
export function inHours(rule, now) {
    const from = rule.hour_from || 0;
    const to = rule.hour_to || 0;
    if (!from && !to) {
        return true;
    }
    const hour = now.getHours() + now.getMinutes() / 60;
    return from <= to ? hour >= from && hour < to : hour >= from || hour < to;
}

function categoryIds(template) {
    const ids = new Set();
    for (let categ of template?.pos_categ_ids || []) {
        // a rule on a category includes its sub-categories
        while (categ && !ids.has(categ.id)) {
            ids.add(categ.id);
            categ = categ.parent_id;
        }
    }
    return ids;
}

/** product: a product.product (order line) or a product.template (product card). */
export function ruleMatchesProduct(rule, product) {
    const template = product?.product_tmpl_id || product;
    if (!template) {
        return false;
    }
    if (rule.applies_on === "all") {
        return true;
    }
    if (rule.applies_on === "products") {
        return rule.product_tmpl_ids.includes(template.id);
    }
    const ids = categoryIds(template);
    return rule.pos_categ_ids.some((id) => ids.has(id));
}

export function ruleIsActive(rule, now) {
    const today = localDate(now);
    return (
        (!rule.date_from || rule.date_from <= today) &&
        (!rule.date_to || rule.date_to >= today) &&
        inHours(rule, now)
    );
}

/** Highest discount among the rules matching the product and quantity now (sequence breaks ties). */
export function bestRule(rules, product, qty, now = new Date()) {
    let best = null;
    for (const rule of rules || []) {
        if (
            qty >= (rule.min_qty || 0) &&
            ruleIsActive(rule, now) &&
            ruleMatchesProduct(rule, product) &&
            (!best || rule.discount > best.discount)
        ) {
            best = rule;
        }
    }
    return best;
}

patch(PosOrderline.prototype, {
    setDiscount(discount) {
        super.setDiscount(discount);
        if (!this._autoDiscountRunning && this.uiState) {
            // changed by hand: keep the cashier's value from now on
            this.uiState.autoDiscountManual = true;
            this.auto_discount_ref = 0;
        }
    },

    getDiscount() {
        return this._autoDiscountMergeAs !== undefined ? this._autoDiscountMergeAs : super.getDiscount();
    },

    /** A new line of the same product merges into an automatically discounted line (Odoo compares discounts). */
    canBeMergedWith(orderline) {
        if (this.auto_discount_ref && !this.uiState?.autoDiscountManual && !orderline.getDiscount()) {
            this._autoDiscountMergeAs = 0;
            try {
                return super.canBeMergedWith(orderline);
            } finally {
                delete this._autoDiscountMergeAs;
            }
        }
        return super.canBeMergedWith(orderline);
    },

    setQuantity(quantity, keep_price) {
        const result = super.setQuantity(...arguments);
        this.applyAutoDiscount();
        return result;
    },

    applyAutoDiscount(now = new Date()) {
        const order = this.order_id;
        const rules = this.config?._pos_auto_discounts;
        if (
            !rules?.length ||
            !order ||
            order.finalized ||
            this.uiState?.autoDiscountManual ||
            this.refunded_orderline_id ||
            this.combo_parent_id ||
            this.is_reward_line ||
            this.qty <= 0
        ) {
            return;
        }
        const rule = bestRule(rules, this.product_id, this.qty, now);
        if (!rule && !this.auto_discount_ref) {
            return; // never touch a line we did not discount
        }
        this._autoDiscountRunning = true;
        try {
            this.setDiscount(rule ? rule.discount : 0);
        } finally {
            this._autoDiscountRunning = false;
        }
        this.auto_discount_ref = rule ? rule.id : 0;
    },

    get autoDiscountRule() {
        return (this.config?._pos_auto_discounts || []).find((r) => r.id === this.auto_discount_ref);
    },
});

patch(PosStore.prototype, {
    async addLineToCurrentOrder(vals, opts = {}, configure = true) {
        const line = await super.addLineToCurrentOrder(...arguments);
        for (const orderLine of this.getOrder()?.lines || []) {
            orderLine.applyAutoDiscount();
        }
        return line;
    },

    /** Badge for product cards: best rule that needs no minimum quantity, or null. */
    autoDiscountBadge(product) {
        if (!this.config.auto_discount_badge) {
            return null;
        }
        const rules = (this.config._pos_auto_discounts || []).filter((r) => !(r.min_qty > 1));
        return bestRule(rules, product, 1);
    },
});
