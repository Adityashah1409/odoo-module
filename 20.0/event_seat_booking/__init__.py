from . import controllers
from . import models
from . import wizard


def _post_init_hook(env):
    """Settings on by default (an unchecked boolean setting removes its parameter in Odoo 19)."""
    ICP = env['ir.config_parameter'].sudo()
    ICP.set_bool('event_seat_booking.auto_allocate', True)
