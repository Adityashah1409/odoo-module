import json

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import BinaryBytes

from .quick_create import ICON_PATTERN, parse_context
from .theme_config import CONFIG_SCHEMA, is_acceptable_value

FILE_FORMAT = 'my_backend_theme.settings'
FILE_VERSION = 1
# A theme file is a few kilobytes; anything much larger is not one.
MAX_FILE_SIZE = 512 * 1024
MAX_ENTRIES = 200


class MyThemeSettingsTransfer(models.TransientModel):
    """Export the theme settings to a JSON file, or import such a file.

    The file holds the company-wide settings plus the Quick Create and Global
    Search entries, identified by model name so it can be moved between
    databases. User preferences, bookmarks and recently viewed records are
    personal and never exported.
    """

    _name = 'my.theme.settings.transfer'
    _description = 'Backend Theme Settings Import/Export'

    file = fields.Binary(string="Theme File", attachment=False)
    filename = fields.Char()
    state = fields.Selection([('upload', 'Upload'), ('done', 'Done')], default='upload', required=True)
    result_message = fields.Text(readonly=True)
    include_entries = fields.Boolean(
        string="Quick Create and Global Search Entries", default=True,
        help="Also add the file's Quick Create and Global Search entries. "
             "Entries already present are kept as they are.",
    )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @api.model
    def _export_data(self):
        QuickCreate = self.env['my.theme.quick.create'].with_context(active_test=False)
        SearchModel = self.env['my.theme.search.model'].with_context(active_test=False)
        return {
            'format': FILE_FORMAT,
            'version': FILE_VERSION,
            'settings': self.env['my.theme.config']._get_global_config(),
            'quick_create': [{
                'name': entry.name,
                'model': entry.model,
                'icon': entry.icon or 'add',
                'context': entry.context or '{}',
                'sequence': entry.sequence,
                'active': entry.active,
            } for entry in QuickCreate.search([])],
            'search_models': [{
                'model': entry.model,
                'sequence': entry.sequence,
                'active': entry.active,
            } for entry in SearchModel.search([])],
        }

    def action_export(self):
        self.ensure_one()
        content = json.dumps(self._export_data(), indent=2, sort_keys=True)
        self.write({
            'file': BinaryBytes(content.encode(), filename='backend_theme_settings.json'),
            'filename': 'backend_theme_settings.json',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{self._name}/{self.id}/file/{self.filename}?download=true',
            'target': 'download',
        }

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    @api.model
    def _parse_file(self, content):
        """:param bytes content: the file's content"""
        if len(content) > MAX_FILE_SIZE:
            raise UserError(self.env._("This file is too large to be a theme settings file."))
        try:
            data = json.loads(content)
        except ValueError:
            raise UserError(self.env._("This is not a theme settings file: it could not be read as JSON."))
        if not isinstance(data, dict) or data.get('format') != FILE_FORMAT:
            raise UserError(self.env._("This is not a theme settings file exported by Backend Theme."))
        if not isinstance(data.get('version'), int) or data['version'] > FILE_VERSION:
            raise UserError(self.env._("This file was exported by a newer version of Backend Theme."))
        return data

    @api.model
    def _import_data(self, data, include_entries=True):
        """Apply an exported file. Values are validated like the settings form
        does; anything invalid or unknown is skipped and reported.

        :returns: dict with the number of applied settings, added entries and
                  the names of skipped settings
        """
        settings = data.get('settings')
        settings = settings if isinstance(settings, dict) else {}
        accepted = {}
        skipped = []
        for key, value in settings.items():
            if key in CONFIG_SCHEMA and is_acceptable_value(key, value):
                accepted[key] = 'none' if CONFIG_SCHEMA[key][0] == 'hotkey' and not value else value
            else:
                skipped.append(str(key)[:64])
        Config = self.env['my.theme.config']
        Config._set_global_config(accepted)
        Config._sync_workspace_menu()

        added = 0
        if include_entries:
            added += self._import_quick_create(data.get('quick_create'), skipped)
            added += self._import_search_models(data.get('search_models'), skipped)
        return {'settings': len(accepted), 'entries': added, 'skipped': skipped}

    @api.model
    def _valid_entries(self, entries):
        if not isinstance(entries, list):
            return []
        return [
            entry for entry in entries[:MAX_ENTRIES]
            if isinstance(entry, dict) and isinstance(entry.get('model'), str)
        ]

    @api.model
    def _import_quick_create(self, entries, skipped):
        QuickCreate = self.env['my.theme.quick.create'].with_context(active_test=False)
        existing = {(entry.model, entry.name) for entry in QuickCreate.search([])}
        added = 0
        for entry in self._valid_entries(entries):
            model, name = entry['model'], entry.get('name')
            icon = entry.get('icon') or 'add'
            entry_context = entry.get('context') or '{}'
            try:
                valid = (
                    isinstance(name, str) and name.strip()
                    and isinstance(icon, str) and ICON_PATTERN.match(icon)
                    and isinstance(entry_context, str) and parse_context(entry_context) is not None
                )
            except (ValueError, SyntaxError, MemoryError, RecursionError):
                valid = False
            model_id = self.env['ir.model']._get_id(model) if valid and model in self.env else False
            if not model_id or self.env[model]._transient:
                skipped.append(self.env._("Quick Create: %s", str(name or model)[:64]))
                continue
            if (model, name) in existing:
                continue
            QuickCreate.create({
                'name': name.strip()[:128],
                'model_id': model_id,
                'icon': icon,
                'context': entry_context,
                'sequence': entry['sequence'] if isinstance(entry.get('sequence'), int) else 10,
                'active': entry.get('active') is not False,
            })
            existing.add((model, name))
            added += 1
        return added

    @api.model
    def _import_search_models(self, entries, skipped):
        SearchModel = self.env['my.theme.search.model'].with_context(active_test=False)
        existing = set(SearchModel.search([]).mapped('model'))
        added = 0
        for entry in self._valid_entries(entries):
            model = entry['model']
            if model in existing:
                continue
            if model not in self.env or self.env[model]._transient:
                skipped.append(self.env._("Global Search: %s", model[:64]))
                continue
            SearchModel.create({
                'model_id': self.env['ir.model']._get_id(model),
                'sequence': entry['sequence'] if isinstance(entry.get('sequence'), int) else 10,
                'active': entry.get('active') is not False,
            })
            existing.add(model)
            added += 1
        return added

    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError(self.env._("Choose a theme settings file to import."))
        result = self._import_data(self._parse_file(self.file.content), self.include_entries)
        message = self.env._(
            "%(settings)s settings and %(entries)s entries imported.",
            settings=result['settings'], entries=result['entries'],
        )
        if result['skipped']:
            message += '\n' + self.env._(
                "Skipped because they are invalid or unknown here: %s.",
                ', '.join(result['skipped'][:50]),
            )
        # The result stays in the dialog: the reload that applies the new
        # settings would drop a notification.
        self.write({'state': 'done', 'result_message': message, 'file': False})
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Import Theme Settings"),
            'res_model': self._name,
            'res_id': self.id,
            'views': [[False, 'form']],
            'target': 'new',
        }

    def action_reload(self):
        return {'type': 'ir.actions.client', 'tag': 'reload'}
