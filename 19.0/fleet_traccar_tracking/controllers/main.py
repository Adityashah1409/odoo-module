import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

STATE_COLORS = {'moving': '#16a34a', 'stopped': '#2563eb', 'offline': '#9ca3af'}

MAP_PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Fleet live map</title>
<link rel="stylesheet" href="/fleet_traccar_tracking/static/lib/leaflet/leaflet.css"/>
<style>
  html, body {{ margin: 0; height: 100%; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
  .layout {{ display: flex; height: 100%; }}
  aside {{ width: 340px; overflow-y: auto; border-right: 1px solid #e5e7eb; background: #fff; }}
  header {{ padding: 14px 16px; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center; }}
  header a {{ color: #714b67; text-decoration: none; font-size: 14px; }}
  h1 {{ font-size: 18px; margin: 0; }}
  .vehicle {{ padding: 12px 16px; border-bottom: 1px solid #f1f5f9; cursor: pointer; }}
  .vehicle:hover {{ background: #f8fafc; }}
  .name {{ font-weight: 600; }} .meta {{ color: #64748b; font-size: 13px; margin-top: 2px; }}
  .badge {{ display: inline-block; padding: 1px 8px; border-radius: 10px; color: #fff; font-size: 12px; float: right; }}
  #map {{ flex: 1; background: #e5e7eb; }}
  .empty {{ padding: 16px; color: #64748b; }}
</style></head>
<body><div class="layout">
<aside><header><h1>Fleet live map</h1><a href="/odoo">Back to Odoo</a></header><div id="list"></div></aside>
<div id="map"></div></div>
<script src="/fleet_traccar_tracking/static/lib/leaflet/leaflet.js"></script>
<script>
const COLORS = {colors};
const DATA_URL = {data_url};
const map = L.map('map').setView([20, 0], 2);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{maxZoom: 19, attribution: '&copy; OpenStreetMap contributors'}}).addTo(map);
const markers = {{}};
let fitted = false;
function esc(s) {{ const d = document.createElement('div'); d.textContent = s == null ? '' : s; return d.innerHTML; }}
function render(vehicles) {{
  const list = document.getElementById('list');
  list.innerHTML = vehicles.length ? '' : '<div class="empty">No vehicle has a GPS position yet.</div>';
  const bounds = [];
  vehicles.forEach(v => {{
    const color = COLORS[v.state] || '#9ca3af';
    const popup = `<b>${{esc(v.name)}}</b><br/>${{esc(v.driver || '')}}<br/>${{v.speed}} km/h · ${{esc(v.fix_time || '')}}<br/>${{esc(v.address || '')}}`;
    if (markers[v.id]) {{ markers[v.id].setLatLng([v.lat, v.lon]).setStyle({{fillColor: color}}).setPopupContent(popup); }}
    else {{ markers[v.id] = L.circleMarker([v.lat, v.lon], {{radius: 9, weight: 2, color: '#fff', fillColor: color, fillOpacity: 1}})
            .bindTooltip(esc(v.name), {{permanent: true, direction: 'right', offset: [10, 0]}}).bindPopup(popup).addTo(map); }}
    bounds.push([v.lat, v.lon]);
    const row = document.createElement('div');
    row.className = 'vehicle';
    row.innerHTML = `<span class="badge" style="background:${{color}}">${{esc(v.state_label)}}</span>
      <div class="name">${{esc(v.name)}}</div><div class="meta">${{esc(v.driver || 'No driver')}} · ${{v.speed}} km/h</div>
      <div class="meta">${{esc(v.address || (v.lat.toFixed(5) + ', ' + v.lon.toFixed(5)))}}</div>
      <div class="meta">Last position: ${{esc(v.fix_time || '-')}}</div>`;
    row.onclick = () => {{ map.setView([v.lat, v.lon], 15); markers[v.id].openPopup(); }};
    list.appendChild(row);
  }});
  if (!fitted && bounds.length) {{ map.fitBounds(bounds, {{padding: [60, 60], maxZoom: 14}}); fitted = true; }}
}}
render({initial});
setInterval(() => fetch(DATA_URL).then(r => r.json()).then(render).catch(() => {{}}), 30000);
</script></body></html>
"""


class TraccarController(http.Controller):

    def _vehicle_data(self, vehicle_ids=None):
        domain = ['|', ('gps_latitude', '!=', 0), ('gps_longitude', '!=', 0)]
        if vehicle_ids:
            domain.append(('id', 'in', vehicle_ids))
        vehicles = request.env['fleet.vehicle'].search(domain)
        states = dict(vehicles._fields['gps_motion_state']._description_selection(request.env))
        return [{
            'id': v.id, 'name': v.display_name, 'driver': v.driver_id.name or '',
            'lat': v.gps_latitude, 'lon': v.gps_longitude, 'speed': round(v.gps_speed or 0.0, 1),
            'state': v.gps_motion_state or 'offline', 'state_label': states.get(v.gps_motion_state or 'offline'),
            'address': v.gps_address or '',
            'fix_time': v.gps_fix_time and v.gps_fix_time.strftime('%Y-%m-%d %H:%M UTC') or '',
        } for v in vehicles]

    @staticmethod
    def _ids(vehicle_ids):
        return [int(i) for i in (vehicle_ids or '').split(',') if i.strip().isdigit()]

    @http.route('/fleet_traccar_tracking/map', type='http', auth='user')
    def live_map(self, vehicle_ids=None, **kwargs):
        """Live map of every vehicle the user can see (Leaflet + OpenStreetMap), refreshed every 30 s."""
        ids = self._ids(vehicle_ids)
        data_url = '/fleet_traccar_tracking/map/data' + (f'?vehicle_ids={",".join(map(str, ids))}' if ids else '')
        html = MAP_PAGE.format(colors=json.dumps(STATE_COLORS), data_url=json.dumps(data_url),
                               initial=json.dumps(self._vehicle_data(ids)).replace('</', '<\\/'))
        return request.make_response(html, headers=[('Content-Type', 'text/html; charset=utf-8')])

    @http.route('/fleet_traccar_tracking/map/data', type='http', auth='user')
    def live_map_data(self, vehicle_ids=None, **kwargs):
        return request.make_json_response(self._vehicle_data(self._ids(vehicle_ids)))

    @http.route('/fleet_traccar_tracking/webhook/<string:token>', type='http', auth='public',
                methods=['POST'], csrf=False)
    def webhook(self, token, **kwargs):
        """Traccar event / position forwarding (event.forward.url, forward.url with JSON)."""
        env = request.env(su=True)
        server = env['traccar.server'].search([('webhook_token', '=', token), ('active', '=', True)], limit=1)
        if not server or not token:
            return request.make_response('unknown token', status=403)
        try:
            payload = json.loads(request.httprequest.get_data() or b'{}')
        except ValueError:
            return request.make_response('invalid JSON', status=400)
        handled = env['traccar.device']._handle_webhook(server, payload)
        return request.make_response('ok' if handled else 'ignored', status=200)

