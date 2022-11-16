from PyQt5.QtCore import QObject, QTimer

from tribler.core.utilities.network_utils import NetworkUtils
from tribler.gui.utilities import connect

RECONNECT_INTERVAL_MS = 1000


class PortChecker(QObject):

    def __init__(self, process_id, base_port, callback):
        QObject.__init__(self, None)
        self.process_id = process_id
        self.base_port = base_port
        self.callback = callback
        self.core_port_checker = None

    def setup_core_port_checker(self):
        self.core_port_checker = QTimer()
        self.core_port_checker.setSingleShot(True)
        connect(self.core_port_checker.timeout, self.check_core_port_and_update_services)

    def schedule_core_port_checker(self):
        if not self.core_port_checker:
            self.setup_core_port_checker()
        self.core_port_checker.start(RECONNECT_INTERVAL_MS)

    def check_core_port_and_update_services(self):
        detected_port = self.detected_core_port()
        if detected_port:
            self.core_port_checker.stop()
            self.callback(detected_port)
        else:
            self.schedule_core_port_checker()

    def detected_core_port(self):
        if not self.process_id:
            return None
        return NetworkUtils().get_closest_process_port(self.process_id, self.api_port)
