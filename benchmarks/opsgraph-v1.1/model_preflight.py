"""Bounded hosted-model probe through a domain-restricted CONNECT proxy."""
import http.server
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import threading
import time

ROOT = Path('/private/tmp/pi-opsgraph-v1.1')
ALLOWED = {'chatgpt.com', 'api.openai.com', 'auth.openai.com', 'ab.chatgpt.com'}
EVENTS = []

class Proxy(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_CONNECT(self):
        if self.path not in {host + ':443' for host in ALLOWED}:
            EVENTS.append({'target': self.path, 'allowed': False})
            self.send_error(403)
            return
        host = self.path[:-4]
        EVENTS.append({'target': host, 'allowed': True})
        try:
            with socket.create_connection((host, 443), timeout=15) as upstream:
                self.send_response(200)
                self.end_headers()
                peers = [self.connection, upstream]
                deadline = time.monotonic() + 150
                while time.monotonic() < deadline:
                    ready, _, _ = select.select(peers, [], [], 1)
                    for source in ready:
                        chunk = source.recv(65536)
                        if not chunk:
                            return
                        (upstream if source is self.connection else self.connection).sendall(chunk)
        except (OSError, TimeoutError):
            self.close_connection = True

def main():
    codex_home = ROOT / 'solver/.pi-engineering/codex-home'
    codex_home.mkdir(exist_ok=True)
    auth = codex_home / 'auth.json'
    if not auth.exists():
        auth.symlink_to('/Users/benchbrex/.codex/auth.json')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    env = {key: os.environ[key] for key in ['HOME', 'PATH', 'USER', 'LANG'] if key in os.environ}
    env.update(CODEX_HOME=str(codex_home), PYTHONPATH=str(ROOT / 'runtime'), PYTHONDONTWRITEBYTECODE='1',
        TMPDIR=str(ROOT / 'solver/.bench-tmp'), HTTPS_PROXY=f'http://127.0.0.1:{port}',
        HTTP_PROXY=f'http://127.0.0.1:{port}', ALL_PROXY=f'http://127.0.0.1:{port}',
        NO_PROXY='127.0.0.1,localhost')
    probe = "import asyncio; from pi_models import CodexModel; from pi_workspace import WorkspaceSettings; s=WorkspaceSettings().model; s.provider='codex'; s.model='default'; print(asyncio.run(CodexModel(s).chat([{'role':'user','content':'Infrastructure connectivity check only. Return content PREFLIGHT_OK and no calls. Do not perform any engineering task.'}], [])))"
    command = ['/usr/bin/sandbox-exec', '-f', str(ROOT / 'solver.sb'),
        '/Volumes/Parth Patel/PI/Pi_Engineering_CLI/.venv/bin/python', '-c', probe]
    try:
        result = subprocess.run(command, cwd=ROOT / 'solver', env=env, text=True, capture_output=True, timeout=150)
        evidence = dict(exit=result.returncode, stdout=result.stdout, stderr=result.stderr, connections=EVENTS)
        (ROOT / 'evaluator/model-preflight.json').write_text(json.dumps(evidence, indent=2))
        print(json.dumps(evidence, indent=2))
    finally:
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()
