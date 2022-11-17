import socket

import psutil
from PyQt5.QtCore import QObject, QTimer

from tribler.gui.utilities import connect

CHECK_INTERVAL_MS = 1000
MAX_PORTS_TO_CHECK = 10


class PortChecker(QObject):

    def __init__(self, base_port, callback):
        QObject.__init__(self, None)
        self.base_port = base_port
        self.callback = callback

        self.process_id = None
        self.checker_timer = None

    def setup_with_pid(self, pid):
        self.process_id = pid
        self.checker_timer = QTimer()
        self.checker_timer.setSingleShot(True)
        connect(self.checker_timer.timeout, self.on_timeout)
        self.checker_timer.start(CHECK_INTERVAL_MS)

    def on_timeout(self):
        detected_port = self.detected_port()
        if detected_port:
            self.checker_timer.stop()
            self.callback(detected_port)
        elif self.checker_timer:
            self.checker_timer.start(CHECK_INTERVAL_MS)

    def detected_port(self):
        if not self.process_id:
            return None

        try:
            process = psutil.Process(self.process_id)
        except psutil.NoSuchProcess:
            return None

        connections = process.connections(kind='inet4')
        candidate_ports = [connection.laddr.port for connection in connections
                           if self._is_connection_in_range(connection)]

        return min(candidate_ports) if candidate_ports else None

    def _is_connection_in_range(self, connection):
        return connection.laddr.ip == '127.0.0.1' \
               and connection.status == 'LISTEN' \
               and connection.type == socket.SocketKind.SOCK_STREAM \
               and 0 <= connection.laddr.port - self.base_port < MAX_PORTS_TO_CHECK
