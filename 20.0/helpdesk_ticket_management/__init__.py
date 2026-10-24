from . import controllers
from . import models
from . import wizard


def _post_init_hook(env):
    """Settings that are on out of the box."""
    ICP = env['ir.config_parameter'].sudo()
    if ICP.get_str('helpdesk_ticket_management.portal_create', None) is None:
        ICP.set_bool('helpdesk_ticket_management.portal_create', True)
    for key, xmlid in (('customer_reply_stage_id', 'stage_in_progress'), ('staff_reply_stage_id', 'stage_waiting')):
        if ICP.get_str(f'helpdesk_ticket_management.{key}', None) is None:
            ICP.set_int(f'helpdesk_ticket_management.{key}', env.ref(f'helpdesk_ticket_management.{xmlid}').id)
