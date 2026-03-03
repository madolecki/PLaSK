import bdb
import json
import sys
import threading
import queue
import socket
import struct
import os

import plask

class Debugger(bdb.Bdb):
    def __init__(self, sock, line_offset=0):
        super().__init__()
        self.command_queue = queue.Queue()
        self.frame = None
        self.sock = sock
        self.call_stack = []
        self.init_lines = None
        self.line_offset = line_offset
        self.finished = False

    def run(self, cmd, globals=None, locals=None):
        try:
            super().run(cmd, globals, locals)
        finally:
            self.finished = True
            self.send_command("continue") # Skip the manatory breakpoint on line 1

    def _frame_info(self, frame):
        return {
            "function": frame.f_code.co_name,
            "file": os.path.relpath(frame.f_code.co_filename),
            "line": frame.f_lineno,
            "local_vars": list(frame.f_locals.items()),
        }

    def _update_top_frame_line(self, frame):
        if self.call_stack:
            self.call_stack[-1]["line"] = frame.f_lineno

    def send(self, event, frame, **extra):
        self.frame = frame
        
        # TODO: Try setting the ignored vars form the config class: https://docs.plask.app/api/plask/plask.config
        if self.init_lines is None:
            self.init_lines = dict(frame.f_locals)

        locals_filtered = {
            k: v
            for k, v in frame.f_locals.items()
            if k not in self.init_lines
        }

        data = {
            "event": event,
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno - self.line_offset,
            "locals": locals_filtered,
            "call_stack": list(self.call_stack),
            **extra
        }

        data = self.serialize_json(data)
        self.send_json(data)

    def send_json(self, data):
        payload = json.dumps(data).encode("utf-8")
        length = len(payload)
        header = struct.pack("!I", length)
        self.sock.sendall(header + payload)

    def user_line(self, frame):
        self.frame = frame
        self._update_top_frame_line(frame)

        self.send("line", frame)

        while not self.command_queue.empty():
            self.command_queue.get_nowait()

        self.wait_for_command()

    def user_call(self, frame, args):
        self.frame = frame
        self.call_stack.append(self._frame_info(frame))
        self.send("call", frame, args=args)

    def user_return(self, frame, retval):
        self.frame = frame
        if self.call_stack:
            self.call_stack.pop()
        self.send("return", frame, retval=retval)

    def user_exception(self, frame, exc_info):
        self.send("exception", frame, exc=exc_info)
        self.set_continue()

    def wait_for_command(self):
        # blocking
        command = self.command_queue.get()
        if command == "step_into":
            self.set_step()
        elif command == "next_line":
            self.set_next(self.frame)
        elif command == "step_out":
            self.set_return(self.frame)
        elif command == "continue":
            self.set_continue()

    def send_command(self, cmd):
        self.command_queue.put(cmd)

    def serialize_json(self, data):
        data['locals'].pop('__loader__', None)
        data['locals'].pop('__builtins__', None)
        data['locals'].pop('bdb', None)
        data['locals'].pop('Debugger', None)
        data['locals'].pop('debugger', None)
        data['locals'].pop('source', None)
        try:
            json_data = json.dumps(data, default=str, indent=2) 
        except Exception:
            json_data = {}
        return json_data


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

    dbg = Debugger(sock=None, line_offset=first_line)

    # Parse breakpoints
    for bp in breakpoints.split(","):
        if bp.strip():
            try:
                bp_file, bp_line = bp.split(":")
                dbg.set_break(bp_file.strip(), int(bp_line))
            except ValueError:
                print(f"Invalid breakpoint format: {bp}", flush=True)

    if WORK_DIR is not None:
        os.chdir(WORK_DIR)

    code_str = "import plask\n" + ("\n" * (first_line - 2)) + manager.script
    code = compile(code_str, script_path, "exec")
    print("[DEBUGGER]: Loading and compilation finished", flush=True)

    HOST = "127.0.0.1"

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((HOST, PORT) if PORT is not None else (HOST, 0))
        s.listen()
        PORT = s.getsockname()[1]
        print(f"[DEBUGGER]: Started socket on: {HOST}:{PORT}", flush=True)

        conn, addr = s.accept()
        try:
            print(f"[DEBUGGER]: Connected by {addr}", flush=True)
            dbg.sock = conn

            # Start debugger in a separate thread
            dbg_thread = threading.Thread(target=lambda: dbg.run(code))
            dbg_thread.start()

            buffer = b""
            while True:
                if not dbg_thread.is_alive():
                    print("[DEBUGGER]: Program finished, exiting.", flush=True)
                    break

                try:
                    data = conn.recv(1024)
                except ConnectionResetError:
                    print("[DEBUGGER]: Connection closed by client.", flush=True)
                    break
                except Exception as e:
                    print(f"[DEBUGGER]: Socket error: {e}", flush=True)
                    break

                if not data:
                    continue

                buffer += data
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.decode("utf-8").strip()
                    if line == "CONTINUE":
                        dbg.send_command("continue")
                    elif line == "NEXT_LINE":
                        dbg.send_command("next_line")
                    elif line == "STEP_INTO":
                        dbg.send_command("step_into")
                    elif line == "STEP_OUT":
                        dbg.send_command("step_out")
                    elif line == "STOP":
                        print("[DEBUGGER]: Stop command received, exiting.", flush=True)
                        dbg_thread.join(timeout=1)
                        sys.exit()

            dbg_thread.join()

        finally:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except:
                pass
            conn.close()

    finally:
        s.close()
