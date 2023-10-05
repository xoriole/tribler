import logging
import socket
import sys
from abc import ABC

from ipv8.taskmanager import TaskManager

CHECK_INTERVAL = 10

WIN_SOCKET_PATH = r'\\.\pipe\triblerapp'
UNIX_SOCKET_PATH = '/tmp/triblerapp'

logger = logging.getLogger(__name__)
gui_socket_manager = None


class GuiSocketManager(ABC):

    def __init__(self):
        super().__init__()
        self.client_socket = None
        self._connected = False

    def start(self):
        self.connect_gui_socket()

    async def stop(self):
        self.close_socket()

    def is_connected(self):
        return self._connected

    def get_socket_path(self):
        raise NotImplementedError()

    def connect_gui_socket(self):
        raise NotImplementedError()

    def close_socket(self):
        raise NotImplementedError()

    def send_message(self, message: bytes):
        raise NotImplementedError()


if sys.platform.startswith("win"):
    import win32file
    import pywintypes

    class WinGuiSocketManager(GuiSocketManager):
        def get_socket_path(self):
            return WIN_SOCKET_PATH

        def connect_gui_socket(self):
            try:
                self.client_socket = win32file.CreateFile(
                    self.get_socket_path(),
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0, None,
                    win32file.OPEN_EXISTING,
                    0, None
                )
                self._connected = True
            except pywintypes.error as e:
                if e.args[0] == 2:
                    logger.error("Windows GUI socket is not available, exiting...")
                else:
                    raise

        def close_socket(self):
            if self.client_socket:
                win32file.CloseHandle(self.client_socket)

        def send_message(self, message: bytes):
            if self.client_socket:
                win32file.WriteFile(self.client_socket, message)


    gui_socket_manager = WinGuiSocketManager()

else:  # For Linux and macOS
    class UnixGuiSocketManager(GuiSocketManager):

        def get_socket_path(self):
            return UNIX_SOCKET_PATH

        def connect_gui_socket(self):
            if self.client_socket is None:
                self.client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.client_socket.connect(self.get_socket_path())
                logger.info('Socket connected')
                self._connected = True

        def close_socket(self):
            if self.client_socket:
                self.client_socket.close()

        def send_message(self, message: bytes):
            if self.client_socket is None:
                logger.warning(f"GUI socket is not connected. Cannot send message: {message}")
                return

            self.client_socket.sendall(message)

    gui_socket_manager = UnixGuiSocketManager()

__all__ = ['gui_socket_manager']
