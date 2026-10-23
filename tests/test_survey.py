from pathlib import Path
import tempfile
import unittest
from scripts.survey_image import survey
from native_port.sources import MAGIC


class ImageSurveyTests(unittest.TestCase):
    def test_stream_boundary_and_false_positive_header(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'synthetic.iso'
            b = bytearray(8*1024*1024 + 100)
            at = 8*1024*1024-10
            b[at:at+len(MAGIC)] = MAGIC
            b[100:104] = b'XEX2'
            p.write_bytes(b)
            result = survey(p)
            self.assertEqual(result['signature_counts'][MAGIC.decode()], 1)
            self.assertEqual(result['signature_offsets'][MAGIC.decode()], [at])
            self.assertFalse(result['xex_candidates'][0]['plausible_header'])
            self.assertTrue(result['read_only'])
            self.assertFalse(result['ready'])
            self.assertEqual(p.read_bytes(), b)
