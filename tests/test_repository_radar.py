from __future__ import annotations

from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

import httpx

from jarvis_mrb import repository_radar as radar


NOW=datetime(2026,10,15,19,0,tzinfo=timezone.utc)


def item(name:str,stars:int=12000,**kwargs):
    return {
        "full_name":name,
        "html_url":"https://github.com/"+name,
        "archived":False,"fork":False,"disabled":False,
        "description":"Open source component, not automatically safe.",
        "stargazers_count":stars,
        "updated_at":"2026-10-14T12:00:00Z",
        "license":{"key":"mit"},
        **kwargs,
    }


class Client:
    def __init__(self,responses):
        self.responses=iter(responses)
        self.requests=[]

    def get(self,url,*,params,headers,timeout):
        self.requests.append((url,params,headers))
        return next(self.responses)


def result(repos):
    return httpx.Response(200,json={"items":repos},request=httpx.Request("GET",radar._API))


class RepositoryRadarTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.path=Path(self.temp.name)/"radar.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_requires_explicit_scan_to_query_external_provider(self):
        self.assertEqual(radar.inspect(path=self.path)["count"],0)

    def test_merges_multiple_buckets_and_scores_without_inventing_verification(self):
        client=Client([result([item("valid/camera")]),result([item("valid/camera"),item("other/voice",4200)])])
        found=radar.scan(path=self.path,client=client,now=NOW,token="",
            buckets={"cameras":("topic:camera",),"voice":("topic:voice",)})
        self.assertEqual(found["total"],2)
        self.assertEqual(found["new_candidates"],2)
        saved=radar._read(self.path)
        matching=next(x for x in saved["repos"] if x["full_name"]=="valid/camera")
        self.assertEqual(set(matching["buckets"]),{"cameras","voice"})
        self.assertEqual(matching["review_status"],"candidate_not_validated_or_installed")
        self.assertEqual(len(client.requests),2)
        self.assertEqual(client.requests[0][0],radar._API)
        self.assertFalse(saved["partial"])

    def test_invalid_and_untrusted_repositories_are_rejected(self):
        bad=[
            item("not valid/repo"),item("valid/fork",fork=True),
            item("valid/archive",archived=True),
            item("valid/disabled",disabled=True),
            item("good/repo",html_url="https://github.com.attacker.tld/good/repo"),
            item("valid/name",html_url="http://github.com/valid/name"),
        ]
        client=Client([result(bad)])
        found=radar.scan(path=self.path,client=client,now=NOW,token="",
            buckets={"one":("test",)})
        self.assertEqual(found["total"],0)
        self.assertEqual(radar._read(self.path)["repos"],[])

    def test_failed_scan_does_not_erase_previous_known_candidates(self):
        radar._write(self.path,{"repos":[item("stored/project")],"scanned_at":"2026-10-10","queries_executed":1})
        client=Client([httpx.Response(429,json={"message":"rate-limited"},request=httpx.Request("GET",radar._API))])
        found=radar.scan(path=self.path,client=client,now=NOW,token="",
            buckets={"one":("test",)})
        self.assertFalse(found["ok"])
        self.assertEqual(radar.inspect(path=self.path)["count"],1)

    def test_second_scan_only_counts_new_candidates(self):
        client1=Client([result([item("same/first")])])
        radar.scan(path=self.path,client=client1,now=NOW,token="",buckets={"one":("test",)})
        client2=Client([result([item("same/first"),item("new/second")])])
        found=radar.scan(path=self.path,client=client2,now=NOW,token="",buckets={"one":("test",)})
        self.assertEqual(found["new_candidates"],1)

    def test_auth_token_is_passed_only_to_fixed_github_api(self):
        client=Client([result([])])
        radar.scan(path=self.path,client=client,now=NOW,token="secret",
                   buckets={"one":("test",)})
        url,params,headers=client.requests[0]
        self.assertEqual(url,"https://api.github.com/search/repositories")
        self.assertEqual(headers["Authorization"],"Bearer secret")
        self.assertNotIn("secret",str(radar.inspect(path=self.path)))


if __name__=="__main__":
    unittest.main()
