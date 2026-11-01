from . import controllers, models


def _post_init_split_names(env):
    """Fill the name parts of the existing people from their current name."""
    env['res.partner']._partner_names_fill_missing()
