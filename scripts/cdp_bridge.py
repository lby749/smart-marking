"""Authorized browser bridge; one JSON request per stdin line, no model calls."""
import argparse
import base64
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image
from playwright.sync_api import sync_playwright


def endpoint_from_file(path):
    lines = Path(path).read_text(encoding='utf-8').splitlines()
    port = int(lines[0])
    browser_path = lines[1].strip()
    if not 1 <= port <= 65535 or not re.fullmatch(r'/devtools/browser/[A-Za-z0-9-]+', browser_path):
        raise ValueError('invalid DevToolsActivePort')
    return f'ws://127.0.0.1:{port}{browser_path}'


def extract_image(page, frame, selector):
    locator = frame.locator(selector)
    if locator.count() != 1:
        raise ValueError('selector must match exactly one element')
    element = locator.first
    info = element.evaluate('''e => ({tag:e.tagName, complete:e.complete,
        width:e.naturalWidth || e.width, height:e.naturalHeight || e.height,
        url:e.tagName === 'IMG' ? (e.currentSrc || e.src) : null})''')
    if info['tag'] not in ('IMG', 'CANVAS') or not info['width'] or not info['height']:
        raise ValueError('answer image is not ready')
    if info['tag'] == 'IMG' and not info['complete']:
        raise ValueError('answer image is not ready')
    raw = element.evaluate('''async e => {
      try {
        let b;
        if (e.tagName === 'IMG') {
          let r = await fetch(e.currentSrc || e.src, {credentials:'same-origin', signal:AbortSignal.timeout(7000)});
          if (!r.ok) return null;
          b = await r.blob();
        } else b = await new Promise(resolve => e.toBlob(resolve, 'image/png'));
        if (!b || !b.type.startsWith('image/')) return null;
        return await new Promise(resolve => {let r=new FileReader();r.onload=()=>resolve(r.result);r.readAsDataURL(b)});
      } catch (_) { return null; }
    }''')
    source = 'page_resource_or_canvas'
    if raw:
        data = base64.b64decode(raw.split(',', 1)[1], validate=True)
    elif info['url'] and urlsplit(info['url']).scheme in ('http', 'https'):
        response = page.context.request.get(info['url'], timeout=15000)
        try:
            if not response.ok:
                raise ValueError('image request failed')
            data = response.body()
        finally:
            response.dispose()
        source = 'browser_context_resource'
    else:
        raise ValueError('cannot obtain the original image')
    with Image.open(io.BytesIO(data)) as image:
        if image.size != (info['width'], info['height']):
            raise ValueError('original image dimensions differ from the page')
        image.verify()
    return data, source


def serve(page):
    for line in sys.stdin:
        try:
            request = json.loads(line)
            operation = request['op']
            if operation == 'close':
                print(json.dumps({'ok': True, 'result': 'disconnected'}), flush=True)
                return
            if operation == 'state':
                result = {'title': page.title(), 'frame_count': len(page.frames), 'closed': page.is_closed()}
            elif operation == 'eval':
                frame = page.frames[request.get('frame', 0)]
                result = frame.evaluate(request['code'], request.get('arg'))
            elif operation == 'capture':
                frame = page.frames[request.get('frame', 0)]
                data, source = extract_image(page, frame, request['selector'])
                path = Path(request['output']).expanduser().resolve()
                with path.open('xb') as output:
                    output.write(data)
                result = {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'source': source}
            else:
                raise ValueError('unknown operation')
            print(json.dumps({'ok': True, 'result': result}, ensure_ascii=False), flush=True)
        except Exception as exc:
            # Do not echo URLs, authentication material, page data or exception details.
            print(json.dumps({'ok': False, 'error': type(exc).__name__}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port-file', required=True, help='Existing user-authorized DevToolsActivePort file')
    args = parser.parse_args()
    # The target URL is received over stdin instead of process arguments or logs.
    target = json.loads(sys.stdin.readline())['target_url']
    if urlsplit(target).scheme not in ('http', 'https'):
        raise ValueError('invalid target URL')
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(endpoint_from_file(args.port_file), timeout=120000)
        pages = [p for c in browser.contexts for p in c.pages if p.url == target]
        if len(pages) != 1:
            raise ValueError('target tab is not unique')
        print(json.dumps({'ok': True, 'result': 'connected'}), flush=True)
        serve(pages[0])
        # Stop Playwright without calling browser.close() on the user's session.


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': type(exc).__name__}), flush=True)
        sys.exit(1)
