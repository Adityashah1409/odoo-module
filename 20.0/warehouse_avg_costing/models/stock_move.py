from collections import defaultdict

from odoo import models

from .stock_warehouse_cost import FLOW_KINDS, TRANSIT


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _wh_applicable(self):
        """Moves of products valued per warehouse (average cost, warehouse costing on)."""
        result = self.browse()
        Cost = self.env['stock.warehouse.cost']
        for company, moves in self.grouped('company_id').items():
            products = Cost._applicable_products(moves.product_id, company)
            result |= moves.filtered(lambda m: m.product_id in products)
        return result

    def _wh_bucket(self, location):
        """Warehouse bucket of a location: warehouse id, TRANSIT, or None when the stock is not valued."""
        company = self.company_id
        if not location or location.usage not in ('internal', 'transit') or location.company_id != company:
            return None
        return location.warehouse_id.id or TRANSIT

    def _wh_target(self):
        """Signed quantity per bucket that this move puts in (+) or takes out of (-) each warehouse."""
        self.ensure_one()
        target = defaultdict(float)
        partner = self.company_id.partner_id
        for line in self.move_line_ids:
            if line.owner_id and line.owner_id != partner:
                continue  # consigned stock is not valued
            qty = line.quantity_product_uom
            if not qty:
                continue
            src, dst = self._wh_bucket(line.location_id), self._wh_bucket(line.location_dest_id)
            if src == dst:
                continue
            if src is not None:
                target[src] -= qty
            if dst is not None:
                target[dst] += qty
        return target

    def _wh_booked(self):
        lines = self.env['stock.warehouse.cost.line'].sudo().search([('move_id', '=', self.id),
                                                                     ('kind', 'in', FLOW_KINDS)])
        booked = defaultdict(float)
        for line in lines:
            booked[line._bucket()] += line.quantity
        return booked, lines

    def _wh_in_unit_cost(self, qty):
        """Unit cost of goods entering the valued stock from outside (supplier, production, return...)."""
        self.ensure_one()
        product = self.product_id.with_company(self.company_id)
        if self.is_in or self._is_in():
            valued_qty = self._get_valued_qty()
            if valued_qty and self.value:
                return self.value / valued_qty
        origin_lines = self.env['stock.warehouse.cost.line'].sudo().search([
            ('move_id', 'in', self.move_orig_ids.ids), ('kind', 'in', ('out', 'transfer_out'))])
        origin_qty = -sum(origin_lines.mapped('quantity'))
        if origin_qty:
            return -sum(origin_lines.mapped('value')) / origin_qty
        return product.standard_price

    def _wh_sync(self):
        """Book in the ledger whatever this move changed in each warehouse and is not booked yet.

        Idempotent: called during validation, value updates and quantity corrections.
        """
        Cost = self.env['stock.warehouse.cost'].sudo()
        touched = self.env['product.product']
        for move in self._wh_applicable():
            company = move.company_id
            target = move._wh_target()
            booked, _lines = move._wh_booked()
            deltas = {bucket: target.get(bucket, 0.0) - booked.get(bucket, 0.0) for bucket in set(target) | set(booked)}
            uom = move.product_id.uom_id
            deltas = {bucket: qty for bucket, qty in deltas.items() if not uom.is_zero(qty)}
            if not deltas:
                continue
            transfer = any(q < 0 for q in deltas.values()) and any(q > 0 for q in deltas.values())
            out_qty = out_value = 0.0
            for bucket, qty in sorted(deltas.items(), key=lambda item: item[1]):
                row = Cost._get_row(move.product_id, bucket, company)
                if qty < 0:
                    line = row._book(qty, kind='transfer_out' if transfer else 'out', move=move)
                    out_qty -= qty
                    out_value -= line.value
                else:
                    unit = out_value / out_qty if transfer and out_qty else move._wh_in_unit_cost(qty)
                    row._book(qty, unit, kind='transfer_in' if transfer else 'in', move=move)
            touched |= move.product_id
        return touched

    def _wh_out_value(self):
        """Value of the goods this move took out of the warehouses (positive)."""
        self.ensure_one()
        lines = self.env['stock.warehouse.cost.line'].sudo().search([('move_id', '=', self.id),
                                                                     ('kind', '=', 'out')])
        return -sum(lines.mapped('value'))

    def _wh_book_value_delta(self):
        """An incoming move got a new value (landed cost, vendor bill, manual valuation): move the difference
        into the warehouse that received the goods."""
        Line = self.env['stock.warehouse.cost.line'].sudo()
        touched = self.env['product.product']
        for move in self._wh_applicable().filtered(lambda m: m.state == 'done' and m.is_in):
            lines = Line.search([('move_id', '=', move.id), ('kind', 'in', ('in', 'correction'))])
            in_lines = lines.filtered(lambda l: l.kind == 'in')
            if not in_lines:
                continue
            booked_qty = sum(in_lines.mapped('quantity'))
            valued_qty = move._get_valued_qty()
            expected = move.value * (booked_qty / valued_qty) if valued_qty else 0.0
            delta = move.company_id.currency_id.round(expected - sum(lines.mapped('value')))
            if move.company_id.currency_id.is_zero(delta):
                continue
            row = max(in_lines, key=lambda l: l.quantity).cost_id
            row._book(0.0, kind='correction', move=move, value_delta=delta,
                      note=self.env._('New value of %s', move.reference or move.display_name))
            touched |= move.product_id
        return touched

    # ------------------------------------------------------------------ hooks
    def _set_value(self, *args, **kwargs):
        result = super()._set_value(*args, **kwargs)
        moves = self._wh_applicable()
        if not moves:
            return result
        touched = self.env['product.product']
        for move in moves:
            if move.is_out or (move.state != 'done' and move._is_out()):
                touched |= move._wh_sync()
                value = move._wh_out_value()
                if move.company_id.currency_id.compare_amounts(move.value, value) != 0:
                    move.value = value
            elif move.state == 'done' and move.is_in:
                touched |= move._wh_sync()
                touched |= move._wh_book_value_delta()
        touched._wh_sync_standard_price()
        return result

    def _action_done(self, cancel_backorder=False):
        moves = super()._action_done(cancel_backorder=cancel_backorder)
        done = moves.filtered(lambda m: m.state == 'done')
        done._wh_sync()._wh_sync_standard_price()
        return moves
