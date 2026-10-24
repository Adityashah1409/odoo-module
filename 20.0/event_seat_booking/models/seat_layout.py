"""Seat grid computation shared by seating plans (templates) and ticket sections."""
import re

from odoo import api, fields, models
from odoo.exceptions import ValidationError


def row_label(index, style='alpha'):
    """1 -> A, 26 -> Z, 27 -> AA ... (or '1', '2' ... for numeric rows)."""
    if style == 'numeric':
        return str(index)
    label = ''
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        label = chr(65 + remainder) + label
    return label


def parse_numbers(text):
    numbers = set()
    for token in re.split(r'[,;\s]+', text or ''):
        if token.isdigit():
            numbers.add(int(token))
    return numbers


class SeatLayoutMixin(models.AbstractModel):
    _name = 'event.seat.layout.mixin'
    _description = 'Seat layout settings'

    seat_rows = fields.Integer('Rows', default=0)
    seat_columns = fields.Integer('Seats per row', default=0)
    seat_row_label = fields.Selection([('alpha', 'A, B, C...'), ('numeric', '1, 2, 3...')], string='Row names',
                                      default='alpha', required=True)
    seat_aisle_rows = fields.Char('Aisle after rows', help='Row numbers followed by an empty row, e.g. "5, 10".')
    seat_aisle_columns = fields.Char('Aisle after seats',
                                     help='Seat numbers followed by an aisle (empty column), e.g. "4, 12".')
    seat_blocked = fields.Char(
        'Blocked', help='Seats that are never sold: seat names ("A1, B7"), whole rows ("C") or seat numbers in every '
                        'row ("1, 16").')
    seat_stage_label = fields.Char('Stage label', default='Stage', help='Shown above the seat map (stage, screen...).')

    @api.constrains('seat_rows', 'seat_columns')
    def _check_seat_size(self):
        for record in self:
            if record.seat_rows < 0 or record.seat_columns < 0:
                raise ValidationError(self.env._('Rows and seats per row cannot be negative.'))
            if record.seat_rows * record.seat_columns > 5000:
                raise ValidationError(self.env._('A section is limited to 5,000 seats.'))

    def _seat_surcharge_lines(self):
        """Override: the surcharge lines of the record."""
        return self.env['event.seat.surcharge']

    def _blocked_rules(self):
        """Seat names ("A1" / "3-7"), rows ("C" / "R3") and seat numbers in every row ("12")."""
        names, rows, numbers = set(), set(), set()
        for token in re.split(r'[,;\s]+', (self.seat_blocked or '').upper()):
            if not token:
                continue
            if token.isdigit():
                numbers.add(int(token))
            elif token.startswith('R') and token[1:].isdigit():
                rows.add(row_label(int(token[1:]), self.seat_row_label))
            elif token.isalpha():
                rows.add(token)
            else:
                names.add(token)
        return names, rows, numbers

    def _seat_cells(self):
        """Seats of the grid: name, row, number, position (with aisles) and price surcharge."""
        self.ensure_one()
        aisle_rows = parse_numbers(self.seat_aisle_rows)
        aisle_columns = parse_numbers(self.seat_aisle_columns)
        names, rows, numbers = self._blocked_rules()
        surcharges = self._seat_surcharge_lines()
        cells = []
        display_row = 0
        for row in range(1, self.seat_rows + 1):
            label = row_label(row, self.seat_row_label)
            surcharge = surcharges._amount_for(label, row)
            display_col = 0
            for number in range(1, self.seat_columns + 1):
                name = f'{label}-{number}' if self.seat_row_label == 'numeric' else f'{label}{number}'
                cells.append({
                    'name': name, 'row_label': label, 'row_number': row, 'number': number,
                    'row_index': display_row, 'column_index': display_col, 'surcharge': surcharge,
                    'blocked': name.upper() in names or label.upper() in rows or number in numbers,
                })
                display_col += 1
                if number in aisle_columns and number != self.seat_columns:
                    display_col += 1
            display_row += 1
            if row in aisle_rows and row != self.seat_rows:
                display_row += 1
        return cells

    def _layout_map_data(self):
        """Grid of the layout itself (before seats exist), for previews: price = premium only."""
        self.ensure_one()
        cells = self._seat_cells() if self.seat_rows and self.seat_columns else []
        width = max([c['column_index'] for c in cells], default=-1) + 1
        rows = {}
        for cell in cells:
            rows.setdefault(cell['row_index'], {'label': cell['row_label'], 'cells': {}})
            rows[cell['row_index']]['cells'][cell['column_index']] = {
                'id': False, 'name': cell['name'], 'number': cell['number'], 'surcharge': cell['surcharge'],
                'status': 'blocked' if cell['blocked'] else 'available', 'price': cell['surcharge']}
        grid = []
        for index in range(max(rows, default=-1) + 1):
            row = rows.get(index)
            grid.append({'label': row['label'] if row else '', 'index': index, 'gap': not row,
                         'cells': [row['cells'].get(col) if row else None for col in range(width)]})
        return {'id': self.id, 'name': self.display_name, 'price': 0.0, 'stage': self.seat_stage_label or '',
                'width': width, 'rows': grid, 'premium': any(c['surcharge'] for c in cells)}

    def _copy_layout_values(self):
        self.ensure_one()
        return {
            'seat_rows': self.seat_rows, 'seat_columns': self.seat_columns, 'seat_row_label': self.seat_row_label,
            'seat_aisle_rows': self.seat_aisle_rows, 'seat_aisle_columns': self.seat_aisle_columns,
            'seat_blocked': self.seat_blocked, 'seat_stage_label': self.seat_stage_label,
        }


class EventSeatSurcharge(models.Model):
    _name = 'event.seat.surcharge'
    _description = 'Premium rows surcharge'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    plan_id = fields.Many2one('event.seat.plan', ondelete='cascade', index=True)
    ticket_id = fields.Many2one('event.event.ticket', ondelete='cascade', index=True)
    rows = fields.Char('Rows', required=True, help='Row names or numbers: "A", "A-C", "1-3, 7".')
    amount = fields.Float('Surcharge', required=True, digits='Product Price')

    def _matches(self, label, number):
        """``label`` is the row name, ``number`` the row number (1 = first row)."""
        self.ensure_one()
        for token in re.split(r'[,;\s]+', (self.rows or '').upper()):
            if not token:
                continue
            if '-' in token:
                start, _dash, end = token.partition('-')
                if start.isdigit() and end.isdigit() and int(start) <= number <= int(end):
                    return True
                if start.isalpha() and end.isalpha() and label.isalpha() and \
                        _alpha_index(start) <= _alpha_index(label) <= _alpha_index(end):
                    return True
            elif token.isdigit():
                if int(token) == number:
                    return True
            elif token == label.upper():
                return True
        return False

    def _amount_for(self, label, number):
        for line in self:
            if line._matches(label, number):
                return line.amount
        return 0.0


def _alpha_index(label):
    index = 0
    for char in label.upper():
        if not char.isalpha():
            return -1
        index = index * 26 + (ord(char) - 64)
    return index
