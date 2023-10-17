import logging

from PyQt5.QtCore import QTextStream, pyqtSignal, QObject
from PyQt5.QtNetwork import QLocalSocket

from tribler.gui.utilities import connect


class ClientConnection(QObject):
    message_received = pyqtSignal(str)

    def __init__(self, socket: QLocalSocket):
        self.logger = logging.getLogger(self.__class__.__name__)
        super().__init__()
        self.socket = socket
        self.socket_stream = QTextStream(self.socket)
        self.socket_stream.setCodec('UTF-8')

        connect(self.socket.readyRead, self._on_ready_read)
        connect(self.socket.connected, self.on_connected)
        connect(self.socket.disconnected, self.on_disconnected)

    def on_disconnected(self):
        print("Socket disconnected")

    def on_connected(self):
        print(f"socket connected: {self.socket.objectName()}")

    def _on_ready_read(self):
        while True:
            msg = self.socket_stream.readLine()
            if not msg:
                break
            self.logger.info(f'ClientSocket: A message received via the local socket from {self.socket.objectName()}: {msg}')
            self.message_received.emit(msg)
