from . import controllers, models, wizard


def _post_init_hook(env):
    ICP = env['ir.config_parameter'].sudo()
    if ICP.get_param('access_management.export_log_days') is False:
        ICP.set_param('access_management.export_log_days', '90')
