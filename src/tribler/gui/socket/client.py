import logging

from PyQt5.QtCore import QObject, QTextStream
from PyQt5.QtNetwork import QLocalSocket, QLocalServer

from tribler.core.components.gui_socket.interface import SocketServer, SocketClient


class GUISocketClient(QObject, SocketClient):

    def __init__(self, socket_id: str):
        self.logger = logging.getLogger(self.__class__.__name__)
        super().__init__()
        self.socket_id = socket_id

        self.local_socket = None
        self.is_connected = False
        self._stream_to_running_app = None

    def id(self):
        return self.socket_id

    def connect(self):
        self.local_socket = QLocalSocket()
        self.local_socket.connectToServer(self.socket_id)

        if self.local_socket.waitForConnected():
            self.is_connected = True

        error = self.local_socket.error()
        if error == QLocalSocket.ConnectionRefusedError:
            self.logger.info('Received QLocalSocket.ConnectionRefusedError; removing server.')
            QLocalServer.removeServer(self.socket_id)

        self._stream_to_running_app = QTextStream(self.local_socket)
        self._stream_to_running_app.setCodec('UTF-8')

    def disconnect(self):
        if self.local_socket:
            self.local_socket.disconnectFromServer()

    def send_message(self, msg):
        self.logger.info(f'Send message: {msg}')
        if not self._stream_to_running_app:
            return False

        self._stream_to_running_app << msg << '\n'  # pylint: disable=pointless-statement

        self._stream_to_running_app.flush()
        return self.local_socket.waitForBytesWritten()

    def reconnect(self): ...

    def send_event(self, event: str): ...

    def send_info(self, info: dict): ...

    def send_data(self, data: bytes): ...

