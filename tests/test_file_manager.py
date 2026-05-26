"""Tests for smartvoice.file_manager — upload validation, sanitization, phone extraction."""

import unittest

from smartvoice import file_manager


class TestExtensionAndHash(unittest.TestCase):
    def test_allowed_extensions(self):
        self.assertTrue(file_manager.is_allowed_extension("call.wav"))
        self.assertTrue(file_manager.is_allowed_extension("call.WAV"))
        self.assertTrue(file_manager.is_allowed_extension("call.mp3"))
        self.assertFalse(file_manager.is_allowed_extension("call.flac"))
        self.assertFalse(file_manager.is_allowed_extension("call.exe"))
        self.assertFalse(file_manager.is_allowed_extension("noext"))

    def test_compute_file_hash_stable(self):
        h1 = file_manager.compute_file_hash(b"hello world")
        h2 = file_manager.compute_file_hash(b"hello world")
        h3 = file_manager.compute_file_hash(b"different")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)
        self.assertEqual(len(h1), 64)  # sha256 hex length


class TestAudioSniff(unittest.TestCase):
    def test_wav_magic(self):
        wav_bytes = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 100
        self.assertEqual(file_manager.sniff_audio_type(wav_bytes), "wav")

    def test_mp3_id3_magic(self):
        mp3_bytes = b"ID3\x03\x00\x00\x00" + b"\x00" * 100
        self.assertEqual(file_manager.sniff_audio_type(mp3_bytes), "mp3")

    def test_mp3_frame_sync(self):
        mp3_bytes = b"\xff\xfb\x90\x00" + b"\x00" * 100
        self.assertEqual(file_manager.sniff_audio_type(mp3_bytes), "mp3")

    def test_invalid_bytes(self):
        self.assertIsNone(file_manager.sniff_audio_type(b""))
        self.assertIsNone(file_manager.sniff_audio_type(b"abc"))
        self.assertIsNone(file_manager.sniff_audio_type(b"not-audio"))


class TestValidateUpload(unittest.TestCase):
    def test_valid_wav(self):
        wav = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 100
        ok, msg = file_manager.validate_upload(wav, "call.wav")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_empty_file(self):
        ok, msg = file_manager.validate_upload(b"", "call.wav")
        self.assertFalse(ok)
        self.assertIn("ว่างเปล่า", msg)

    def test_oversized(self):
        # 101 MB of zeros
        big = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * (101 * 1024 * 1024)
        ok, msg = file_manager.validate_upload(big, "call.wav")
        self.assertFalse(ok)
        self.assertIn("MB", msg)

    def test_wrong_extension(self):
        wav = b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 100
        ok, msg = file_manager.validate_upload(wav, "call.flac")
        self.assertFalse(ok)
        self.assertIn(".wav", msg)

    def test_fake_audio(self):
        fake = b"PK\x03\x04" + b"\x00" * 100  # zip header, not audio
        ok, msg = file_manager.validate_upload(fake, "call.wav")
        self.assertFalse(ok)
        self.assertIn("magic", msg.lower())


class TestSanitizeFilename(unittest.TestCase):
    def test_strips_path(self):
        self.assertEqual(
            file_manager.sanitize_filename("/etc/passwd.wav"), "passwd.wav"
        )
        self.assertEqual(
            file_manager.sanitize_filename("..\\..\\evil.wav"), "evil.wav"
        )
        self.assertEqual(
            file_manager.sanitize_filename("C:\\Windows\\foo.wav"), "foo.wav"
        )

    def test_replaces_dangerous_chars(self):
        # 7 dangerous chars: < > : " | ? * → 7 underscores
        self.assertEqual(
            file_manager.sanitize_filename('weird<>:"|?*.wav'), "weird_______.wav"
        )

    def test_empty_fallback(self):
        self.assertEqual(file_manager.sanitize_filename(""), "unnamed.wav")

    def test_keeps_thai(self):
        # Thai filenames should pass through unchanged
        self.assertEqual(
            file_manager.sanitize_filename("สาย-ลูกค้า.mp3"), "สาย-ลูกค้า.mp3"
        )


class TestPhoneExtraction(unittest.TestCase):
    def test_mobile_phone_in_filename(self):
        self.assertEqual(
            file_manager.extract_phone_from_filename(
                "20251225134209-1766644826-0812345678-Inbound.wav"
            ),
            "0812345678",
        )

    def test_landline(self):
        self.assertEqual(
            file_manager.extract_phone_from_filename("call-0212345678-log.mp3"),
            "0212345678",
        )

    def test_no_phone(self):
        self.assertIsNone(
            file_manager.extract_phone_from_filename("random_recording.wav")
        )

    def test_rejects_11_digit_number(self):
        # Must be exactly 10 digits — 11 digits shouldn't match
        self.assertIsNone(
            file_manager.extract_phone_from_filename("98123456789.wav")
        )

    def test_rejects_not_starting_with_zero(self):
        self.assertIsNone(
            file_manager.extract_phone_from_filename("1234567890.wav")
        )


class TestDirectionExtraction(unittest.TestCase):
    """Direction tag is read from the CDR filename suffix — used by the Admin
    page filter (Omazz request: separate Inbound vs Outbound views)."""

    def test_inbound_filename(self):
        self.assertEqual(
            file_manager.extract_direction_from_filename(
                "20251225134209-1766644826-0631451550-104-Inbound.wav"
            ),
            "inbound",
        )

    def test_outbound_filename(self):
        self.assertEqual(
            file_manager.extract_direction_from_filename(
                "20251104173706-1762252614-0819979336-Outbound.wav"
            ),
            "outbound",
        )

    def test_case_insensitive(self):
        self.assertEqual(
            file_manager.extract_direction_from_filename("call-INBOUND.wav"),
            "inbound",
        )
        self.assertEqual(
            file_manager.extract_direction_from_filename("call-outbound.MP3"),
            "outbound",
        )

    def test_unknown_when_no_tag(self):
        self.assertIsNone(
            file_manager.extract_direction_from_filename("random_recording.wav")
        )

    def test_empty_filename(self):
        self.assertIsNone(file_manager.extract_direction_from_filename(""))
        self.assertIsNone(file_manager.extract_direction_from_filename(None))


class TestAgentCodeExtraction(unittest.TestCase):
    """Agent extension is encoded in the CDR filename — used by the Dashboard
    Agent Performance filter (Omazz request: separate agents by code)."""

    def test_outbound_layout(self):
        # Outbound: TIMESTAMP-CALLID.NNN-AGENT-PHONE-Outbound.wav
        self.assertEqual(
            file_manager.extract_agent_code_from_filename(
                "20251104173706-1762252614.105999-104-0819979336-Outbound.wav"
            ),
            "104",
        )

    def test_inbound_layout(self):
        # Inbound: TIMESTAMP-CALLID.NNN-PHONE-AGENT-Inbound.wav
        self.assertEqual(
            file_manager.extract_agent_code_from_filename(
                "20251225134209-1766644826.135925-0631451550-104-Inbound.wav"
            ),
            "104",
        )

    def test_different_agent_codes(self):
        self.assertEqual(
            file_manager.extract_agent_code_from_filename(
                "20251225134109-1766644797.135924-0653965264-102-Inbound.wav"
            ),
            "102",
        )

    def test_ignores_timestamp_prefix(self):
        # 14-digit timestamp must not be picked as an agent code
        self.assertNotEqual(
            file_manager.extract_agent_code_from_filename(
                "20251104173706-1762252614.105999-104-0819979336-Outbound.wav"
            ),
            "20251104173706",
        )

    def test_ignores_thai_phone(self):
        # 10-digit phone starting with 0 must not be picked
        self.assertNotEqual(
            file_manager.extract_agent_code_from_filename(
                "20251104173706-1762252614.105999-104-0819979336-Outbound.wav"
            ),
            "0819979336",
        )

    def test_unknown_when_no_short_code(self):
        self.assertIsNone(
            file_manager.extract_agent_code_from_filename(
                "20251104173706-0819979336-Outbound.wav"
            )
        )

    def test_empty_or_none(self):
        self.assertIsNone(file_manager.extract_agent_code_from_filename(""))
        self.assertIsNone(file_manager.extract_agent_code_from_filename(None))


if __name__ == "__main__":
    unittest.main()
