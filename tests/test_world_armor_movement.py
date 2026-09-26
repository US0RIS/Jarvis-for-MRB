from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from jarvis_mrb import world_armor_movement as movement


class MovementGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "world_armor_platform.sqlite3"
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        flags = patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_PLATFORM_ENABLED": "1",
            "JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED": "1",
            "AISSTREAM_API_KEY": "test-key",
        })
        flags.start()
        self.addCleanup(flags.stop)

    def enroll_air(self, **kwargs):
        data = dict(
            label="LA airspace", kind="opensky_region",
            grant_class="public_publisher",
            terms_reference="OpenSky terms reviewed by operator",
            authorized_automated_access=True,
            provider_min_interval_seconds=0,
            cadence_seconds=1,
            retention_days=7,
            latitude=34.05, longitude=-118.25, radius_km=80,
            db_path=self.db, now=self.now,
        )
        data.update(kwargs)
        return movement.enroll_source(**data)

    def aircraft_result(self, *, entity="icao24:abc123",
                        lat=34.05, lon=-118.25, observed=None):
        observed = observed or self.now.isoformat()
        return {
            "status": "ok", "checked_at": self.now.isoformat(),
            "source_observed_at": self.now.isoformat(),
            "source_note": "fixture public movement",
            "entities": [{
                "entity_type": "aircraft",
                "entity_id": entity,
                "provider_identifier": entity.split(":", 1)[1],
                "callsign": "TEST1", "name": None,
                "latitude": lat, "longitude": lon,
                "altitude_m": 3000.0, "on_ground": False,
                "velocity_mps": 200.0, "heading_deg": 90.0,
                "vertical_rate_mps": 0.0, "category": 4,
                "position_source": 0, "observed_at": observed,
                "provider_time": self.now.isoformat(),
                "source": "OpenSky Network",
            }],
        }

    def test_sources_have_no_global_count_ceiling(self):
        for i in range(43):
            self.enroll_air(
                label=f"Air {i}",
                authorized_automated_access=False,
                cadence_seconds=0,
            )
        first = movement.list_sources(db_path=self.db, page_size=20)
        second = movement.list_sources(
            db_path=self.db, offset=first["next_offset"], page_size=20,
        )
        third = movement.list_sources(
            db_path=self.db, offset=second["next_offset"], page_size=20,
        )
        self.assertEqual(first["total"], 43)
        self.assertIsNone(first["global_source_count_cap"])
        self.assertEqual([len(first["sources"]), len(second["sources"]),
                          len(third["sources"])], [20, 20, 3])

    def test_global_opensky_source_is_explicit_and_not_region_forged(self):
        source = movement.enroll_source(
            label="Global public airspace", kind="opensky_global",
            grant_class="api_contract",
            terms_reference="Operator-reviewed OpenSky provider grant",
            authorized_automated_access=False,
            provider_min_interval_seconds=0, cadence_seconds=0,
            retention_days=3, db_path=self.db, now=self.now,
        )
        self.assertTrue(source["global_scope"])
        self.assertIsNone(source["latitude"])
        with self.assertRaises(ValueError):
            movement.enroll_source(
                label="Bad", kind="opensky_global",
                grant_class="api_contract", terms_reference="terms",
                latitude=34, longitude=-118, radius_km=5,
                db_path=self.db, now=self.now,
            )

    def test_ais_requires_server_side_key(self):
        with patch.dict(os.environ, {"AISSTREAM_API_KEY": ""}):
            with self.assertRaises(ValueError):
                movement.enroll_source(
                    label="Port", kind="aisstream_region",
                    grant_class="api_contract", terms_reference="AISStream terms",
                    latitude=33.74, longitude=-118.25, radius_km=30,
                    db_path=self.db, now=self.now,
                )

    def test_collect_saves_public_transport_track_without_person_identity(self):
        source = self.enroll_air()
        with patch.object(
            movement, "_collect_provider",
            return_value=self.aircraft_result(),
        ):
            receipt = movement.collect_source(
                source["id"], db_path=self.db, now=self.now,
            )
        self.assertEqual(receipt["status"], "ok")
        self.assertEqual(receipt["observations_saved"], 1)
        near = movement.nearby(
            34.05, -118.25, radius_km=5,
            entity_type="aircraft", db_path=self.db,
        )
        self.assertEqual(len(near["entities"]), 1)
        self.assertFalse(near["absence_means_clear"])
        item = near["entities"][0]
        self.assertEqual(item["entity_id"], "icao24:abc123")
        self.assertTrue(item["person_identity_inference"] is False)
        history = movement.track("icao24:abc123", db_path=self.db)
        self.assertEqual(len(history["observations"]), 1)
        self.assertFalse(history["owner_or_passenger_inference"])

    def test_duplicate_same_provider_state_is_deduped(self):
        source = self.enroll_air()
        result = self.aircraft_result()
        with patch.object(movement, "_collect_provider",
                          return_value=result):
            one = movement.collect_source(
                source["id"], db_path=self.db, now=self.now,
            )
            two = movement.collect_source(
                source["id"], db_path=self.db, now=self.now,
            )
        self.assertEqual(one["observations_saved"], 1)
        self.assertEqual(two["observations_saved"], 0)
        history = movement.track("icao24:abc123", db_path=self.db)
        self.assertEqual(len(history["observations"]), 1)

    def test_distinct_state_builds_track_history(self):
        source = self.enroll_air()
        later = self.now + timedelta(seconds=20)
        with patch.object(
            movement, "_collect_provider",
            side_effect=[
                self.aircraft_result(),
                self.aircraft_result(
                    lat=34.07, lon=-118.20, observed=later.isoformat()
                ),
            ],
        ):
            movement.collect_source(source["id"], db_path=self.db, now=self.now)
            movement.collect_source(source["id"], db_path=self.db, now=later)
        history = movement.track("icao24:abc123", db_path=self.db)
        self.assertEqual(len(history["observations"]), 2)
        self.assertGreater(
            history["observations"][1]["longitude"],
            history["observations"][0]["longitude"],
        )

    def test_stop_during_network_blocks_inflight_save(self):
        source = self.enroll_air()
        def revoke(_source, worker_id="windows"):
            self.assertEqual(worker_id, "windows")
            movement.transition_source(
                source["id"], "stop", db_path=self.db,
            )
            return self.aircraft_result()
        with patch.object(movement, "_collect_provider",
                          side_effect=revoke):
            receipt = movement.collect_source(
                source["id"], db_path=self.db, now=self.now,
            )
        self.assertEqual(receipt["status"], "revoked_or_superseded")
        self.assertEqual(
            movement.track("icao24:abc123", db_path=self.db)["observations"],
            [],
        )

    def test_remote_mac_opensky_worker_normalizes_on_controller_and_records_worker(self):
        import time
        source = self.enroll_air()
        now_epoch = self.now.timestamp()
        provider_payload = {
            "time": now_epoch,
            "states": [[
                "abc123", "TEST1", None, now_epoch, now_epoch,
                -118.25, 34.05, 3000.0, False, 200.0, 90.0,
                0.0, None, None, False, False, 0, 4,
            ]],
        }
        with patch(
            "jarvis_mrb.reality_mesh.world_observe",
            return_value={
                "status": "ok", "provider": "opensky",
                "worker_observed_at": self.now.isoformat(),
                "provider_payload": provider_payload,
                "device_id": "macbook",
            },
        ) as worker:
            result = movement.collect_source(
                source["id"], db_path=self.db, now=self.now,
                worker_id="macbook",
            )
        self.assertEqual(result["worker_id"], "macbook")
        self.assertEqual(result["observations_saved"], 1)
        worker.assert_called_once()
        history = movement.track("icao24:abc123", db_path=self.db)
        self.assertEqual(history["observations"][0]["worker_id"], "macbook")

    def test_remote_worker_error_releases_lease_but_does_not_widen_source_authority(self):
        source = self.enroll_air()
        with patch(
            "jarvis_mrb.reality_mesh.world_observe",
            side_effect=RuntimeError("worker offline"),
        ):
            with self.assertRaises(RuntimeError):
                movement.collect_source(
                    source["id"], db_path=self.db, now=self.now,
                    worker_id="macbook",
                )
        current = movement.get_source(source["id"], db_path=self.db)
        self.assertEqual(current["check_count"], 1)
        self.assertEqual(current["last_outcome"], "worker_or_provider_error")
        # A failed Mac request does not grant permission to switch provider,
        # global scope, AIS, or arbitrary RPC.
        with self.assertRaises(ValueError):
            movement.collect_source(
                source["id"], db_path=self.db,
                now=self.now + timedelta(seconds=1),
                worker_id="unknown-node",
            )

    def test_remote_mac_is_not_allowed_for_global_opensky_or_ais(self):
        global_source = movement.enroll_source(
            label="Global", kind="opensky_global",
            grant_class="api_contract", terms_reference="terms",
            authorized_automated_access=False, cadence_seconds=0,
            db_path=self.db, now=self.now,
        )
        with self.assertRaises(ValueError):
            movement.collect_source(
                global_source["id"], db_path=self.db,
                now=self.now, worker_id="macbook",
            )
        ais = movement.enroll_source(
            label="Port", kind="aisstream_region",
            grant_class="api_contract", terms_reference="terms",
            authorized_automated_access=False, cadence_seconds=0,
            latitude=33.74, longitude=-118.25, radius_km=30,
            db_path=self.db, now=self.now,
        )
        with self.assertRaises(ValueError):
            movement.collect_source(
                ais["id"], db_path=self.db, now=self.now,
                worker_id="macmini",
            )

    def test_provider_floor_applies_to_manual_collection(self):
        source = self.enroll_air(
            provider_min_interval_seconds=60,
            cadence_seconds=120,
        )
        with patch.object(movement, "_collect_provider",
                          return_value=self.aircraft_result()):
            movement.collect_source(source["id"], db_path=self.db, now=self.now)
            with self.assertRaisesRegex(ValueError, "minimum interval"):
                movement.collect_source(
                    source["id"], db_path=self.db, now=self.now,
                )

    def test_due_runner_uses_only_authorized_scheduled_sources(self):
        scheduled = self.enroll_air()
        manual = self.enroll_air(
            label="Manual only",
            authorized_automated_access=False, cadence_seconds=0,
        )
        with patch.object(movement, "_collect_provider",
                          return_value=self.aircraft_result()):
            result = movement.run_due(
                db_path=self.db, limit=1, now=self.now,
            )
        self.assertEqual(len(result["checks"]), 1)
        self.assertEqual(result["checks"][0]["source_id"], scheduled["id"])
        self.assertEqual(
            movement.get_source(manual["id"], db_path=self.db)["check_count"],
            0,
        )

    def test_forget_works_when_collection_flag_off(self):
        source = self.enroll_air()
        with patch.object(movement, "_collect_provider",
                          return_value=self.aircraft_result()):
            movement.collect_source(source["id"], db_path=self.db, now=self.now)
        with patch.dict(os.environ, {
            "JARVIS_WORLD_ARMOR_MOVEMENT_ENABLED": "0",
        }):
            stopped = movement.transition_source(
                source["id"], "stop", db_path=self.db,
            )
            self.assertEqual(stopped["state"], "stopped")
            self.assertEqual(
                movement.forget_source(source["id"], db_path=self.db)["deleted"],
                1,
            )

    def test_source_terms_required_and_cadence_cannot_exceed_declared_rights(self):
        with self.assertRaises(ValueError):
            self.enroll_air(terms_reference="")
        with self.assertRaises(ValueError):
            self.enroll_air(
                authorized_automated_access=False, cadence_seconds=1,
            )
        with self.assertRaises(ValueError):
            self.enroll_air(
                provider_min_interval_seconds=30, cadence_seconds=10,
            )


if __name__ == "__main__":
    unittest.main()
