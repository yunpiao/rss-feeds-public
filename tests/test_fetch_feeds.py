from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fetch_feeds import save_feed, validate_sources, fetch_one
from unittest.mock import patch, MagicMock
from urllib.error import URLError


class FeedSafetyTest(unittest.TestCase):
    def test_transient_network_failure_retries_before_reporting_failure(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'<rss><channel><item><title>News</title></item></channel></rss>'
        with tempfile.TemporaryDirectory() as directory, patch('fetch_feeds.urlopen',side_effect=[URLError('temporary'),response]) as request, patch('fetch_feeds.time.sleep'):
            self.assertEqual(fetch_one('feed.xml','https://example.com/feed',Path(directory)),{'ok':True,'entries':1})
            self.assertEqual(request.call_count,2)

    def test_atom_is_normalized_without_losing_title_link_date_or_content(self):
        body=b'''<feed xmlns="http://www.w3.org/2005/Atom"><title>Products</title><entry><id>urn:item:1</id><title>New product</title><link href="https://example.com/item"/><published>2026-10-26T08:00:00+08:00</published><content type="html">&lt;p&gt;Details&lt;/p&gt;</content></entry></feed>'''
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'atom.xml'
            self.assertEqual(save_feed(body,destination),1)
            root=ET.parse(destination).getroot()
            self.assertEqual(root.tag,'rss')
            self.assertEqual(root.findtext('./channel/item/link'),'https://example.com/item')
            self.assertEqual(root.findtext('./channel/item/guid'),'urn:item:1')
            self.assertEqual(root.findtext('./channel/item/description'),'<p>Details</p>')
            self.assertEqual(root.findtext('./channel/item/pubDate'),'Mon, 26 Oct 2026 08:00:00 +0800')

    def test_atom_without_real_date_cannot_replace_previous_feed(self):
        body=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Missing date</title><link href="https://example.com/item"/></entry></feed>'
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'feed.xml';destination.write_text('previous')
            with self.assertRaises(ValueError):save_feed(body,destination)
            self.assertEqual(destination.read_text(),'previous')

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
