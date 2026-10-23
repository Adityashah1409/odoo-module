"""Fixes that Odoo 20's upgrade_code does not (yet) cover, applied after it.

usage: python post_port_20.py <path/to/20.0/module>
"""
import pathlib
import re
import sys

module = pathlib.Path(sys.argv[1])

# 1. keep ir.access.csv right after security.xml in the manifest
manifest = module / '__manifest__.py'
text = manifest.read_text()
if "'security/ir.access.csv'" in text:
    text = re.sub(r"\n\s*'security/ir\.access\.csv',", '', text)
    if "'security/security.xml'," in text:
        text = text.replace("'security/security.xml',", "'security/security.xml',\n        'security/ir.access.csv',", 1)
    else:
        text = text.replace("'data': [", "'data': [\n        'security/ir.access.csv',", 1)
    manifest.write_text(text)

for path in module.rglob('*'):
    if path.suffix == '.xml':
        text = path.read_text()
        original = text
        # 2. upgrade_code drops the XML declaration and mis-indents the root end tag
        if not text.lstrip().startswith('<?xml') and text.lstrip().startswith('<odoo'):
            text = '<?xml version="1.0" encoding="utf-8"?>\n' + text.lstrip()
        text = re.sub(r'\n[ \t]+</odoo>\s*$', '\n</odoo>\n', text)
        # 3. ir.attachment.datas no longer exists in 20: views use `raw`
        if 'views' in path.parts:
            text = text.replace('<field name="datas"', '<field name="raw"')
        if text != original:
            path.write_text(text)
    elif path.suffix == '.py':
        text = path.read_text()
        original = text
        # 4. odoo.http became a package; content_disposition moved to odoo.http.stream
        match = re.search(r'^from odoo\.http import (.+)$', text, re.MULTILINE)
        if match and 'content_disposition' in match.group(1):
            names = [n.strip() for n in match.group(1).split(',') if n.strip() != 'content_disposition']
            replacement = (f"from odoo.http import {', '.join(names)}\n" if names else '') + \
                'from odoo.http.stream import content_disposition'
            text = text.replace(match.group(0), replacement)
        if text != original:
            path.write_text(text)

print(f"post-port fixes applied to {module}")

# 5. ir.config_parameter: get_param/set_param became typed getters/setters in 20
for path in module.rglob('*.py'):
    text = path.read_text()
    new = text.replace('.get_param(', '.get_str(').replace('.set_param(', '.set_str(')
    if new != text:
        path.write_text(new)
