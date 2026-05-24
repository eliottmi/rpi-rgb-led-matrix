#!/usr/bin/env python3
"""Web server that drives rpi-rgb-led-matrix examples and utilities.

Usage:
    python3 webserver/server.py [--host 0.0.0.0] [--port 8080] [--no-sudo]

The server runs entirely on the Python standard library. It serves a single
page that exposes a form for each example/utility in the repository.
Submitting a form spawns the binary; output (stdout+stderr) is captured and
streamed back to the browser. Only one program may run at a time.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
WEB_ROOT = os.path.join(REPO_ROOT, "webserver")
STATIC_DIR = os.path.join(WEB_ROOT, "static")
UPLOAD_DIR = os.path.join(WEB_ROOT, "uploads")

sys.path.insert(0, WEB_ROOT)
from programs import PROGRAMS, LED_MATRIX_OPTIONS, get_program  # noqa: E402

# --- Process manager -------------------------------------------------------


class Runner:
    """Single-process LED matrix program runner."""

    LOG_LINES = 2000

    def __init__(self, use_sudo: bool = True):
        # RLock so we can call _append_log (which acquires the condition
        # built on this lock) while we already hold the lock in start().
        self._lock = threading.RLock()
        self._proc: subprocess.Popen | None = None
        self._program_id: str | None = None
        self._argv: list[str] = []
        self._started_at: float = 0
        self._log: deque[str] = deque(maxlen=self.LOG_LINES)
        self._log_seq = 0
        self._log_cond = threading.Condition(self._lock)
        self._use_sudo = use_sudo
        self._reader_thread: threading.Thread | None = None

    # ---- log helpers ----
    def _append_log(self, line: str) -> None:
        with self._log_cond:
            self._log.append(line.rstrip("\n"))
            self._log_seq += 1
            self._log_cond.notify_all()

    def get_log_since(self, since: int) -> tuple[int, list[str]]:
        with self._log_cond:
            total = self._log_seq
            start = max(0, total - len(self._log))
            if since < start:
                since = start
            offset = since - start
            lines = list(self._log)[offset:]
            return total, lines

    # ---- status ----
    def status(self) -> dict:
        with self._lock:
            running = self._proc is not None and self._proc.poll() is None
            exit_code = None
            if self._proc is not None and not running:
                exit_code = self._proc.returncode
            return {
                "running": running,
                "program_id": self._program_id,
                "argv": self._argv,
                "started_at": self._started_at,
                "exit_code": exit_code,
                "log_seq": self._log_seq,
            }

    # ---- start / stop ----
    def start(self, program: dict, argv: list[str],
              stdin_text: str | None = None,
              env: dict | None = None) -> dict:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return {"ok": False, "error": "Un programme est déjà en cours d'exécution. Arrêtez-le d'abord."}
            cmd: list[str] = []
            if self._use_sudo and program.get("needs_root", False):
                if shutil.which("sudo") is None:
                    return {"ok": False,
                            "error": "sudo introuvable. Lancez le serveur en root ou avec --no-sudo."}
                cmd.append("sudo")
                cmd.append("-n")
            cmd.extend(argv)
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=REPO_ROOT,
                    stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    env={**os.environ, **(env or {})},
                    start_new_session=True,
                    bufsize=1,
                    universal_newlines=True,
                )
            except FileNotFoundError as e:
                return {"ok": False,
                        "error": f"Binaire introuvable: {e}. Avez-vous compilé l'exemple ?"}
            except PermissionError as e:
                return {"ok": False, "error": f"Permission refusée: {e}"}
            self._proc = proc
            self._program_id = program["id"]
            self._argv = cmd
            self._started_at = time.time()
            self._log.clear()
            self._log_seq = 0
            self._append_log(f"$ {' '.join(shlex.quote(c) for c in cmd)}")
            if stdin_text is not None and proc.stdin is not None:
                try:
                    proc.stdin.write(stdin_text)
                    if not stdin_text.endswith("\n"):
                        proc.stdin.write("\n")
                    proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    pass
            self._reader_thread = threading.Thread(
                target=self._read_loop, args=(proc,), daemon=True)
            self._reader_thread.start()
            return {"ok": True}

    def _read_loop(self, proc: subprocess.Popen) -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self._append_log(line)
        except Exception as e:
            self._append_log(f"[reader error: {e}]")
        rc = proc.wait()
        self._append_log(f"[process exited with code {rc}]")

    def send_stdin(self, text: str) -> dict:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                return {"ok": False, "error": "Aucun processus en cours."}
            if self._proc.stdin is None:
                return {"ok": False, "error": "Le processus n'a pas de stdin."}
            try:
                self._proc.stdin.write(text)
                if not text.endswith("\n"):
                    self._proc.stdin.write("\n")
                self._proc.stdin.flush()
                return {"ok": True}
            except (BrokenPipeError, OSError) as e:
                return {"ok": False, "error": f"Erreur d'écriture stdin: {e}"}

    def stop(self) -> dict:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                return {"ok": True, "message": "Aucun processus en cours."}
            pid = self._proc.pid
            argv = self._argv
        # Kill the whole process group so child binaries spawned via sudo die too.
        killed = False
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            killed = True
        except ProcessLookupError:
            killed = True
        except PermissionError:
            # sudo elevated the child; ask sudo to kill it.
            if argv and argv[0] == "sudo":
                try:
                    subprocess.run(
                        ["sudo", "-n", "kill", "-TERM", str(pid)],
                        check=False, timeout=5)
                    killed = True
                except Exception:
                    pass
        if not killed:
            return {"ok": False, "error": "Impossible de terminer le processus."}
        for _ in range(30):
            if self._proc is None or self._proc.poll() is not None:
                break
            time.sleep(0.1)
        # Force kill if still alive.
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                try:
                    os.killpg(os.getpgid(self._proc.pid), signal.SIGKILL)
                except Exception:
                    pass
                if argv and argv[0] == "sudo":
                    try:
                        subprocess.run(
                            ["sudo", "-n", "kill", "-KILL", str(self._proc.pid)],
                            check=False, timeout=5)
                    except Exception:
                        pass
        return {"ok": True}


# --- Argument building -----------------------------------------------------


COLOR_RE = re.compile(r"^\d{1,3},\d{1,3},\d{1,3}$")


def _coerce(opt: dict, raw_value):
    t = opt["type"]
    if t == "bool":
        return bool(raw_value)
    if raw_value in (None, ""):
        return None
    if t == "int":
        return int(raw_value)
    if t == "float":
        return float(raw_value)
    if t == "color":
        if not COLOR_RE.match(str(raw_value)):
            raise ValueError(f"Couleur invalide pour {opt['name']}: {raw_value!r}")
        # Sanity check 0..255 per channel.
        for chan in str(raw_value).split(","):
            n = int(chan)
            if not (0 <= n <= 255):
                raise ValueError(f"Couleur hors plage pour {opt['name']}: {raw_value!r}")
        return str(raw_value)
    return str(raw_value)


def _file_ok(opt: dict, raw_value: str) -> str:
    """Validate that a file value resolves inside one of the allowed dirs."""
    if raw_value in (None, ""):
        return ""
    # Normalize and make absolute relative to repo root if needed.
    candidate = raw_value
    abs_path = os.path.abspath(
        os.path.join(REPO_ROOT, candidate)
        if not os.path.isabs(candidate) else candidate)
    allowed = []
    for d in opt.get("dirs", []):
        allowed.append(os.path.abspath(os.path.join(REPO_ROOT, d)))
    for root in allowed:
        if abs_path == root or abs_path.startswith(root + os.sep):
            if not os.path.isfile(abs_path):
                raise ValueError(f"Fichier introuvable: {raw_value}")
            return os.path.relpath(abs_path, REPO_ROOT)
    raise ValueError(f"Chemin de fichier non autorisé: {raw_value}")


def build_argv(program: dict, values: dict) -> tuple[list[str], str | None]:
    """Return (argv, stdin_text).

    argv starts with the binary path. Common LED options come first, then
    program-specific options (with flags), then any positional values.
    """
    binary = os.path.join(REPO_ROOT, program["binary"])
    argv = [binary]
    positional_values = {}
    stdin_text = None
    stdin_field = program.get("stdin_field")

    def emit(opt, value):
        if opt["type"] == "bool":
            if value:
                argv.append(opt["flag"])
            return
        if value is None or value == "":
            return
        if opt.get("omit_if_default") and value == opt.get("default"):
            return
        if opt.get("flag"):
            argv.append(opt["flag"])
            argv.append(str(value))

    for opt in LED_MATRIX_OPTIONS:
        raw = values.get(opt["name"])
        emit(opt, _coerce(opt, raw))

    positional_names = set(program.get("positional", []))
    for opt in program.get("specific_options", []):
        name = opt["name"]
        raw = values.get(name)
        if opt.get("stdin_only"):
            if stdin_field == name and raw:
                stdin_text = str(raw)
            continue
        if opt["type"] == "file":
            value = _file_ok(opt, raw or opt.get("default", ""))
        elif name == "format" and program["id"] == "clock":
            # Multiple -d allowed; split on "|".
            if raw is None or raw == "":
                value = None
            else:
                lines = [l for l in str(raw).split("|") if l != ""]
                for ln in lines:
                    argv.append("-d")
                    argv.append(ln)
                continue
        else:
            value = _coerce(opt, raw)
        if opt.get("required") and (value is None or value == ""):
            raise ValueError(f"Option requise: {name}")
        if name in positional_names:
            positional_values[name] = value
        else:
            emit(opt, value)

    for name in program.get("positional", []):
        v = positional_values.get(name)
        if v:
            argv.append(str(v))

    return argv, stdin_text


# --- File helpers ----------------------------------------------------------


def list_files(opt: dict) -> list[str]:
    out = []
    for d in opt.get("dirs", []):
        root = os.path.abspath(os.path.join(REPO_ROOT, d))
        if not os.path.isdir(root):
            continue
        exts = [e.lower() for e in opt.get("exts", [])]
        for dirpath, _dirs, files in os.walk(root):
            for f in files:
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, REPO_ROOT)
                if exts and not any(f.lower().endswith(e) for e in exts):
                    continue
                out.append(rel)
    out.sort()
    return out


# --- HTTP handler ----------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    runner: Runner  # set on class

    server_version = "rpi-rgb-led-matrix-web/1.0"

    def log_message(self, fmt, *args):  # quiet
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ---- helpers ----
    def _send_json(self, obj, status=200):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: str, content_type: str):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            self.send_error(404, "Not Found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def _read_json(self):
        body = self._read_body()
        if not body:
            return {}
        return json.loads(body.decode("utf-8"))

    # ---- routing ----
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path
        if path == "/" or path == "/index.html":
            self._send_file(os.path.join(STATIC_DIR, "index.html"),
                            "text/html; charset=utf-8")
            return
        if path == "/app.js":
            self._send_file(os.path.join(STATIC_DIR, "app.js"),
                            "application/javascript; charset=utf-8")
            return
        if path == "/style.css":
            self._send_file(os.path.join(STATIC_DIR, "style.css"),
                            "text/css; charset=utf-8")
            return

        if path == "/api/programs":
            self._send_json({
                "common": LED_MATRIX_OPTIONS,
                "programs": PROGRAMS,
            })
            return
        if path == "/api/files":
            qs = parse_qs(url.query)
            program_id = (qs.get("program") or [""])[0]
            option_name = (qs.get("option") or [""])[0]
            prog = get_program(program_id)
            if prog is None:
                self._send_json({"files": []})
                return
            for opt in prog.get("specific_options", []):
                if opt["name"] == option_name and opt["type"] == "file":
                    self._send_json({"files": list_files(opt)})
                    return
            self._send_json({"files": []})
            return
        if path == "/api/status":
            self._send_json(Handler.runner.status())
            return
        if path == "/api/log":
            qs = parse_qs(url.query)
            since = int((qs.get("since") or ["0"])[0])
            total, lines = Handler.runner.get_log_since(since)
            self._send_json({"seq": total, "lines": lines,
                             "status": Handler.runner.status()})
            return
        self.send_error(404, "Not Found")

    def do_POST(self):
        url = urlparse(self.path)
        path = url.path
        try:
            if path == "/api/start":
                data = self._read_json()
                program_id = data.get("program_id") or ""
                values = data.get("values") or {}
                prog = get_program(program_id)
                if prog is None:
                    self._send_json({"ok": False,
                                     "error": f"Programme inconnu: {program_id}"},
                                    status=400)
                    return
                try:
                    argv, stdin_text = build_argv(prog, values)
                except ValueError as e:
                    self._send_json({"ok": False, "error": str(e)}, status=400)
                    return
                res = Handler.runner.start(prog, argv, stdin_text=stdin_text)
                if not res.get("ok"):
                    self._send_json(res, status=400)
                    return
                self._send_json({"ok": True, "argv": argv})
                return
            if path == "/api/stop":
                self._send_json(Handler.runner.stop())
                return
            if path == "/api/stdin":
                data = self._read_json()
                text = data.get("text", "")
                self._send_json(Handler.runner.send_stdin(text))
                return
            if path == "/api/build":
                data = self._read_json()
                program_id = data.get("program_id") or ""
                prog = get_program(program_id)
                if prog is None:
                    self._send_json({"ok": False, "error": "Programme inconnu"},
                                    status=400)
                    return
                build_dir = os.path.join(REPO_ROOT, prog.get("build_dir", "."))
                target = prog.get("build_target", "")
                cmd = ["make"]
                if target:
                    cmd.append(target)
                try:
                    cp = subprocess.run(cmd, cwd=build_dir,
                                        capture_output=True, text=True,
                                        timeout=600)
                except FileNotFoundError:
                    self._send_json({"ok": False,
                                     "error": "make introuvable"}, status=500)
                    return
                output = (cp.stdout or "") + (cp.stderr or "")
                self._send_json({"ok": cp.returncode == 0,
                                 "returncode": cp.returncode,
                                 "output": output})
                return
            if path == "/api/upload":
                self._handle_upload()
                return
        except Exception as e:
            self._send_json({"ok": False, "error": f"{type(e).__name__}: {e}"},
                            status=500)
            return
        self.send_error(404, "Not Found")

    # ---- multipart upload ----
    def _handle_upload(self):
        ctype = self.headers.get("Content-Type", "")
        m = re.match(r"multipart/form-data;\s*boundary=(.+)", ctype, re.I)
        if not m:
            self._send_json({"ok": False, "error": "multipart/form-data attendu"},
                            status=400)
            return
        boundary = ("--" + m.group(1)).encode()
        body = self._read_body()
        parts = body.split(boundary)
        saved = []
        for part in parts:
            part = part.lstrip(b"\r\n")
            if not part or part.startswith(b"--"):
                continue
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue
            headers_blob = part[:header_end].decode("utf-8", errors="replace")
            content = part[header_end + 4:]
            # Strip trailing CRLF.
            if content.endswith(b"\r\n"):
                content = content[:-2]
            fname_match = re.search(
                r'filename="([^"]*)"', headers_blob, re.I)
            if not fname_match:
                continue
            filename = os.path.basename(fname_match.group(1))
            if not filename:
                continue
            # Sanitize: keep only safe chars.
            filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            target = os.path.join(UPLOAD_DIR, filename)
            with open(target, "wb") as f:
                f.write(content)
            saved.append(os.path.relpath(target, REPO_ROOT))
        self._send_json({"ok": True, "files": saved})


# --- main ------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="0.0.0.0", help="Bind address (default 0.0.0.0)")
    ap.add_argument("--port", type=int, default=8080, help="Port (default 8080)")
    ap.add_argument("--no-sudo", action="store_true",
                    help="Do not prefix binaries with sudo (useful for testing)")
    args = ap.parse_args()

    Handler.runner = Runner(use_sudo=not args.no_sudo)
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"rpi-rgb-led-matrix web UI listening on http://{args.host}:{args.port}/")
    print(f"  repo root: {REPO_ROOT}")
    print(f"  sudo:      {'no' if args.no_sudo else 'yes'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        try:
            Handler.runner.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
