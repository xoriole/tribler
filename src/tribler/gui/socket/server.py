import logging

from PyQt5.QtCore import QObject, pyqtSignal, QByteArray
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
        connect(self.local_server.newConnection, self.handle_new_connection)

    def read_client_data(self):
        client_socket = self.local_server.sender()
        if client_socket not in self.connections:
            return

        while True:
            data: QByteArray = client_socket.readLine()
            if not data:
                break

            data: bytes = data.data().strip()

            self.protocol_server.handle_data(data)
            self.message_received.emit(data.decode('utf-8'))

    def handle_new_connection(self):
        client_socket = self.local_server.nextPendingConnection()
        if not client_socket:
            return

        # Store the client socket in the connections list
        self.connections.append(client_socket)

        # Connect the socket's disconnected signal to handle its removal
        client_socket.disconnected.connect(self.remove_connection)

        # Read the data
        client_socket.readyRead.connect(self.read_client_data)

    # def on_message_received(self, msg):
    #     self.message_received.emit(msg)
    #     self.protocol_server.handle_message(msg)

    def remove_connection(self):
        # Remove the socket from the connections list
        client_socket = self.local_server.sender()
        if client_socket in self.connections:
            self.connections.remove(client_socket)
            client_socket.deleteLater()
