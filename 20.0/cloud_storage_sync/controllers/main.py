import io
import zipfile

from odoo import http
from odoo.http import request
from odoo.http.stream import content_disposition

from ..models.providers import StorageError


class CloudStorageController(http.Controller):

    @http.route('/cloud_storage_sync/folder/<int:folder_id>/zip', type='http', auth='user')
    def folder_zip(self, folder_id, **kwargs):
        """Download a folder (and its subfolders) as a ZIP, with the user's access rights."""
        folder = request.env['cloud.storage.folder'].browse(folder_id).exists()
        if not folder:
            raise request.not_found()
        folder.check_access('read')
        folders = request.env['cloud.storage.folder'].search([('id', 'child_of', folder.id)])
        attachments = request.env['ir.attachment'].search([('cloud_folder_id', 'in', folders.ids)])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for attachment in attachments:
                relative = attachment.cloud_folder_id.remote_path[len(folder.parent_id.remote_path or ''):].strip('/')
                name = f"{relative}/{attachment._cloud_file_name()}"
                data = bytes(attachment.raw or b'')
                if attachment.type == 'url' and attachment.cloud_path:
                    client = attachment.sudo().cloud_folder_id.client_id
                    try:
                        data = client._provider().download(client._full_path(attachment.cloud_path))
                    except StorageError:
                        data = (attachment.url or '').encode()
                        name += '.url.txt'
                archive.writestr(name, data or b'')
        payload = buffer.getvalue()
        return request.make_response(payload, headers=[
            ('Content-Type', 'application/zip'),
            ('Content-Length', len(payload)),
            ('Content-Disposition', content_disposition(f"{folder.sanitized_name}.zip")),
        ])
