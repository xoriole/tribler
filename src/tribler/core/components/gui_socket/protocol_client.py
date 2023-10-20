from typing import TYPE_CHECKING

from tribler.core.components.gui_socket.protocol import *

if TYPE_CHECKING:
    from tribler.core.components.gui_socket.gui_socket import GuiSocketManager


class ProtocolClient(Protocol):

    def __init__(self, uid: str, socket_manager: "GuiSocketManager"):
        super().__init__()
        self.uid = uid
        self.socket_manager = socket_manager

    def gui_register(self, uid: str, kind: str):
        message: RegisterMessage = {'uid': self.uid, 'method': 'gui_register', 'kind': kind}
        self.socket_manager.send_message(message)

    def gui_send_event(self, uid: str, event: dict):
        message: EventMessage = {'uid': self.uid, 'method': 'gui_send_event', 'event': event}
        self.socket_manager.send_message(message)

    def gui_send_port_info(self, uid: str, port: int):
        message: PortMessage = {'uid': self.uid, 'method': 'gui_send_port_info', 'port': port}
        self.socket_manager.send_message(message)

    def gui_send_command_args(self, uid: str, args: list):
        raise ValueError("Core service is not allowed to send command args")

    def gui_send_data(self, uid: str, data: bytes):
        message: DataMessage = {'uid': self.uid, 'method': 'gui_send_data', 'data': data}
        self.socket_manager.send_message(message)
