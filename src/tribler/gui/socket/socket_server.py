from PyQt5.QtCore import QObject

from tribler.core.components.gui_socket.interface import SocketServer


class GUISocketServer(QObject, SocketServer):

    def __init__(self, socket_id: bytes):
        super().__init__()
        self.socket_id = socket_id

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
