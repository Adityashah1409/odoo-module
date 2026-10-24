from . import controllers
from . import models
from . import wizard


def _post_init_hook(env):
    """Settings that are on out of the box (an unchecked boolean setting removes its parameter)."""
    ICP = env['ir.config_parameter'].sudo()
    defaults = {
        'helpdesk_ticket_management.portal_create': 'True',
        'helpdesk_ticket_management.customer_reply_stage_id': str(env.ref('helpdesk_ticket_management.stage_in_progress').id),
        'helpdesk_ticket_management.staff_reply_stage_id': str(env.ref('helpdesk_ticket_management.stage_waiting').id),
    }
    for key, value in defaults.items():
        if ICP.get_param(key) is False:
            ICP.set_param(key, value)
