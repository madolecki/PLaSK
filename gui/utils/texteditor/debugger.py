from ...qt.QtWidgets import *
from ...qt.QtCore import Qt, QThread
from ...qt import QtSignal
from ...qt.QtGui import QColor, QIcon
from ...utils.config import CONFIG
import socket
import json
import struct
import time
from datetime import datetime


class PersistentSocketThread(QThread):
    vars_received = QtSignal(dict)
    connected_ok = QtSignal()
    error = QtSignal(str)
    closed = QtSignal()

    stack_received = QtSignal(list)

    send_command_signal = QtSignal(bytes)

    def __init__(self, host, port):
        super().__init__()
        self.host = host
        self.port = port
        self.socket = None
        self.running = True
        self.connected = False

        self.send_queue = []
        self.send_command_signal.connect(self.enqueue_command)

    def enqueue_command(self, cmd: bytes):
        self.send_queue.append(cmd)

    def connect_socket(self, retries=5, delay=0.5):
        attempt = 0
        while attempt < retries and self.running:
            try:
                self.socket = socket.create_connection((self.host, self.port), timeout=3)
                self.socket.settimeout(0.25)
                self.connected = True
                self.connected_ok.emit()
                return
            except Exception as e:
                attempt += 1
                if attempt < retries:
                    time.sleep(delay)
                else:
                    self.error.emit(f"Connection failed after {retries} attempts: {e}")
                    self.connected = False
                    return

    def run(self):
        self.connect_socket(retries=CONFIG['debugger/connection_retires'],delay=CONFIG['debugger/connection_retry_delay'])
        if not self.connected:
            return

        while self.running:
            # Send queued commands
            if self.send_queue:
                cmd = self.send_queue.pop(0)
                try:
                    self.socket.sendall(cmd)
                except Exception as e:
                    self.error.emit(f"Send error: {e}")
                    break

            # Try receiving a JSON response
            try:
                data = self.recv_json(self.socket)
                if data:
                    try:
                        vars_dict = json.loads(data)
                        if "locals" in vars_dict:
                            self.vars_received.emit(vars_dict)

                        if "call_stack" in vars_dict:
                            self.stack_received.emit(vars_dict["call_stack"])
                            self.vars_received.emit(vars_dict)
                    except Exception as e:
                        self.error.emit(f"JSON decode error: {e}")

            except socket.timeout:
                pass
            except Exception as e:
                self.error.emit(f"Socket error: {e}")
                break

            time.sleep(0.01)

        try:
            if self.socket:
                self.socket.close()
        except:
            pass

        self.closed.emit()

    def recv_json(self, sock):
        def recv_all(sock, n):
            data = b""
            while len(data) < n:
                packet = sock.recv(n - len(data))
                if not packet:
                    raise ConnectionError("Socket closed")
                data += packet
            return data
        header = recv_all(sock, 4)
        (length,) = struct.unpack("!I", header)
        payload = recv_all(sock, length)
        return json.loads(payload.decode("utf-8"))

    def stop(self):
        self.running = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
                self.socket.close()
            except:
                pass

class DebuggerPanel(QDockWidget):
    current_line_signal = QtSignal(int)

    ask_breakpoints = QtSignal()
    received_breakpoints = QtSignal(set)

    def __init__(self, window_parent):
        super().__init__("Debugger", window_parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        container = QWidget()
        layout = QVBoxLayout(container)

        # --- Connection Info ---
        config_layout = QHBoxLayout()
        config_layout.addWidget(QLabel("Host:"))
        self.host_label = QLabel("127.0.0.1")
        config_layout.addWidget(self.host_label)

        config_layout.addWidget(QLabel("Port:"))
        self.port_label = QLabel(str(CONFIG['launcher_debug/port']))
        config_layout.addWidget(self.port_label)

        # --- Buttons ---
        button_layout = QHBoxLayout()
        style = self.style()

        #self.connect_button = QPushButton()
        #self.connect_button.setIcon(style.standardIcon(QStyle.SP_DialogOpenButton))
        #self.connect_button.clicked.connect(self.connect_debugger)
        #self.connect_button.setToolTip("Connect to the debugger backend.")

        self.continue_button = QPushButton()
        self.continue_button.setIcon(QIcon("gui/utils/texteditor/play.svg"))
        self.continue_button.clicked.connect(lambda: self.send_cmd(b"CONTINUE\n"))
        self.continue_button.setEnabled(False)
        self.continue_button.setToolTip("Continue execution until the next breakpoint.")

        self.step_line_button = QPushButton()
        self.step_line_button.setIcon(QIcon("gui/utils/texteditor/step.svg"))
        self.step_line_button.clicked.connect(lambda: self.send_cmd(b"NEXT_LINE\n"))
        self.step_line_button.setEnabled(False)
        self.step_line_button.setToolTip("Execute the next line of code.")

        self.step_into_button = QPushButton()
        self.step_into_button.setIcon(QIcon("gui/utils/texteditor/step_in.svg"))
        self.step_into_button.clicked.connect(lambda: self.send_cmd(b"STEP_INTO\n"))
        self.step_into_button.setEnabled(False)
        self.step_into_button.setToolTip("Step into the next function call.")

        self.step_out_button = QPushButton()
        self.step_out_button.setIcon(QIcon("gui/utils/texteditor/step_out.svg"))
        self.step_out_button.clicked.connect(lambda: self.send_cmd(b"STEP_OUT\n"))
        self.step_out_button.setEnabled(False)
        self.step_out_button.setToolTip("Step out of the current function.")

        self.stop_button = QPushButton()
        self.stop_button.setIcon(style.standardIcon(QStyle.SP_MediaStop))
        self.stop_button.clicked.connect(self.stop_debugger)
        self.stop_button.setEnabled(False)
        self.stop_button.setToolTip("Stop the debugger and disconnect from the program.")

        # Add buttons to layout
        for btn in [
            #self.connect_button,
            self.continue_button,
            self.step_line_button,
            self.step_into_button,
            self.step_out_button,
            self.stop_button
        ]:
            button_layout.addWidget(btn)

        # --- Panel for Variables ---
        self.panel_widget = QTreeWidget()
        self.panel_widget.setHeaderLabels(["Variable", "Value"])
        self.panel_widget.setColumnWidth(0, 200)
        self.panel_widget.setToolTip("Shows all current local variables and their values.")

        # --- Panel for Call Stack ---
        self.call_stack_widget = QTreeWidget()
        self.call_stack_widget.setHeaderLabels(["Function", "File", "Line"])
        self.call_stack_widget.setColumnCount(3)
        self.call_stack_widget.setColumnWidth(0, 60)
        self.call_stack_widget.setColumnWidth(1, 120)
        self.call_stack_widget.setColumnWidth(2, 20)
        self.call_stack_widget.setAlternatingRowColors(True)
        self.call_stack_widget.setRootIsDecorated(True)
        self.call_stack_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.call_stack_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.call_stack_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.call_stack_widget.setToolTip("Shows the current call stack and frame-local variables.")

        # --- Layout assembly ---
        layout.addLayout(config_layout)
        layout.addLayout(button_layout)
        layout.addWidget(QLabel("Variables:"))
        layout.addWidget(self.panel_widget)
        layout.addWidget(QLabel("Call Stack:"))
        layout.addWidget(self.call_stack_widget)
        layout.setContentsMargins(4, 4, 4, 4)

        self.setWidget(container)
        self.setVisible(False)

        if window_parent and hasattr(window_parent, "addDockWidget"):
            window_parent.addDockWidget(Qt.RightDockWidgetArea, self)

        # Thread ref
        self.socket_thread = None
        self.breakpoints = set()


    def add_panel_message(self, panel, text, msg_type="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        item = QTreeWidgetItem([timestamp, text])
        
        color_map = {
            "error": QColor("red"),
            "warn": QColor("orange"),
            "info": QColor("blue"),
            "debug": QColor("gray")
        }
        color = color_map.get(msg_type, QColor("black"))
        item.setForeground(1, color)
        
        panel.addTopLevelItem(item)
        panel.scrollToItem(item)

    def get_breakpoint_lines(self):
        self.request_breakpoints()
        return self.breakpoints

    def request_breakpoints(self):
        self.ask_breakpoints.emit()

    def recieve_breakpoints(self, breakpoints):
        self.breakpoints = breakpoints

    def toggle_visibility(self):
        self.setVisible(not self.isVisible())

    def connect_debugger(self):
        host = "127.0.0.1"
        port = CONFIG['launcher_debug/port']

        if self.socket_thread:
            self.add_panel_message(self.panel_widget, "Already connected.", "info")
            return

        self.add_panel_message(self.panel_widget, "Connecting...", "info")

        self.socket_thread = PersistentSocketThread(host, port)
        self.socket_thread.connected_ok.connect(self.on_connected)
        self.socket_thread.vars_received.connect(self.update_vars)
        self.socket_thread.error.connect(self.show_error)
        self.socket_thread.closed.connect(self.on_closed)
        self.socket_thread.stack_received.connect(self.update_call_stack)
        self.socket_thread.start()

    def send_cmd(self, cmd: bytes):
        if self.socket_thread and self.socket_thread.connected:
            self.socket_thread.send_command_signal.emit(cmd)
        else:
            self.add_panel_message(self.panel_widget, "Not connected", "warn")

    def stop_debugger(self):
        if self.socket_thread:
            self.send_cmd(b"STOP\n")
            self.socket_thread.stop()

    def on_connected(self):
        self.panel_widget.clear()
        self.add_panel_message(self.panel_widget, "Connected to debugger.", "info")
        #self.connect_button.setEnabled(False)

        for btn in [
            self.continue_button,
            self.step_line_button,
            self.step_into_button,
            self.step_out_button,
            self.stop_button
        ]:
            btn.setEnabled(True)

        self.send_cmd(b"CONTINUE\n")

    def add_variable_item(self, parent, name, value, max_str_len=100, max_items=50):
        # Truncate long strings for display
        display_value = value
        if isinstance(value, str) and len(value) > max_str_len:
            display_value = value[:max_str_len] + "... (truncated)"
        
        # Create the current tree item
        if isinstance(value, dict):
            item = QTreeWidgetItem([str(name), f"dict ({len(value)})"])
            item.setToolTip(1, str(value))
            item.setForeground(1, QColor("darkGreen"))
            # Add children for each key/value
            for i, key in enumerate(sorted(value.keys())):
                if i >= max_items:
                    QTreeWidgetItem(item, [f"... ({len(value)-max_items} more items)", ""])
                    break
                self.add_variable_item(item, key, value[key], max_str_len, max_items)

        elif isinstance(value, (list, tuple, set)):
            type_name = type(value).__name__
            item = QTreeWidgetItem([str(name), f"{type_name} ({len(value)})"])
            item.setToolTip(1, str(value))
            item.setForeground(1, QColor("darkBlue"))
            # Add children for each element
            for i, v in enumerate(value):
                if i >= max_items:
                    QTreeWidgetItem(item, [f"... ({len(value)-max_items} more)", ""])
                    break
                self.add_variable_item(item, f"[{i}]", v, max_str_len, max_items)

        else:
            # Simple value
            item = QTreeWidgetItem([str(name), repr(display_value)])
            item.setToolTip(1, str(value))
            # Color coding
            if isinstance(value, (int, float, complex)):
                item.setForeground(1, QColor("blue"))
            elif isinstance(value, str):
                item.setForeground(1, QColor("darkRed"))
            elif isinstance(value, bool):
                item.setForeground(1, QColor("darkMagenta"))
            elif value is None:
                item.setForeground(1, QColor("gray"))

        # Add to parent
        if isinstance(parent, QTreeWidget):
            parent.addTopLevelItem(item)
        else:
            parent.addChild(item)

        # Optionally expand top-level items
        if isinstance(parent, QTreeWidget):
            item.setExpanded(True)

    def format_var(self, name, value, indent=0, max_str_len=100, max_items=10):
            spacer = "  " * indent

            # Truncate long strings
            if isinstance(value, str) and len(value) > max_str_len:
                value = value[:max_str_len] + "... (truncated)"

            # Limit length of containers
            if isinstance(value, dict):
                lines = [f"{spacer}{name}: dict{{"]
                for i, k in enumerate(sorted(value.keys())):
                    if i >= max_items:
                        lines.append(f"{spacer}  ... ({len(value) - max_items} more items)")
                        break
                    lines.append(self.format_var(k, value[k], indent + 1))
                lines.append(f"{spacer}}}")
                return "\n".join(lines)
            elif isinstance(value, (list, tuple, set)):
                type_name = type(value).__name__
                lines = [f"{spacer}{name}: {type_name}["]
                for i, v in enumerate(value):
                    if i >= max_items:
                        lines.append(f"{spacer}  ... ({len(value) - max_items} more items)")
                        break
                    lines.append(self.format_var(f"[{i}]", v, indent + 1))
                lines.append(f"{spacer}]")
                return "\n".join(lines)
            else:
                return f"{spacer}{name}: {repr(value)}"

    def update_vars(self, vars_data):
        self.panel_widget.clear()
        locals_dict = vars_data.get("locals", {})
        for key, value in locals_dict.items():
            self.add_variable_item(self.panel_widget, key, value)

        line = int(vars_data["line"])
        self.current_line_signal.emit(line)


    def update_call_stack(self, stack_data):
        self.call_stack_widget.clear()

        for frame in stack_data:
            func = frame.get("function", "?")
            file = frame.get("file", "?")
            line = frame.get("line", "?")
            locals_dict = frame.get("locals", {})

            parts = file.replace("\\", "/").split("/")
            short_file = "/".join(parts[-3:]) if len(parts) > 3 else file

            top = QTreeWidgetItem([
                func,
                short_file,
                str(line)
            ])
            self.call_stack_widget.addTopLevelItem(top)

            for key, value in locals_dict.items():
                self.add_variable_item(top, key, value)

            top.setExpanded(False)


    def show_error(self, msg):
        self.add_panel_message(self.panel_widget, msg, "error")

    def on_closed(self):
        self.panel_widget.clear()
        self.add_panel_message(self.panel_widget, "Debugger connection closed.", "info")
        #self.connect_button.setEnabled(True)

        for btn in [
            self.continue_button,
            self.step_line_button,
            self.step_into_button,
            self.step_out_button,
            self.stop_button
        ]:
            btn.setEnabled(False)

        self.current_line_signal.emit(-1)
        self.socket_thread.stop()
        self.socket_thread = None

