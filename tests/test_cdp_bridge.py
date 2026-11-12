"""Local synthetic CDP smoke test; never touches a real user browser."""
import base64
import http.server
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright
from PIL import Image

BRIDGE = Path(__file__).resolve().parents[1] / 'scripts' / 'cdp_bridge.py'
buffer = io.BytesIO()
Image.new('RGB', (10, 10), 'white').save(buffer, format='PNG')
PNG = buffer.getvalue()


class BridgeTest(unittest.TestCase):
    def test_existing_session_and_capture(self):
        with tempfile.TemporaryDirectory() as tmp, sync_playwright() as pw:
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    body = ('<title>fixture</title><img id="answer" src="data:image/png;base64,' + base64.b64encode(PNG).decode() + '">').encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html')
                    self.end_headers()
                    self.wfile.write(body)
                def log_message(self, *args):
                    pass
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            sock.close()
            browser = pw.chromium.launch(channel=os.environ.get('TEST_BROWSER_CHANNEL', 'msedge'), headless=True,
                                         args=[f'--remote-debugging-port={port}'])
            bridge = None
            try:
                page = browser.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}/')
                for _ in range(50):
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=1) as response:
                            ws = json.load(response)['webSocketDebuggerUrl']
                        break
                    except OSError:
                        time.sleep(.1)
                else:
                    self.fail('test browser did not expose CDP')
                portfile = Path(tmp) / 'DevToolsActivePort'
                portfile.write_text(f'{port}\n' + '/' + ws.split('/', 3)[-1], encoding='utf8')
                bridge = subprocess.Popen([sys.executable, str(BRIDGE), '--port-file', str(portfile)], stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE, text=True, encoding='utf8')
                def call(obj):
                    bridge.stdin.write(json.dumps(obj) + '\n')
                    bridge.stdin.flush()
                    return json.loads(bridge.stdout.readline())
                self.assertTrue(call({'target_url': page.url})['ok'])
                self.assertEqual(call({'op': 'state'})['result']['title'], 'fixture')
                result = call({'op': 'capture', 'selector': '#answer', 'output': str(Path(tmp) / 'answer.png')})
                self.assertTrue(result['ok'], result)
                self.assertEqual(Path(result['result']['path']).read_bytes(), PNG)
                self.assertFalse(call({'op': 'capture', 'selector': '.missing', 'output': str(Path(tmp) / 'x')})['ok'])
                self.assertTrue(call({'op': 'close'})['ok'])
                bridge.wait(timeout=10)
                self.assertEqual(page.title(), 'fixture')
            finally:
                if bridge and bridge.poll() is None:
                    bridge.kill()
                    bridge.wait()
                if bridge:
                    bridge.stdin.close()
                    bridge.stdout.close()
                browser.close()
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
