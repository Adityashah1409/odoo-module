import { patch } from "@web/core/utils/patch";
import { usePos } from "@point_of_sale/app/hooks/pos_hook";
import { ProductCard } from "@point_of_sale/app/components/product_card/product_card";

patch(ProductCard.prototype, {
    setup() {
        super.setup(...arguments);
        this.pos = usePos();
    },

    get autoDiscountBadge() {
        const rule = this.pos?.autoDiscountBadge?.(this.props.product);
        return rule ? `-${Number(rule.discount.toFixed(2))}%` : "";
    },
});
