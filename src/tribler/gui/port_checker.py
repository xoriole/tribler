import socket
from typing import Callable

import psutil
from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from tribler.gui.utilities import connect

CHECK_INTERVAL_MS = 1000
MAX_PORTS_TO_CHECK = 10


class PortChecker(QObject):
    """
    PortChecker finds the closest port of process given a base port.
    When it finds the closest port, it calls the success callback with the detected port.
    If it does not find the closest port within the range, it calls the timeout callback.

    port_checker = PortChecker(process_id, success_callback, timeout_callback)

    Raises: TimeoutError, NoProcessError
    """

    on_port_detected_signal = pyqtSignal(object)
    on_timeout_signal = pyqtSignal()

    def __init__(
            self,
            pid: int,
            base_port: int,
            success_callback: Callable[[int], None],
            timeout_callback: Callable[[], None],
            check_timeout_in_sec=120,
            check_interval_in_sec=1,
            max_ports_to_check=10
    ):
        QObject.__init__(self, None)
        self.process = self.get_process_from_pid(pid)
        self.base_port = base_port

        self.success_callback = success_callback
        self.timeout_callback = timeout_callback

        self.check_interval_in_sec = check_interval_in_sec
        self.check_timeout_in_sec = check_timeout_in_sec

        self.max_ports_to_check = max_ports_to_check

        self.detected_port = None

        self.checker_timer = None
        self.timeout_timer = None
        self._setup_timers()

    @staticmethod
    def get_process_from_pid(pid):
        try:
            return psutil.Process(pid)
        except psutil.NoSuchProcess:
            raise ValueError(f"Process[PID:{pid}] does not exist.")

    def _setup_timers(self):
        self.checker_timer = QTimer()
        self.checker_timer.setSingleShot(False)
        connect(self.checker_timer.timeout, self._check_ports)
        self.checker_timer.start(self.check_interval_in_sec * 1000)

        self.timeout_timer = QTimer()
        self.timeout_timer.setSingleShot(True)
        connect(self.timeout_timer.timeout, self._check_ports)
        self.timeout_timer.start(self.check_timeout_in_sec * 1000)

    def _stop_timers(self):
        if self.checker_timer:
            self.checker_timer.stop()
            self.checker_timer = None

        if self.timeout_timer:
            self.timeout_timer.stop()
            self.timeout_timer = None

    def _check_ports(self):
        self._detect_port_from_process()
        if self.detected_port:
            self._stop_timers()
            self.success_callback(self.detected_port)

    def _on_timeout(self):
        self._stop_timers()

        if not self.detected_port:
            self.timeout_callback()

    def _detect_port_from_process(self):
        def is_local_listening_connection_in_range(connection):
            return connection.laddr.ip == '127.0.0.1' \
                   and connection.status == 'LISTEN' \
                   and connection.type == socket.SocketKind.SOCK_STREAM \
                   and 0 <= connection.laddr.port - self.base_port < MAX_PORTS_TO_CHECK

        connections = self.process.connections(kind='inet4')
        candidate_ports = [connection.laddr.port for connection in connections
                           if is_local_listening_connection_in_range(connection)]
        if candidate_ports:
            self.detected_port = min(candidate_ports)
