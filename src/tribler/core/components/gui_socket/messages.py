from dataclasses import dataclass, field

MSG_CONNECT = 1
MSG_CONNECT_OK = 2
MSG_CONNECT_REFUSED = 3


@dataclass
class ConnectRequest:
    msg_id: int
    uuid: str
    process: str
    pid: int


@dataclass
class ConnectOk:
    msg_id: int


@dataclass
class ConnectRefused:
    msg_id: int
