from . import models
from . import wizard


def _post_init_hook(env):
    """Defaults that must be switchable off: an unchecked boolean setting removes its parameter."""
    ICP = env['ir.config_parameter'].sudo()
    for key, value in (('activity_management.reminder_days', '1'),
                       ('activity_management.overdue_digest', 'True'),
                       ('activity_management.notify_supervisor', 'True')):
        if ICP.get_param(key) is False:
            ICP.set_param(key, value)
