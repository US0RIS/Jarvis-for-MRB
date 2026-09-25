from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from jarvis_mrb import world_armor_hypotheses as hypotheses
from jarvis_mrb import world_armor_phase1 as armor

NOW=datetime(2026,9,24,20,0,tzinfo=timezone.utc)


def conditions(at=NOW, *, aqi=45.0, nws="ok"):
    return {
        "checked_at":at.isoformat(),
        "air_quality":{
            "status":"ok","us_aqi":aqi,
            "model_time_utc":at.isoformat(),
        },
        "weather_alerts":{
            "status":nws,
            "alerts":[{
                "id":"nws-one","event":"Wind Advisory",
                "headline":"Official source report",
                "severity":"Moderate",
            }] if nws=="ok" else [],
        },
    }


def earthquakes(at=NOW-timedelta(minutes=12), *, located=True, status="ok"):
    event={
        "id":"us-one","magnitude":3.2,"place":"reported near query center",
        "occurred_at":at.isoformat(),"reviewed":False,
        "source_url":"https://earthquake.usgs.gov/",
    }
    if located:
        event.update({"latitude":34.121,"longitude":-118.161})
    return {
        "status":status,"checked_at":NOW.isoformat(),
        "events":[event] if status=="ok" else [],
    }


class WorldArmorHypothesisTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db=Path(temp.name)/"armor.sqlite3"
        self.env=patch.dict(os.environ,{"JARVIS_WORLD_ARMOR_ENABLED":"1"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.key=armor.create_investigation(
            "Infrastructure corridor",34.12,-118.16,
            radius_km=30,db_path=self.db,now=NOW,
        )["id"]

    def collect(self, *, at=NOW, air=None, quake=None):
        return armor.ingest_fixture(
            self.key,
            air if air is not None else conditions(at),
            quake if quake is not None else earthquakes(at-timedelta(minutes=12)),
            db_path=self.db,now=at,
        )

    def graph(self, **kwargs):
        args=dict(
            investigation_id=self.key,
            start_at=(NOW-timedelta(hours=1)).isoformat(),
            end_at=(NOW+timedelta(minutes=1)).isoformat(),
            query_radius_km=10,
            db_path=self.db,
            now=NOW+timedelta(hours=1),
        )
        args.update(kwargs)
        return hypotheses.build_evidence_graph(**args)

    def test_candidate_is_inspectable_noncausal_and_stable(self):
        self.collect()
        first=self.graph()
        second=self.graph()
        self.assertEqual(len(first["hypotheses"]),1)
        h=first["hypotheses"][0]
        self.assertEqual(h["status"],"candidate_unverified")
        self.assertEqual(h["independent_lineage_count"],2)
        self.assertEqual(h["id"],second["hypotheses"][0]["id"])
        self.assertEqual(len(h["supporting_observation_ids"]),2)
        self.assertEqual(h["contradicting_observation_ids"],[])
        self.assertGreaterEqual(len(h["alternative_explanations"]),3)
        self.assertGreaterEqual(len(h["missing_evidence"]),2)
        self.assertIn("No causal",h["prohibited_conclusion"])
        self.assertEqual(first["causal_claims"],0)
        self.assertEqual(first["external_actions"],0)
        self.assertEqual(first["model_calls"],0)

    def test_every_edge_and_hypothesis_reference_exists_in_graph(self):
        self.collect()
        graph=self.graph()
        ids={node["id"] for node in graph["nodes"]}
        for edge in graph["edges"]:
            self.assertIn(edge["from"],ids)
            self.assertIn(edge["to"],ids)
            self.assertFalse(edge["causal"])
        for h in graph["hypotheses"]:
            self.assertTrue(set(h["supporting_observation_ids"]).issubset(ids))

    def test_source_revision_edge_has_both_traversable_nodes(self):
        self.collect()
        later=NOW+timedelta(minutes=15)
        changed=earthquakes(NOW-timedelta(minutes=12))
        changed["events"][0]["magnitude"]=3.6
        self.collect(at=later,air=conditions(later,aqi=52),quake=changed)
        graph=self.graph(
            end_at=(later+timedelta(minutes=1)).isoformat(),
            now=later+timedelta(hours=1),
        )
        revisions=[e for e in graph["edges"]
                   if e["type"]=="same_provider_revision"]
        self.assertGreaterEqual(len(revisions),1)
        ids={node["id"] for node in graph["nodes"]}
        for edge in revisions:
            self.assertIn(edge["from"],ids)
            self.assertIn(edge["to"],ids)
            self.assertFalse(edge["causal"])

    def test_nws_unknown_event_time_never_supports_temporal_hypothesis(self):
        self.collect()
        graph=self.graph(source_ids=["nws_point_alerts","usgs_earthquakes"])
        self.assertEqual(graph["hypotheses"],[])
        self.assertEqual(graph["receipt_time_only_count"],1)

    def test_missing_epicenter_is_not_inside_narrowed_radius(self):
        self.collect(quake=earthquakes(located=False))
        graph=self.graph(query_radius_km=2)
        self.assertEqual(graph["hypotheses"],[])
        self.assertEqual(graph["spatially_indeterminate_count"],1)

    def test_provider_unavailable_does_not_become_contradicting_evidence(self):
        self.collect(
            air=conditions(NOW,nws="unavailable"),
            quake=earthquakes(status="unavailable"),
        )
        graph=self.graph()
        self.assertEqual(graph["hypotheses"],[])
        self.assertIn("nws_point_alerts",graph["unavailable_or_unchecked_sources"])
        self.assertIn("usgs_earthquakes",graph["unavailable_or_unchecked_sources"])

    def test_mixed_fixture_and_real_adapter_evidence_cannot_form_hypothesis(self):
        self.collect(quake=earthquakes(status="unavailable"))
        later=NOW+timedelta(minutes=20)
        with patch.object(armor,"_clock",return_value=later), \
             patch("jarvis_mrb.physical_conditions.physical_conditions",
                   return_value={
                       "checked_at":later.isoformat(),
                       "air_quality":{"status":"unavailable"},
                       "weather_alerts":{"status":"unsupported_region","alerts":[]},
                   }), \
             patch("jarvis_mrb.public_incidents.regional_earthquakes",
                   return_value=earthquakes(later-timedelta(minutes=5))):
            armor.observe_once(self.key,db_path=self.db)
        graph=self.graph(
            end_at=(later+timedelta(minutes=1)).isoformat(),
            now=later+timedelta(hours=1),
        )
        self.assertEqual(graph["hypotheses"],[])
        self.assertEqual({n["adapter_mode"] for n in graph["nodes"]},
                         {"fixture","real_adapter"})

    def test_graph_is_read_only_and_off_gate_is_enforced(self):
        self.collect()
        before=armor.replay(
            self.key,db_path=self.db,now=NOW+timedelta(hours=1)
        )["sample_timeline"]
        graph=self.graph()
        after=armor.replay(
            self.key,db_path=self.db,now=NOW+timedelta(hours=1)
        )["sample_timeline"]
        self.assertEqual(before,after)
        self.assertEqual(graph["external_requests"],0)
        with patch.dict(os.environ,{"JARVIS_WORLD_ARMOR_ENABLED":"0"}):
            with self.assertRaises(armor.ArmorDisabled):
                self.graph()

    def test_claim_text_describes_cooccurrence_not_dependency(self):
        self.collect()
        claim=self.graph()["hypotheses"][0]["claim"].lower()
        for forbidden in ("caused","causes","responsible","because of","proof"):
            self.assertNotIn(forbidden,claim)


if __name__=="__main__":
    import unittest
    unittest.main()
