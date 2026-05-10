import json
import sys
import threading
import socket 
import os

import plask
from .adapter import DebuggerAdapter

def run_server(adapter, code, HOST, PORT, env=None):
    conn = None

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT) if PORT is not None else (HOST, 0))
        s.listen()

        PORT = s.getsockname()[1]
        print(f"[DEBUGGER]: Started socket on: {HOST}:{PORT}", flush=True)

        conn, addr = s.accept()
        print(f"[DEBUGGER]: Connected by {addr}", flush=True)

        def emit_state(state_json):
            try:
                conn.sendall(state_json.encode("utf-8") + b"\n")
            except OSError:
                pass

        adapter.emit_state = emit_state

        buffer = b""

        def run_dbg():
            adapter.run(code, env=env)

        def socket_loop():
            nonlocal buffer
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        cmd = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
                    adapter.handle_command(cmd)

        socket_thread = threading.Thread(target=socket_loop, daemon=True)
        socket_thread.start()

        run_dbg()

    print("[DEBUGGER]: Successfully exited")

def compile_xpl(source, first_line=0, defs={}):
    env = globals().copy()
    env['plask'] = sys.modules["plask"]
    env.update(defs)
    plask.loadxpl(source, defs, destination=env)
    if type(source) == str:
        if not source.lstrip().startswith('<plask'):
            filename = source
        else:
            filename = "<source>"
    else:
        try: filename = source.name
        except: filename = "<source>"
    env.update(env['__manager__'].defs)
    try:
        script = ("\n" * (first_line - 2)) + env['__script__']
        with open("xpl_contents", "w") as f:
            f.write(str(script))
        code = compile(script, filename, 'exec')
        return code, env
    except Exception as exc:
        ety, eva, etb = sys.exc_info()
        plask._plask._print_exception(ety, eva, etb, filename, '<script>', env['__manager__']._scriptline)


if __name__ == "__main__":
    PORT = None
    WORK_DIR = None

    # Parse command-line flags
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        try:
            PORT = int(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("Error: --port must be followed by a valid number", flush=True)
            sys.exit(1)
        sys.argv.pop(idx)
        sys.argv.pop(idx)

    if "--work_dir" in sys.argv:
        idx = sys.argv.index("--work_dir")
        try:
            WORK_DIR = str(sys.argv[idx + 1])
        except (IndexError, ValueError):
            print("Error: --work_dir must be followed by a string path", flush=True)
            sys.exit(1)
        sys.argv.pop(idx)
        sys.argv.pop(idx)

    if len(sys.argv) < 2:
        print("Usage: python debugger.py <file.xpl> [breakpoints] [--port <port>]", flush=True)
        sys.exit(1)

    script_path = sys.argv[1]
    breakpoints = sys.argv[2] if len(sys.argv) >= 3 else ""

    manager = plask.Manager()
    manager.load(script_path)
    first_line = manager._scriptline

    code, env = compile_xpl(script_path, first_line=first_line, defs={})
    adapter = DebuggerAdapter(line_offset=first_line)

    # Parse breakpoints
    for bp in breakpoints.split(","):
        if bp.strip():
            try:
                bp_file, bp_line = bp.split(":")
                adapter.debugger.set_break(bp_file.strip(), int(bp_line))
            except ValueError:
                print(f"Invalid breakpoint format: {bp}", flush=True)

    if WORK_DIR is not None:
        os.chdir(WORK_DIR)

    print("[DEBUGGER]: Loading and compilation finished", flush=True)

    HOST = "127.0.0.1"

    run_server(adapter, code, HOST, PORT, env=env)
