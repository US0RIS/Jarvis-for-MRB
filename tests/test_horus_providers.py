from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from jarvis_mrb.horus import providers as pv

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)

NDBC = """#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE
#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   hPa  degC  degC  degC  nmi  hPa    ft
2026 10 01 11 50 270  6.0  8.0   1.4    12   7.5 280 1015.2  17.1  18.3  12.0   MM   MM    MM
2026 10 01 11 40 270  5.0  MM    MM     MM   MM  MM  1015.3  17.0  18.2  12.0   MM   MM    MM
"""


class ProviderTests(unittest.TestCase):
    def test_dot_cameras_allowlist_and_wildfire_framing(self) -> None:
        cams = pv.normalize_dot_cameras([
            {"CameraID": 1, "Title": "I-5 @ Seattle", "ImageURL": "https://images.wsdot.wa.gov/nw/005vc.jpg",
             "CameraLocation": {"Latitude": 47.6, "Longitude": -122.3}},
            {"CameraID": 2, "Title": "evil", "ImageURL": "https://evil.example/x.jpg", "CameraLocation": {"Latitude": 1, "Longitude": 1}},
        ], source="wsdot", allowed_hosts=["wsdot.wa.gov"])
        self.assertEqual([c["id"] for c in cams], ["wsdot:1"])
        obs = pv.wildfire_camera_observation(cams[0], 0.8, T0)
        self.assertIn("not a confirmed incident", obs.framing)
        self.assertTrue(pv.is_webcam_stream("Morro Bay Harbor Live Cam"))
        self.assertFalse(pv.is_webcam_stream("lofi beats live 24/7 radio"))

    def test_gateway_and_eventification(self) -> None:
        cam = pv.CameraSource("c1", "noaa", "https://x.gov/cam", "https://x.gov/cam.m3u8", "hls", (34, -119), True)
        plan = pv.gateway_plan(cam)
        self.assertTrue(plan["consumer_url"].endswith("stream.m3u8?src=c1"))
        self.assertEqual(plan["source_of_truth"]["stream"], "https://x.gov/cam.m3u8")
        self.assertFalse(pv.gateway_plan(pv.CameraSource("c2", "?", "", "", "rtsp", (0, 0), False))["ok"])
        ev = pv.zone_crossings({"t1": [(T0, (5, 5)), (T0 + timedelta(seconds=1), (1, 1)), (T0 + timedelta(seconds=2), (5, 5))]},
                               [(0, 0), (2, 0), (2, 2), (0, 2)], camera="driveway")
        self.assertEqual([e["event"] for e in ev], ["entered_zone", "left_zone"])

    def test_ndbc_aqi_gtfs_notam(self) -> None:
        obs = pv.parse_ndbc(NDBC, "46053")
        self.assertEqual(obs[0].values["wave_height_m"], 1.4)
        self.assertIsNone(obs[1].values["wave_height_m"])
        self.assertEqual(pv.pm25_to_aqi(9.0), 50)
        self.assertEqual(pv.pm25_to_aqi(35.4), 100)
        self.assertEqual(pv.pm25_to_aqi(12.0), 56)
        an = pv.parse_airnow([{"DateObserved": "2026-10-01 ", "HourObserved": 11, "ParameterName": "PM2.5", "AQI": 42,
                               "Category": {"Name": "Good"}, "ReportingArea": "Ventura"}])
        self.assertEqual(an[0].values["category"], "Good")
        self.assertEqual(pv.parse_purpleair({"sensor_index": 7, "pm2.5_atm": 40.0}, at=T0).values["aqi"], 112)
        feed = {"entity": [{"trip_update": {"trip": {"route_id": "LOSSAN", "trip_id": "t1"},
                                            "stop_time_update": [{"stop_id": "VEN", "arrival": {"delay": 720}}]}}]}
        self.assertIn("12 minutes late", pv.gtfs_delays(feed, stop_id="VEN")[0]["message"])
        n = pv.parse_notam("!LAX 10/123 LAX RWY 07L/25R CLSD 2610011200-2610012000")
        self.assertEqual((n["kind"], n["effective"][:16]), ("runway", "2026-10-01T12:00"))
        self.assertIsNone(pv.parse_notam("garbage"))

    def test_local_rf_and_sensors(self) -> None:
        ac = pv.parse_readsb({"now": T0.timestamp(), "aircraft": [
            {"hex": "a1b2c3", "flight": "SWA123 ", "lat": 34.05, "lon": -119.0, "alt_baro": 3000, "baro_rate": -800, "seen": 1},
            {"hex": "nopos"}]}, receiver="pi5", home=(34.0, -119.0))
        self.assertEqual(len(ac), 1)
        self.assertEqual(ac[0].tier, pv.LOCAL)
        self.assertEqual(ac[0].values["trend"], "descending")
        self.assertLess(ac[0].values["distance_mi"], 4)
        ais = pv.parse_ais_catcher([{"mmsi": 367000000, "lat": 34.1, "lon": -119.2, "speed": 10}], receiver="pi5", at=T0)
        self.assertEqual(ais[0].subject, "367000000")
        lines = [json.dumps({"time": "2026-10-01 12:00:00", "model": "Acurite-Tower", "id": 1, "temperature_C": 21.5}),
                 json.dumps({"time": "2026-10-01 12:00:00", "model": "Neighbor-TPMS", "id": 9, "pressure_kPa": 220}),
                 "not json"]
        rf = pv.parse_rtl433(lines, enrolled={"Acurite-Tower:1": "garage temp"})
        self.assertEqual([o.subject for o in rf], ["garage temp"])
        es = pv.parse_esphome_state("esphome/office/binary_sensor/mmwave/state", "ON", at=T0)
        self.assertEqual(es.values["value"], "ON")
        self.assertIsNone(pv.parse_esphome_state("other/x", "1", at=T0))
        csi = pv.csi_presence([4.0, 5.0], baseline=1.0)
        self.assertTrue(csi["motion"])
        self.assertIn("pose", csi["unsupported"])
        rp = pv.room_presence({"mmwave": True, "door": False, "csi": None})
        self.assertTrue(rp["occupied"])
        self.assertIsNone(pv.room_presence({})["occupied"])

    def test_authenticated_node(self) -> None:
        secrets = {"bench1": b"k"}
        rep = {"node": "bench1", "at": T0.isoformat(), "nonce": "n1", "kind": "door", "values": {"open": True}}
        sig = pv.sign_sensor_report(b"k", rep)
        nonces: set[str] = set()
        self.assertIsNotNone(pv.verify_sensor_report(secrets, rep, sig, now=T0, seen_nonces=nonces))
        self.assertIsNone(pv.verify_sensor_report(secrets, rep, sig, now=T0, seen_nonces=nonces))  # replay
        self.assertIsNone(pv.verify_sensor_report(secrets, rep, "00" * 32, now=T0))
        self.assertIsNone(pv.verify_sensor_report(secrets, rep, sig, now=T0 + timedelta(hours=1)))

    def test_home_assistant_bus(self) -> None:
        ha = pv.HomeAssistantBus()
        caps = ha.discover([{"entity_id": "light.porch", "state": "off", "attributes": {"friendly_name": "Porch"}},
                            {"entity_id": "lock.front", "state": "locked"}])
        self.assertEqual([c["entity_id"] for c in caps], ["light.porch"])
        with self.assertRaises(PermissionError):
            ha.grant("lock.front", "unlock", now=T0)
        g = ha.grant("light.porch", "turn_on", now=T0)
        d = ha.dispatch(g, now=T0)
        self.assertEqual(d["status"], "dispatched_unverified")
        self.assertEqual(d["request"]["path"], "/api/services/light/turn_on")
        self.assertEqual(ha.dispatch(g, now=T0)["status"], "rejected")
        self.assertEqual(ha.verify("turn_on", "on")["status"], "verified")

    def test_lora(self) -> None:
        msg = pv.lora_compact({"priority": "critical", "at": T0, "code": "FLOOD", "text": "Flash flood emergency. " * 20})
        self.assertLessEqual(len(msg), 200)
        self.assertEqual(pv.lora_expand(msg)["priority"], "critical")


if __name__ == "__main__":
    unittest.main()
