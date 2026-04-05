import bdb
import json
import sys
import threading
import queue
import socket 
import struct 
import os

import plask

from stack_manager import StackManager

class Debugger(bdb.Bdb):
    def __init__(self, sock, line_offset=0):
        super().__init__()
        self.command_queue = queue.Queue()
        self.frame = None
        self.sock = sock
        
        self.stack_manager = StackManager(__file__)
        self.init_lines = None
        self.line_offset = line_offset
        self._stop_requested = False

        self.watch_list = []

    def run(self, cmd, globals=None, locals=None):
        self.set_step()
        super().run(cmd, globals, locals)

    def stop(self):
        self._stop_requested = True
        self.set_quit()

    def _frame_info(self, frame):
        return {
            "function": frame.f_code.co_name,
            "file": os.path.relpath(frame.f_code.co_filename),
            "line": frame.f_lineno,
            "local_vars": list(frame.f_locals.items()),
        }
    
    def _filter_locals(self, f_locals):
        # TODO: Try setting the ignored vars form the config class: https://docs.plask.app/api/plask/plask.config
        if self.init_lines is None:
            self.init_lines = dict(f_locals)

        return {
            k: v
            for k, v in f_locals.items()
            if k not in self.init_lines
        }

    def send(self, event, frame, **extra):
        self.frame = frame
        locals_filtered = self._filter_locals(frame.f_locals)
        stack_list = list(self.stack_manager.get_stack())

        eval_dict = {}
        for w in self.watch_list:
            eval_dict[w] = self.evaluate_expression(w)

        for f in stack_list:
            f['locals'] = self._filter_locals(f['locals'])

        data = {
            "event": event,
            "file": frame.f_code.co_filename,
            "line": frame.f_lineno - self.line_offset,
            "locals": locals_filtered,
            "call_stack": stack_list,
            "watch_list": eval_dict,
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
        if self._stop_requested:
            raise bdb.BdbQuit
        self.frame = frame
        self.stack_manager.on_line(frame)
        self.stack_manager.rebuild_from_frame(frame)

        self.send("line", frame)

        while not self.command_queue.empty():
            self.command_queue.get_nowait()

        self.wait_for_command()

    def user_call(self, frame, args):
        self.stack_manager.on_call(frame)
        self.send("call", frame, args=args)

    def user_return(self, frame, retval):
        self.stack_manager.on_return(frame)
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

    def evaluate_expression(self, expr: str):
        try:
            return eval(expr, self.frame.f_globals, self.frame.f_locals)
        except Exception as e:
            return f"<Error: {e.__class__.__name__}: {e}>"

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

def run_server(dbg, code, HOST, PORT):
    dbg_thread = None
    conn = None

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        s.bind((HOST, PORT) if PORT is not None else (HOST, 0))
        s.listen()

        PORT = s.getsockname()[1]
        print(f"[DEBUGGER]: Started socket on: {HOST}:{PORT}", flush=True)

        try:
            conn, addr = s.accept()
            print(f"[DEBUGGER]: Connected by {addr}", flush=True)

            dbg.sock = conn

            def run_dbg():
                dbg.run(code)

            dbg_thread = threading.Thread(target=run_dbg, daemon=True)
            dbg_thread.start()

            buffer = b""

            while True:
                if dbg_thread and not dbg_thread.is_alive():
                    print("[DEBUGGER]: Program finished, exiting.", flush=True)
                    break

                try:
                    data = conn.recv(1024)
                except ConnectionResetError:
                    print("[DEBUGGER]: Connection reset by client.", flush=True)
                    break
                except OSError as e:
                    print(f"[DEBUGGER]: Socket error: {e}", flush=True)
                    break

                if not data:
                    print("[DEBUGGER]: Client disconnected.", flush=True)
                    break

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
                    elif line.startswith("WATCHED:"):
                        expr_list_str = line[len("WATCHED:"):]
                        try:
                            exprs = json.loads(expr_list_str)
                            dbg.watch_list = exprs
                        except Exception as e:
                            print("Invalid watch list:", e, flush=True)
                    elif line == "STOP":
                        print("[DEBUGGER]: Stop command received.", flush=True)
                        return

        finally:
            if dbg_thread and dbg_thread.is_alive():
                dbg.stop()
                dbg_thread.join(timeout=2)

            if conn:
                try:
                    conn.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                conn.close()

    print("[DEBUGGER]: Successfully exited")

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

    run_server(dbg, code, HOST, PORT)
