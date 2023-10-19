# Copied and modified from http://stackoverflow.com/a/12712362/605356

import logging
import sys
from typing import Optional

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QApplication

from tribler.gui.socket.client import GUISocketClient
from tribler.gui.socket.server import GUISocketServer
from tribler.gui.tribler_window import TriblerWindow
from tribler.gui.utilities import connect


class QtSingleApplication(QApplication):
    """
    This class makes sure that we can only start one Tribler application.
    When a user tries to open a second Tribler instance, the current active one will be brought to front.
    """

    message_received = pyqtSignal(str)

    def __init__(self, win_id: str, start_local_server: bool, *argv):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info(f'Start Tribler application. Win id: "{win_id}". '
                         f'Sys argv: "{sys.argv}"')

        QApplication.__init__(self, *argv)
        self.tribler_window: Optional[TriblerWindow] = None
        self._id = win_id

        self.local_socket: Optional[GUISocketClient] = None
        self.local_server: Optional[GUISocketServer] = None

        # Is there another instance running?
        self.client_socket = GUISocketClient(self._id)
        self.client_socket.connect()
        if self.client_socket.is_connected:
            self.connected_to_previous_instance = True
        elif start_local_server:
            self.local_server = GUISocketServer(self._id)
            self.local_server.listen()
            connect(self.local_server.message_received, self.on_message_received)

    def get_id(self):
        return self._id

    def send_message(self, msg):
        return self.client_socket.send_message(msg)

    def on_message_received(self, msg):
        print(f"on message received: {msg}")
        sender = self.local_server.sender()
        print(f"sender: {sender}")
        self.message_received.emit(msg)
