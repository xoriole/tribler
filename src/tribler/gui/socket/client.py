from PyQt5.QtCore import QObject
from PyQt5.QtNetwork import QLocalSocket, QLocalServer

from tribler.core.components.gui_socket.interface import SocketServer, SocketClient


class GUISocketClient(QObject, SocketClient):

    def __init__(self, socket_id: str):
        super().__init__()
        self.socket_id = socket_id

        self.local_socket = None
        self.is_connected = False

    def id(self):
        return self.socket_id

    def connect(self):
        self.local_socket = QLocalSocket()
        self.local_socket.connectToServer(self._id)

        if self.local_socket.waitForConnected():
            self.is_connected = True

        error = self.local_socket.error()
        if error == QLocalSocket.ConnectionRefusedError:
            self.logger.info('Received QLocalSocket.ConnectionRefusedError; removing server.')
            QLocalServer.removeServer(self.socket_id)

    def disconnect(self):
        if self.local_socket:
            self.local_socket.disconnectFromServer()

    def reconnect(self): ...

    def send_event(self, event: str): ...

    def send_info(self, info: dict): ...

    def send_data(self, data: bytes): ...

