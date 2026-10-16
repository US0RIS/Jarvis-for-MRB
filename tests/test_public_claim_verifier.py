from __future__ import annotations

import unittest
from unittest.mock import Mock

from jarvis_mrb.public_claim_verifier import _safe_source, verify_public_claim
from jarvis_mrb.tools.web import WebResult


URL = "https://blog.google/technology/ai/gemini-4-argon/"
QUESTION = "Did Google announce Gemini 4 Argon today?"


def search_results(entries):
    return lambda *args,**kwargs: WebResult(
        True, "retrieved", {"evidence":[{"kind":"organic","link":link,"text":text}
                                     for link,text in entries]}
    )


class FakePage:
    def __init__(self,body: bytes,status: int=200,ctype="text/html"):
        self.status_code=status
        self.headers={"content-type":ctype}
        self.content=body


class ClaimVerifierTests(unittest.TestCase):
    def test_source_must_be_official_https_without_redirects_or_creds(self):
        allowed=("blog.google",)
        self.assertTrue(_safe_source(URL,allowed))
        for url in (
            "http://blog.google/technology/ai/gemini-4",
            "https://notblog.google/technology/ai/gemini-4",
            "https://blog.google:444/technology/ai/",
            "https://user:pass@blog.google/technology/ai/",
            "https://blog.google:bad/technology/ai/",
            "https://blog.google/technology/ai/#fragment",
            "https://blog.google.evil.example/technology/ai/",
        ):
            with self.subTest(url=url):
                self.assertFalse(_safe_source(url,allowed))

    def test_original_first_party_page_is_fetched_before_reporting_a_mention(self):
        getter=Mock(return_value=FakePage(b"<html><title>Gemini 4 Argon</title><p>Introducing Gemini 4 Argon</p></html>"))
        result=verify_public_claim(
            QUESTION,
            search=search_results([(URL,"search snippet about Gemini 4 Argon")]),
            fetch=getter,
        )
        self.assertEqual(result["status"],"primary_source_mentions_subject")
        self.assertIn("does not authenticate",result["message"])
        self.assertEqual(len(result["sources"]),1)
        self.assertEqual(result["sources"][0]["source_type"],"first_party_page_fetched")
        self.assertFalse(getter.call_args.kwargs["follow_redirects"])

    def test_untrusted_snippet_without_primary_source_proves_nothing(self):
        getter=Mock(return_value=FakePage(b"Missing",status=404))
        result=verify_public_claim(
            QUESTION,
            search=search_results([(URL,"Announced according to snippet")]),
            fetch=getter,
        )
        self.assertEqual(result["status"],"unverified")
        self.assertIn("does not establish",result["message"])
        self.assertEqual(result["sources"],[])

    def test_unofficial_sources_not_fetched_and_not_counted(self):
        getter=Mock(side_effect=AssertionError("SSRF / unofficial fetch"))
        result=verify_public_claim(
            QUESTION,
            search=search_results([("https://blog.google.example/launch","fake announcement")]),
            fetch=getter,
        )
        self.assertEqual(result["status"],"unverified")
        getter.assert_not_called()

    def test_official_page_without_target_or_with_script_only_is_not_a_hit(self):
        getter=Mock(return_value=FakePage(b"<html><script>Gemini 4 Argon</script>Nothing announced here</html>"))
        result=verify_public_claim(
            QUESTION,search=search_results([(URL,"reported")]),fetch=getter,
        )
        self.assertEqual(result["status"],"unverified")

    def test_missing_search_is_not_evidence_of_falsity(self):
        result=verify_public_claim(
            QUESTION,search=lambda *args,**kwargs: WebResult(False,"no key"),
        )
        self.assertEqual(result["status"],"search_unavailable")
        self.assertIn("not evidence it is false",result["message"])

    def test_unsupported_provider_must_not_search_or_guess(self):
        result=verify_public_claim(
            "Did an unknown studio publish this screenshot?",
            search=lambda *args,**kwargs: self.fail("should not search"),
        )
        self.assertEqual(result["status"],"unsupported_official_domain")


if __name__=="__main__":
    unittest.main()
