"""Mirror public RSS sources and report individual failures without overwriting feeds."""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import format_datetime
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MAX_BYTES = 10 * 1024 * 1024
ATOM = '{http://www.w3.org/2005/Atom}'


def atom_to_rss(root):
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = root.findtext(ATOM + 'title', '')
    for entry in root.findall(ATOM + 'entry'):
        item = ET.SubElement(channel, 'item')
        ET.SubElement(item, 'title').text = entry.findtext(ATOM + 'title', '')
        links = [link.get('href') for link in entry.findall(ATOM + 'link') if link.get('rel', 'alternate') == 'alternate']
        if not links or not links[0]:
            raise ValueError('Atom entry has no alternate link')
        ET.SubElement(item, 'link').text = links[0]
        ET.SubElement(item, 'guid').text = entry.findtext(ATOM + 'id') or links[0]
        timestamp = entry.findtext(ATOM + 'published') or entry.findtext(ATOM + 'updated')
        if not timestamp:
            raise ValueError('Atom entry has no timestamp')
        published = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        if published.utcoffset() is None:
            raise ValueError('Atom timestamp requires timezone')
        ET.SubElement(item, 'pubDate').text = format_datetime(published)
        content = entry.find(ATOM + 'content')
        if content is None:
            content = entry.find(ATOM + 'summary')
        if content is not None:
            ET.SubElement(item, 'description').text = ''.join(ET.tostring(child, encoding='unicode') for child in content) if len(content) else content.text or ''
    return rss


def validate_sources(sources):
    if not isinstance(sources, dict) or not sources:
        raise ValueError("sources must be a nonempty object")
    for filename, url in sources.items():
        if Path(filename).name != filename or not filename.endswith(".xml"):
            raise ValueError("source filenames must be plain .xml filenames")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("sources must use public HTTPS URLs without credentials")


def save_feed(body, destination):
    if len(body) > MAX_BYTES:
        raise ValueError("feed exceeds size limit")
    root = ET.fromstring(body)
    if root.tag == ATOM + 'feed':
        root = atom_to_rss(root)
        body = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("response is not RSS 2.0")
    items = root.findall("./channel/item")
    if not items:
        raise ValueError("feed contains no entries")
    temporary = destination.with_suffix(".xml.tmp")
    temporary.write_bytes(body)
    os.replace(temporary, destination)
    return len(items)


def fetch_one(filename, url, output):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 RSSFeedMirror/1.0"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                body = response.read(MAX_BYTES + 1)
            entries = save_feed(body, output / filename)
            return {"ok": True, "entries": entries}
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, ET.ParseError) as error:
            transient = error.code >= 500 or error.code == 429 if isinstance(error, HTTPError) else isinstance(error, (URLError, TimeoutError, OSError))
            if transient and attempt < 2:
                time.sleep(attempt + 1)
                continue
            return {"ok": False, "error": str(error)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=Path("sources.json"))
    parser.add_argument("--output", type=Path, default=Path("feeds"))
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text())
    validate_sources(sources)
    args.output.mkdir(parents=True, exist_ok=True)
    results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        tasks = {executor.submit(fetch_one, name, url, args.output): name for name, url in sources.items()}
        for task in as_completed(tasks):
            filename = tasks[task]
            result = task.result()
            results[filename] = result
            if result["ok"]:
                print(f"OK {filename}: {result['entries']} entries", flush=True)
            else:
                print(f"::warning::{filename}: {result['error']}", flush=True)
    successes = sum(result["ok"] for result in results.values())
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "successful": successes, "total": len(sources), "sources": results}
    (args.output / "status.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as stream:
            stream.write(f"RSS sources updated: {successes}/{len(sources)}\n\n")
            for filename, result in sorted(results.items()):
                if not result["ok"]:
                    stream.write(f"- {filename}: {result['error']}\n")
    print(f"Updated {successes}/{len(sources)} sources", flush=True)
    return 0 if successes else 1


if __name__ == "__main__":
    raise SystemExit(main())
