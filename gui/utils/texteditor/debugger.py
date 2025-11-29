
from PySide6.QtWidgets import (
    QDockWidget, QListWidget, QVBoxLayout, QWidget,
    QPushButton, QHBoxLayout, QLineEdit, QLabel
)
from PySide6.QtCore import Qt, QThread, Signal
import socket
import json
import time


class PersistentSocketThread(QThread):
    vars_received = Signal(dict)
    connected_ok = Signal()
    error = Signal(str)
    closed = Signal()

    send_command_signal = Signal(bytes)

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

    def connect_socket(self):
        try:
            self.socket = socket.create_connection((self.host, self.port), timeout=3)
            self.socket.settimeout(0.25)
            self.connected = True
            self.connected_ok.emit()
        except Exception as e:
            self.error.emit(f"Connection failed: {e}")
            self.connected = False

    def run(self):
        self.connect_socket()
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
                data = self.socket.recv(65536)
                if data:
                    try:
                        vars_dict = json.loads(data.decode("utf-8"))
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

    def stop(self):
        self.running = False


class DebuggerPanel(QDockWidget):
    def __init__(self, window_parent):
        super().__init__("Debugger", window_parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        container = QWidget()
        layout = QVBoxLayout(container)

        config_layout = QHBoxLayout()

        self.host_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("5000")

        config_layout.addWidget(QLabel("Host:"))
        config_layout.addWidget(self.host_input)
        config_layout.addWidget(QLabel("Port:"))
        config_layout.addWidget(self.port_input)

        button_layout = QHBoxLayout()

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_debugger)

        self.next_break_button = QPushButton("Next Break")
        self.next_break_button.clicked.connect(lambda: self.send_cmd(b"NEXT\n"))
        self.next_break_button.setEnabled(False)

        self.next_line_button = QPushButton("Next Line")
        self.next_line_button.clicked.connect(lambda: self.send_cmd(b"STEP\n"))
        self.next_line_button.setEnabled(False)

        self.stop_button = QPushButton("Stop Debugger")
        self.stop_button.clicked.connect(self.stop_debugger)
        self.stop_button.setEnabled(False)

        button_layout.addWidget(self.connect_button)
        button_layout.addWidget(self.next_break_button)
        button_layout.addWidget(self.next_line_button)
        button_layout.addWidget(self.stop_button)

        self.panel_widget = QListWidget()

        layout.addLayout(config_layout)
        layout.addLayout(button_layout)
        layout.addWidget(self.panel_widget)
        layout.setContentsMargins(4, 4, 4, 4)

        self.setWidget(container)
        self.setVisible(False)

        # Add to parent window
        if window_parent and hasattr(window_parent, "addDockWidget"):
            window_parent.addDockWidget(Qt.RightDockWidgetArea, self)

        # Thread ref
        self.socket_thread: PersistentSocketThread | None = None

    def toggle_visibility(self):
        self.setVisible(not self.isVisible())

    def connect_debugger(self):
        host = self.host_input.text().strip()
        try:
            port = int(self.port_input.text())
        except ValueError:
            self.panel_widget.addItem("Error: Port must be an integer.")
            return

        if self.socket_thread:
            self.panel_widget.addItem("Already connected.")
            return

        self.panel_widget.addItem("Connecting...")

        self.socket_thread = PersistentSocketThread(host, port)
        self.socket_thread.connected_ok.connect(self.on_connected)
        self.socket_thread.vars_received.connect(self.update_vars)
        self.socket_thread.error.connect(self.show_error)
        self.socket_thread.closed.connect(self.on_closed)
        self.socket_thread.start()

    def send_cmd(self, cmd: bytes):
        if self.socket_thread and self.socket_thread.connected:
            self.socket_thread.send_command_signal.emit(cmd)
        else:
            self.panel_widget.addItem("Not connected.")

    def stop_debugger(self):
        if self.socket_thread:
            self.send_cmd(b"STOP\n")
            self.socket_thread.stop()

    def on_connected(self):
        self.panel_widget.addItem("Connected to debugger.")

        self.next_break_button.setEnabled(True)
        self.next_line_button.setEnabled(True)
        self.stop_button.setEnabled(True)

    def update_vars(self, vars_data):
        self.panel_widget.clear()
        for key, value in vars_data.items():
            pretty = json.dumps(value, indent=2)
            self.panel_widget.addItem(f"{key}:\n{pretty}")

    def show_error(self, msg):
        self.panel_widget.addItem(f"Error: {msg}")

    def on_closed(self):
        self.panel_widget.addItem("Debugger connection closed.")
        self.next_break_button.setEnabled(False)
        self.next_line_button.setEnabled(False)
        self.stop_button.setEnabled(False)

        self.socket_thread = None

