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
    connected_ok = QtSignal()
    error = QtSignal(str)
    closed = QtSignal()

    vars_received = QtSignal(dict)
    stack_received = QtSignal(list)
    watch_list_received = QtSignal(dict)

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
                        
                        if "watch_list" in vars_dict:
                            self.watch_list_received.emit(vars_dict["watch_list"])
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

        self.reconnect_button = QPushButton("Reconnect")
        self.reconnect_button.setToolTip("Reconnect to debugger backend.")
        self.reconnect_button.setEnabled(False) 
        self.reconnect_button.setVisible(False) 
        self.reconnect_button.clicked.connect(self.connect_debugger)

        # Add buttons to layout
        for btn in [
            self.continue_button,
            self.step_line_button,
            self.step_into_button,
            self.step_out_button,
            self.stop_button
        ]:
            button_layout.addWidget(btn)

        def make_section_header(title: str):
            btn = QPushButton(f"▼ {title}")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFlat(True)

            # Nice styling
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 4px 6px;
                    border: none;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
            """)

            btn.toggled.connect(
                lambda c, b=btn, t=title: b.setText(("▼ " if c else "▶ ") + t)
            )

            return btn


        # --- Panel for Variables ---
        self.panel_widget = QTreeWidget()
        self.panel_widget.setHeaderLabels(["Variable", "Value"])
        self.panel_widget.setColumnWidth(0, 200)
        self.panel_widget.setToolTip("Shows all current local variables and their values.")

        vars_section = self.CollapsibleSection("Variables", self.panel_widget)


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

        stack_section = self.CollapsibleSection("Call Stack", self.call_stack_widget)


        # --- Panel for Watch Expressions ---
        self.watch_tree = QTreeWidget()
        self.watch_tree.setHeaderLabels(["Expression", "Value"])
        self.watch_tree.setColumnWidth(0, 250)
        self.watch_tree.setAlternatingRowColors(True)
        self.watch_tree.setRootIsDecorated(False)
        self.watch_tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.watch_tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.watch_tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.watch_tree.setToolTip("Auto-evaluated watch expressions.")

        self.watch_input = QLineEdit()
        self.watch_input.setPlaceholderText("Enter watch expression…")

        self.watch_add_button = QPushButton("Add")
        self.watch_add_button.clicked.connect(self.add_expression)

        watch_container = QWidget()
        watch_layout = QVBoxLayout(watch_container)
        watch_layout.setContentsMargins(0, 0, 0, 0)

        watch_layout.addWidget(self.watch_tree)

        watch_input_layout = QHBoxLayout()
        watch_input_layout.addWidget(self.watch_input)
        watch_input_layout.addWidget(self.watch_add_button)

        watch_layout.addLayout(watch_input_layout)

        self.watch_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.watch_tree.customContextMenuRequested.connect(self.open_context_menu)

        watch_section = self.CollapsibleSection("Watch Expressions", watch_container)

        # --- Layout assembly ---

        self.sections = [vars_section, stack_section, watch_section]

        for section in self.sections:
            section.toggled.connect(self.update_section_stretch)

        sections_container = QWidget()
        sections_layout = QVBoxLayout(sections_container)
        sections_layout.setContentsMargins(0, 0, 0, 0)
        sections_layout.setSpacing(4)

        sections_layout.addWidget(vars_section)
        sections_layout.addWidget(stack_section)
        sections_layout.addWidget(watch_section)
        sections_layout.addStretch(1)


        layout.addLayout(config_layout)
        layout.addLayout(button_layout)
        layout.addWidget(self.reconnect_button)
        layout.addWidget(sections_container)
        layout.setContentsMargins(4, 4, 4, 4)

        self.setWidget(container)
        self.setVisible(False)

        if window_parent and hasattr(window_parent, "addDockWidget"):
            window_parent.addDockWidget(Qt.RightDockWidgetArea, self)

        # Thread ref
        self.socket_thread = None
        self.breakpoints = set()

    class CollapsibleSection(QWidget):
        toggled = QtSignal()
        def __init__(self, title: str, content: QWidget):
            super().__init__()

            self.toggle_btn = QPushButton(f"▼ {title}")
            self.toggle_btn.setCheckable(True)
            self.toggle_btn.setChecked(True)
            self.toggle_btn.setFlat(True)

            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 4px 6px;
                    border: none;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #e0e0e0;
                }
            """)

            self.content = content

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            layout.addWidget(self.toggle_btn)
            layout.addWidget(self.content)

            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

            self.toggle_btn.toggled.connect(self.on_toggle)

        def on_toggle(self, checked):
            title = self.toggle_btn.text()[2:]
            self.toggle_btn.setText(("▼ " if checked else "▶ ") + title)
            self.content.setVisible(checked)
            self.updateGeometry()
            self.toggled.emit()
            if self.parentWidget():
                self.parentWidget().updateGeometry()

    def update_section_stretch(self):
        expanded = [s for s in self.sections if s.toggle_btn.isChecked()]

        layout = self.sections[0].parentWidget().layout()

        for i in range(layout.count()):
            layout.setStretch(i, 0)

        if len(expanded) == 0:
            layout.setStretch(layout.count() - 1, 1)
            return

        for i, section in enumerate(self.sections):
            if section in expanded:
                layout.setStretch(i, 1)
            else:
                layout.setStretch(i, 0)

        layout.setStretch(layout.count() - 1, 0)


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

        self.add_panel_message(self.panel_widget, "Connecting...", "info")

        self.socket_thread = PersistentSocketThread(host, port)
        self.socket_thread.connected_ok.connect(self.on_connected)
        self.socket_thread.vars_received.connect(self.update_vars)
        self.socket_thread.error.connect(self.show_error)
        self.socket_thread.closed.connect(self.on_closed)
        self.socket_thread.stack_received.connect(self.update_call_stack)
        self.socket_thread.watch_list_received.connect(self.update_watch_list)
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
        self.reconnect_button.setVisible(False)
        self.reconnect_button.setEnabled(False)

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

    def add_expression(self):
        expr = self.watch_input.text()
        self.watch_tree.addTopLevelItem(
            QTreeWidgetItem([
                expr,
                None
            ])
        )
        self.update_expressions()

    def edit_expression(self, item):
        old_expr = item.text(0)
        new_expr, ok = QInputDialog.getText(
            self, "Edit Watch Expression", "Expression:", text=old_expr
        )

        if ok and new_expr:
            item.setText(0, new_expr)
            self.update_expressions()
        self.update_expressions()

    def delete_expression(self, item):
        index = self.watch_tree.indexOfTopLevelItem(item)
        self.watch_tree.takeTopLevelItem(index)
        #self.on_expression_removed(item)
        self.update_expressions()

    def _get_watch_expressions(self):
        return [
            self.watch_tree.topLevelItem(i).text(0)
            for i in range(self.watch_tree.topLevelItemCount())
        ]

    def update_expressions(self):
        expressions = self._get_watch_expressions()
        list_str = json.dumps(expressions)
        watched_str = f"WATCHED:{list_str}\n"
        self.send_cmd(watched_str.encode('utf-8'))

    def update_watch_list(self, values):
        for i in range(self.watch_tree.topLevelItemCount()):
                item = self.watch_tree.topLevelItem(i)
                expr = item.text(0)  # Column 0 = expression string
                
                if expr in values:
                    val = values[expr]
                    item.setText(1, str(val))  # Column 1 = value
                else:
                    item.setText(1, "<not available>")

    def open_context_menu(self, position):
        item = self.watch_tree.itemAt(position)
        if item is None:
            return

        menu = QMenu()

        edit_action = menu.addAction("Edit Expression")
        delete_action = menu.addAction("Delete Expression")

        action = menu.exec_(self.watch_tree.viewport().mapToGlobal(position))

        if action == edit_action:
            self.edit_expression(item)
        elif action == delete_action:
            self.delete_expression(item)

    def show_error(self, msg):
        self.add_panel_message(self.panel_widget, msg, "error")

        if self.socket_thread and not self.socket_thread.connected:
                self.reconnect_button.setVisible(True)
                self.reconnect_button.setEnabled(True)

    def on_closed(self):
        self.panel_widget.clear()
        self.add_panel_message(self.panel_widget, "Debugger connection closed.", "info")

        self.reconnect_button.setVisible(True)
        self.reconnect_button.setEnabled(True)

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

