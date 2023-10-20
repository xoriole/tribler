from typing import TypedDict


class Protocol:

    def gui_register(self, uid: str, kind: str):
        ...

    def gui_send_event(self, uid: str, event: str):
        ...

    def gui_send_port_info(self, uid: str, port: int):
        ...

    def gui_send_command_args(self, uid: str, args: list):
        ...

    def gui_send_data(self, uid: str, data: bytes):
        ...


class BaseMessage(TypedDict):
    uid: str
    method: str


class RegisterMessage(BaseMessage):
    kind: str


class EventMessage(BaseMessage):
    event: dict


class PortMessage(BaseMessage):
    port: int


class DataMessage(BaseMessage):
    data: bytes


