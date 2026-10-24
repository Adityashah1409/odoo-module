from . import models
from . import wizard


def _post_init_hook(env):
    """Defaults of the settings that are on out of the box."""
    ICP = env['ir.config_parameter'].sudo()
    if ICP.get_str('activity_management.reminder_days', None) is None:
        ICP.set_int('activity_management.reminder_days', 1)
    for key in ('activity_management.overdue_digest', 'activity_management.notify_supervisor'):
        if ICP.get_str(key, None) is None:
            ICP.set_bool(key, True)
