import logging

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtNetwork import QLocalServer

from tribler.core.components.gui_socket.interface import SocketServer
from tribler.gui.socket.connection import ClientConnection
from tribler.gui.socket.protocol_server import ProtocolServer
from tribler.gui.utilities import connect


class GUISocketServer(QObject, SocketServer):
    message_received = pyqtSignal(str)

    def __init__(self, socket_id: str):
        self.logger = logging.getLogger(self.__class__.__name__)
        super().__init__()
        self.socket_id = socket_id
        self.local_server = None
        self.connections = []

        self.protocol_server = ProtocolServer(self)

    def listen(self):
        self.local_server = QLocalServer()
        self.local_server.listen(self.socket_id)
        connect(self.local_server.newConnection, self.on_client_connected)

    def on_client_connected(self):
        socket = self.local_server.nextPendingConnection()
        if not socket:
            return

        client_socket = ClientConnection(socket)
        connect(client_socket.message_received, self.on_message_received)
        self.connections.append(client_socket)

    def on_message_received(self, msg):
        self.message_received.emit(msg)
        self.protocol_server.handle_message(msg)
