from . import controllers, models, wizard


def _post_init_hook(env):
    ICP = env['ir.config_parameter'].sudo()
    if not ICP.search_count([('key', '=', 'access_management.export_log_days')]):
        ICP.set_int('access_management.export_log_days', 90)
