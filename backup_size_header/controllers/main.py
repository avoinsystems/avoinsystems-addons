import datetime
import logging
import tempfile

import odoo
import werkzeug
import werkzeug.exceptions
import werkzeug.utils
import werkzeug.wrappers
import werkzeug.wsgi
from odoo import http
from odoo.addons.web.controllers.main import Database
from odoo.http import content_disposition, dispatch_rpc

_logger = logging.getLogger(__name__)


class CustomDatabase(Database):

    @http.route('/web/database/backup', type='http', auth="none",
                methods=['POST'], csrf=False)
    def backup(self, master_pwd, name, backup_format='zip'):
        """
        Overridden method for passing content-length to the browser.
        """
        insecure = odoo.tools.config.verify_admin_password('admin')
        if insecure and master_pwd:
            dispatch_rpc('db', 'change_admin_password', ["admin", master_pwd])
        try:
            odoo.service.db.check_super(master_pwd)
            ts = datetime.datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
            filename = "%s_%s.%s" % (name, ts, backup_format)
            dump_stream = tempfile.TemporaryFile()
            odoo.service.db.dump_db(name, dump_stream, backup_format)
            headers = [
                ('Content-Type', 'application/octet-stream; charset=binary'),
                ('Content-Disposition', content_disposition(filename)),
                ('Content-Length', dump_stream.tell()),
            ]
            dump_stream.seek(0)
            response = werkzeug.wrappers.Response(dump_stream, headers=headers,
                                                  direct_passthrough=True)
            return response
        except Exception as e:
            _logger.exception('Database.backup')
            error = "Database backup error: %s" % (str(e) or repr(e))
            return self._render_template(error=error)
