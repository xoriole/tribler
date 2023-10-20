import dataclasses
import json
import logging
import os
import socket
import sys
import uuid
from abc import ABC

from ipv8.taskmanager import TaskManager

from tribler.core.components.gui_socket.messages import ConnectRequest
from tribler.core.components.gui_socket.protocol import BaseMessage
from tribler.core.components.gui_socket.protocol_client import ProtocolClient

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
        self._uuid = str(uuid.uuid4())
        self.protocol = ProtocolClient(self._uuid, self)

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

    def send_data(self, data: bytes):
        raise NotImplementedError()

    def send_message(self, message: BaseMessage):
        self.send_data(json.dumps(message).encode('utf-8'))

    def send_connect_request(self):
        connect_request = ConnectRequest(
            msg_id=1,
            uuid=self._uuid,
            process='CORE',
            pid=os.getpid()
        )
        self.send_data(json.dumps(dataclasses.asdict(connect_request)).encode('utf-8'))


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

        def send_data(self, data: bytes):
            if self.client_socket:
                win32file.WriteFile(self.client_socket, data)


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
                self.on_connected()

        def close_socket(self):
            if self.client_socket:
                self.client_socket.close()

        def on_connected(self):
            self.send_connect_request()

        def send_data(self, data: bytes):
            if self.client_socket is None:
                logger.warning(f"GUI socket is not connected. Cannot send message: {data}")
                return

            self.client_socket.sendall(data)

    gui_socket_manager = UnixGuiSocketManager()

__all__ = ['gui_socket_manager']
