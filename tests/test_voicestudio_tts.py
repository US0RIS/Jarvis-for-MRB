from __future__ import annotations

import unittest
from unittest.mock import patch

from jarvis_mrb import tts_client as tts


WAV = b"RIFF" + (36).to_bytes(4,"little") + b"WAVE" + bytes(32)


class FakeResponse:
    def __init__(self,*,payload=None,body=WAV,status=200):
        self.payload=payload
        self.content=body
        self.status_code=status

    def raise_for_status(self):
        if self.status_code>=400: raise ValueError("HTTP error")

    def json(self):
        return self.payload


class FakeClient:
    calls=[]
    result=FakeResponse()

    def __init__(self,*args,**kwargs):
        self.args=args
        self.kwargs=kwargs

    def __enter__(self): return self
    def __exit__(self,*args): return False
    def post(self,url,*,json,headers):
        FakeClient.calls.append((url,json,headers))
        return FakeClient.result


class VoiceStudioIntegrationTests(unittest.TestCase):
    def setUp(self):
        FakeClient.calls=[]
        self.patches=[
            patch.object(tts,"TTS_PROVIDER","voicestudio"),
            patch.object(tts,"TTS_URL","http://127.0.0.1:3900"),
            patch.object(tts,"TTS_MODEL","tts-1"),
            patch.object(tts,"TTS_VOICE","alloy"),
            patch.object(tts,"VOICESTUDIO_API_KEY",""),
        ]
        for item in self.patches: item.start()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()

    def test_voicestudio_discovery_is_not_mistaken_for_kokoro(self):
        with patch.object(tts.httpx,"get",return_value=FakeResponse(payload={"protocol":"voicestudio.speech.v1"})) as get:
            self.assertTrue(tts.tts_health())
            self.assertIn("/.well-known/voicestudio-speech",get.call_args.args[0])
        with patch.object(tts.httpx,"get",return_value=FakeResponse(payload={"status":"ok"})):
            self.assertFalse(tts.tts_health())

    def test_no_kokoro_autostart_when_voicestudio_selected(self):
        with (
            patch.object(tts,"tts_health",return_value=False),
            patch.object(tts,"_wsl_start_command",side_effect=AssertionError("Kokoro started")),
        ):
            self.assertFalse(tts.ensure_tts_server())

    def test_generates_openai_compatible_wav_with_local_voice(self):
        with (
            patch.object(tts,"tts_health",return_value=True),
            patch.object(tts.httpx,"Client",FakeClient),
        ):
            result=tts.synthesize_wav("  Hello   through AirPods.  ")
        self.assertEqual(result,WAV)
        url,payload,headers=FakeClient.calls[0]
        self.assertEqual(url,"http://127.0.0.1:3900/v1/audio/speech")
        self.assertEqual(payload["model"],"tts-1")
        self.assertEqual(payload["voice"],"alloy")
        self.assertEqual(payload["input"],"Hello through AirPods.")
        self.assertEqual(payload["response_format"],"wav")
        self.assertEqual(headers,{})

    def test_rejects_html_that_looks_like_audio(self):
        FakeClient.result=FakeResponse(body=b"<html>"*12)
        try:
            with (
                patch.object(tts,"tts_health",return_value=True),
                patch.object(tts.httpx,"Client",FakeClient),
            ),self.assertRaises(RuntimeError):
                tts.synthesize_wav("Hi")
        finally:
            FakeClient.result=FakeResponse()

    def test_does_not_send_api_key_over_remote_cleartext(self):
        with (
            patch.object(tts,"TTS_URL","http://192.168.1.10:3900"),
            patch.object(tts,"VOICESTUDIO_API_KEY","verysecret"),
            patch.object(tts,"tts_health",return_value=True),
        ),self.assertRaises(RuntimeError):
            tts.synthesize_wav("Hi")

    def test_authenticated_local_service(self):
        with patch.object(tts,"VOICESTUDIO_API_KEY","privatekey"):
            self.assertEqual(tts._voicestudio_headers(),{"Authorization":"Bearer privatekey"})


if __name__=="__main__":
    unittest.main()
