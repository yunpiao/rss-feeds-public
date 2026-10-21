from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_feeds import save_feed, validate_sources


class FeedSafetyTest(unittest.TestCase):
    def test_invalid_response_preserves_previous_feed(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "example.xml"
            original = b'<rss><channel><item><title>Earlier</title></item></channel></rss>'
            destination.write_bytes(original)
            with self.assertRaises(ValueError):
                save_feed(b'<html><body>upstream error</body></html>', destination)
            self.assertEqual(destination.read_bytes(), original)

    def test_valid_feed_is_written(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "example.xml"
            body = b'<rss><channel><item><title>Today</title></item></channel></rss>'
            self.assertEqual(save_feed(body, destination), 1)
            self.assertEqual(destination.read_bytes(), body)

    def test_empty_feed_does_not_replace_previous_content(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                save_feed(b'<rss><channel/></rss>', Path(directory) / 'example.xml')

    def test_rejects_credentials_and_path_traversal(self):
        for sources in [{"../outside.xml": "https://example.com/feed"}, {"feed.xml": "https://user:password@example.com/feed"}, {}]:
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                validate_sources(sources)


if __name__ == "__main__":
    unittest.main()
