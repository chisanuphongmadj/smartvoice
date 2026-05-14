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


if __name__ == "__main__":
    unittest.main()
