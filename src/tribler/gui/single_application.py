# Copied and modified from http://stackoverflow.com/a/12712362/605356

import logging
import sys
from typing import Optional

from PyQt5.QtCore import QTextStream, pyqtSignal, QObject
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import QApplication

from tribler.gui.socket.socket_server import GUISocketServer
from tribler.gui.tribler_window import TriblerWindow
from tribler.gui.utilities import connect, disconnect


class QtSingleApplication(QApplication, GUISocketServer):
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

        self._stream_to_running_app = None

        self.local_socket = None
        self.socket_stream = None

        self.local_socket: Optional[QLocalSocket] = None
        self.local_server: Optional[QLocalServer] = None

        self.client_connections = []

        # Is there another instance running?
        self.connected_to_previous_instance = self.connect_to_existing_socket_server()
        if self.connected_to_previous_instance:
            self.setup_stream_to_running_app()
        elif start_local_server:
            self.setup_socket_server()

    def connect_to_existing_socket_server(self) -> bool:
        self.local_socket = QLocalSocket()
        self.local_socket.connectToServer(self._id)

        if self.local_socket.waitForConnected():
            print(f"name of socket: {self.local_socket.serverName()}, objectName: {self.local_socket.objectName()}")
            return True

        error = self.local_socket.error()
        self.logger.info(f'No running instances (socket error: {error})')
        if error == QLocalSocket.ConnectionRefusedError:
            self.logger.info('Received QLocalSocket.ConnectionRefusedError; removing server.')
            self.cleanup_crashed_server()

        return False

    def setup_socket_server(self):
        self.local_server = QLocalServer()
        self.local_server.listen(self._id)
        connect(self.local_server.newConnection, self._on_new_connection)

    def setup_stream_to_running_app(self):
        self.logger.info('Another instance is running')
        self._stream_to_running_app = QTextStream(self.local_socket)
        self._stream_to_running_app.setCodec('UTF-8')

    def on_client_connected(self):
        pass

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

    def cleanup_crashed_server(self):
        self.logger.info('Cleaning up crashed server...')
        if self.local_socket:
            self.local_socket.disconnectFromServer()
        if self.local_server:
            self.local_server.close()
        QLocalServer.removeServer(self._id)
        self.logger.info('Crashed server was removed')

    def get_id(self):
        return self._id

    def send_message(self, msg):
        self.logger.info(f'Send message: {msg}')
        if not self._stream_to_running_app:
            return False

        self._stream_to_running_app << msg << '\n'  # pylint: disable=pointless-statement

        self._stream_to_running_app.flush()
        return self.local_socket.waitForBytesWritten()

    def _on_new_connection(self):
        socket = self.local_server.nextPendingConnection()
        if not socket:
            return

        client_socket = ClientConnection(socket)
        connect(client_socket.message_received, self.on_message_received)
        self.client_connections.append(client_socket)

        if self.tribler_window:
            self.tribler_window.raise_window()

    def on_message_received(self, msg):
        self.message_received.emit(msg)
        print(f"num connections: {len(self.client_connections)}")


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
