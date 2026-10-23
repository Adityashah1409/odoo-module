import json
from datetime import datetime
from unittest.mock import patch

from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from odoo.exceptions import AccessError

REQUEST = 'odoo.addons.fleet_traccar_tracking.models.traccar_server.TraccarServer._request'

DEVICES = [
    {'id': 1, 'name': 'Van 1', 'uniqueId': '1-ABC-123', 'status': 'online', 'lastUpdate': '2026-10-23T09:59:00.000+00:00',
     'phone': '+32 470 00 00 01', 'model': 'Traccar Client', 'category': 'van', 'disabled': False},
    {'id': 2, 'name': 'Truck 7', 'uniqueId': '358240051111110', 'status': 'offline', 'lastUpdate': None},
]
POSITIONS = [
    {'id': 501, 'deviceId': 1, 'fixTime': '2026-10-23T10:00:00.000+02:00', 'latitude': 50.8466, 'longitude': 4.3528,
     'speed': 27.0, 'course': 90, 'altitude': 60, 'accuracy': 8.5, 'address': 'Grand-Place, Brussels',
     'attributes': {'motion': True, 'batteryLevel': 76, 'totalDistance': 152345.0}},
    {'id': 601, 'deviceId': 2, 'fixTime': '2026-10-23T07:00:00Z', 'latitude': 51.2194, 'longitude': 4.4025,
     'speed': 0.0, 'attributes': {'motion': False}},
]
TRIPS = [
    {'deviceId': 1, 'startTime': '2026-10-22T08:00:00.000+00:00', 'endTime': '2026-10-22T09:30:00.000+00:00',
     'startAddress': 'Depot, Brussels', 'endAddress': 'Client, Antwerp', 'startLat': 50.85, 'startLon': 4.35,
     'endLat': 51.22, 'endLon': 4.40, 'distance': 45230.0, 'averageSpeed': 19.4, 'maxSpeed': 54.0, 'driverName': 'Sam'},
]


def fake_request(server, path, params=None, method='GET'):
    return {
        'server': {'version': '6.10', 'registration': True},
        'devices': DEVICES,
        'positions': POSITIONS,
        'reports/trips': TRIPS,
    }[path]


class TraccarCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        brand = cls.env['fleet.vehicle.model.brand'].create({'name': 'Renault'})
        model = cls.env['fleet.vehicle.model'].create({'name': 'Master', 'brand_id': brand.id})
        cls.van = cls.env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': '1-ABC-123'})
        cls.truck = cls.env['fleet.vehicle'].create({'model_id': model.id, 'license_plate': 'TRUCK-7'})
        cls.server = cls.env['traccar.server'].create({
            'name': 'Test Traccar', 'url': 'https://gps.example.com', 'username': 'admin', 'password': 'secret'})

    def setUp(self):
        super().setUp()
        patcher = patch(REQUEST, autospec=True, side_effect=fake_request)
        self.mock = patcher.start()
        self.addCleanup(patcher.stop)

    def connect(self):
        self.server.action_test_connection()
        self.server.action_import_devices()
        return self.server.device_ids


@tagged('post_install', '-at_install')
class TestTraccar(TraccarCase):

    def test_connect_and_import_devices(self):
        devices = self.connect()
        self.assertEqual(self.server.state, 'connected')
        self.assertEqual(self.server.server_version, '6.10')
        self.assertEqual(len(devices), 2)
        van_device = devices.filtered(lambda d: d.traccar_id == 1)
        self.assertEqual(van_device.vehicle_id, self.van, "linked by license plate = identifier")
        self.assertEqual(self.van.traccar_device_id, van_device)
        self.assertFalse(devices.filtered(lambda d: d.traccar_id == 2).vehicle_id)
        self.server.action_import_devices()
        self.assertEqual(len(self.server.device_ids), 2, "no duplicates")

    def test_refresh_positions_updates_vehicle(self):
        devices = self.connect()
        devices.filtered(lambda d: d.traccar_id == 2).vehicle_id = self.truck
        self.server.action_refresh_positions()
        self.assertAlmostEqual(self.van.gps_latitude, 50.8466)
        self.assertAlmostEqual(self.van.gps_speed, 27.0 * 1.852, places=1)
        self.assertEqual(self.van.gps_motion_state, 'moving')
        self.assertEqual(self.van.gps_fix_time, datetime(2026, 10, 23, 8, 0, 0), "converted to UTC")
        self.assertEqual(self.van.gps_battery_level, 76)
        self.assertEqual(self.van.gps_address, 'Grand-Place, Brussels')
        self.assertIn('openstreetmap.org/export/embed.html', self.van.gps_map_html)
        self.assertEqual(self.truck.gps_motion_state, 'offline', "device offline wins over last motion")
        self.assertEqual(self.van.odometer, 152.3)
        # same positions again: no duplicate history
        self.server.action_refresh_positions()
        self.assertEqual(self.env['traccar.position'].search_count([('vehicle_id', '=', self.van.id)]), 1)

    def test_disabled_tracking_is_ignored(self):
        devices = self.connect()
        devices.filtered(lambda d: d.traccar_id == 1).tracking_enabled = False
        self.server.action_refresh_positions()
        self.assertFalse(self.van.gps_fix_time)

    def test_import_trips(self):
        self.connect()
        wizard = self.env['traccar.trip.import.wizard'].create({
            'date_from': datetime(2026, 10, 22), 'date_to': datetime(2026, 10, 23), 'vehicle_ids': [(6, 0, self.van.ids)]})
        wizard.action_import()
        trip = self.env['traccar.trip'].search([('vehicle_id', '=', self.van.id)])
        self.assertEqual(len(trip), 1)
        self.assertAlmostEqual(trip.distance_km, 45.23)
        self.assertAlmostEqual(trip.duration, 1.5)
        self.assertAlmostEqual(trip.max_speed, 54.0 * 1.852, places=1)
        self.assertEqual(self.van.trip_count, 1)
        params = self.mock.call_args.kwargs['params']
        self.assertEqual(params['from'], '2026-10-22T00:00:00Z')
        wizard.action_import()
        self.assertEqual(self.env['traccar.trip'].search_count([('vehicle_id', '=', self.van.id)]), 1, "no duplicates")

    def test_connection_error(self):
        from ..models.traccar_server import TraccarError
        self.mock.side_effect = TraccarError("refused")
        action = self.server.action_test_connection()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(self.server.state, 'error')
        self.assertEqual(self.server.last_error, 'refused')

    def test_access_rights(self):
        user = new_test_user(self.env, 'fleet_officer', groups='fleet.fleet_group_user')
        self.connect()
        self.assertEqual(len(self.env['traccar.device'].with_user(user).search([])), 2)
        with self.assertRaises(AccessError):
            self.server.with_user(user).read(['password'])
        with self.assertRaises(AccessError):
            self.env['traccar.server'].with_user(user).create({'name': 'x', 'url': 'https://x'})


@tagged('post_install', '-at_install')
class TestTraccarHttp(HttpCase, TraccarCase):

    def test_webhook_event_forwarding(self):
        self.connect()
        url = f'/fleet_traccar_tracking/webhook/{self.server.webhook_token}'
        self.assertEqual(self.url_open('/fleet_traccar_tracking/webhook/wrong', data=b'{}').status_code, 403)
        payload = {
            'event': {'type': 'alarm', 'deviceId': 1, 'attributes': {'alarm': 'overspeed'}},
            'position': dict(POSITIONS[0], id=777, latitude=50.9),
            'device': {'id': 1, 'name': 'Van 1', 'status': 'online'},
        }
        response = self.url_open(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 200)
        self.assertAlmostEqual(self.van.gps_latitude, 50.9)
        self.assertTrue(any('overspeed' in m.body for m in self.van.message_ids))

    def test_live_map(self):
        self.connect()
        self.server.action_refresh_positions()
        self.authenticate('admin', 'admin')
        response = self.url_open('/fleet_traccar_tracking/map')
        self.assertEqual(response.status_code, 200)
        self.assertIn('leaflet.js', response.text)
        self.assertIn('1-ABC-123', response.text)
        data = self.url_open(f'/fleet_traccar_tracking/map/data?vehicle_ids={self.van.id}').json()
        self.assertEqual([(d['id'], d['state']) for d in data], [(self.van.id, 'moving')])
