import logging

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtNetwork import QLocalServer

from tribler.core.components.gui_socket.interface import SocketServer
from tribler.gui.socket.connection import ClientConnection
from tribler.gui.utilities import connect


class GUISocketServer(QObject, SocketServer):
    message_received = pyqtSignal(str)

    def __init__(self, socket_id: str):
        self.logger = logging.getLogger(self.__class__.__name__)
        super().__init__()
        self.socket_id = socket_id
        self.local_server = None
        self.client_connections = []

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
        self.client_connections.append(client_socket)

    def on_message_received(self, msg):
        self.message_received.emit(msg)

    def on_client_disconnected(self):
        pass

    def on_received_message(self, message: str):
        pass

    def on_received_event(self, event: bytes):
        pass

    def on_received_magnet_link(self, magnet_link: bytes):
        pass

    def on_received_file_path(self, file_path: bytes):
        pass

    def on_heart_beat(self):
        pass
#
#
# class ClientConnection(QObject):
#
#     message_received = pyqtSignal(str)
#
#     def __init__(self, socket: QLocalSocket):
#         self.logger = logging.getLogger(self.__class__.__name__)
#         super().__init__()
#         self.socket = socket
#         self.socket_stream = QTextStream(self.socket)
#         self.socket_stream.setCodec('UTF-8')
#
#         connect(self.socket.readyRead, self._on_ready_read)
#         connect(self.socket.connected, self.on_connected)
#         connect(self.socket.disconnected, self.on_disconnected)
#
#     def on_disconnected(self):
#         print("Socket disconnected")
#
#     def on_connected(self):
#         print(f"socket connected: {self.socket.objectName()}")
#
#     def _on_ready_read(self):
#         while True:
#             msg = self.socket_stream.readLine()
#             if not msg:
#                 break
#             self.logger.info(f'ClientSocket: A message received via the local socket from {self.socket.objectName()}: {msg}')
#             self.message_received.emit(msg)
