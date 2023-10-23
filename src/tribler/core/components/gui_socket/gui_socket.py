import dataclasses
import json
import logging
import os
import socket
import sys
import uuid
from abc import ABC
from asyncio import Queue

from tribler.core import notifications
from tribler.core.components.gui_socket.events_manager import MessageDict
from tribler.core.components.gui_socket.messages import ConnectRequest
from tribler.core.components.gui_socket.protocol import BaseMessage
from tribler.core.components.gui_socket.protocol_client import ProtocolClient
from tribler.core.components.restapi.rest.util import fix_unicode_dict
from tribler.core.utilities.async_group.async_group import AsyncGroup
from tribler.core.utilities.process_manager import ProcessKind

CHECK_INTERVAL = 10

WIN_SOCKET_PATH = r'\\.\pipe\triblerapp'
UNIX_SOCKET_PATH = '/tmp/triblerapp'

logger = logging.getLogger(__name__)
# gui_socket_manager = None


class GuiSocketManager(ABC):

    def __init__(self, notifier, public_key):
        super().__init__()
        self._public_key = public_key
        self.client_socket = None
        self._connected = False
        self._uid = str(uuid.uuid4())
        self._kind = ProcessKind.Core.name
        self.protocol = ProtocolClient(self._uid, self)

        self._notifier = notifier
        # self.queue = Queue()
        # self.async_group = AsyncGroup()
        # self.async_group.add_task(self.process_queue())
        # notifier.add_observer(notifications.circuit_removed, self.on_circuit_removed)
        notifier.add_generic_observer(self.on_notification)

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

    def set_notifier(self, notifier):
        self._notifier = notifier
        self._notifier.add_generic_observer(self.on_notification)

    def initial_message(self) -> MessageDict:
        return {
            "topic": notifications.events_start.__name__,
            "kwargs": {"public_key": self._public_key, "version": "7.13.0"}
        }

    def on_notification(self, topic, *args, **kwargs):
        event = {"topic": topic.__name__, "args": args, "kwargs": kwargs}
        print(f"received event: {event}")
        # self.send_event({"topic": topic.__name__, "args": args, "kwargs": kwargs})
        self.send_event(event)

    def send_data(self, data: bytes):
        raise NotImplementedError()

    def send_message(self, message: BaseMessage):
        try:
            message_str = json.dumps(message) + '\n\n'
            self.send_data(message_str.encode('utf-8'))
        except TypeError:
            pass

    def send_connect_request(self):
        connect_request = ConnectRequest(
            msg_id=1,
            uuid=self._uid,
            process='CORE',
            pid=os.getpid()
        )
        self.send_data(json.dumps(dataclasses.asdict(connect_request)).encode('utf-8'))

    def send_port_info(self, port: int):
        self.protocol.gui_send_port_info(self._uid, port)

    def send_event(self, event: dict | bytes):
        if isinstance(event, dict):
            try:
                event = json.dumps(event)
            except TypeError:
                print(f"Failed to send event because of type error: {event}")
                return
        self.protocol.gui_send_event(self._uid, event)


if sys.platform.startswith("win"):
    import win32file
    import pywintypes

    class WinGuiSocketManager(GuiSocketManager):

        def __init__(self, notifier, public_key):
            super().__init__(notifier, public_key)

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


    # gui_socket_manager = WinGuiSocketManager()

else:  # For Linux and macOS
    class UnixGuiSocketManager(GuiSocketManager):

        def __init__(self, notifier, public_key):
            super().__init__(notifier, public_key)

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
            # self.send_connect_request()
            self.protocol.gui_register(self._uid, self._kind)
            print(f"sending initial message")
            self.protocol.gui_send_data(self._uid, self.encode_message(self.initial_message()))

        def encode_message(self, message: MessageDict) -> bytes:
            try:
                message = json.dumps(message)
            except UnicodeDecodeError:
                # The message contains invalid characters; fix them
                self._logger.error("Event contains non-unicode characters, fixing")
                message = json.dumps(fix_unicode_dict(message))
            except TypeError as te:
                logger.warning(te)
                return b''
            return b'data: ' + message.encode('utf-8') + b'\n\n'

        def send_data(self, data: bytes):
            if self.client_socket is None:
                logger.warning(f"GUI socket is not connected. Cannot send message: {data}")
                return

            try:
                self.client_socket.sendall(data)
            except OSError as ose:
                logger.exception(ose)


def get_socket_manager(notifier, public_key):
    if sys.platform.startswith("win"):
        return WinGuiSocketManager(notifier, public_key)
    return UnixGuiSocketManager(notifier, public_key)

