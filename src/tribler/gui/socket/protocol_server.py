from tribler.core.components.gui_socket.protocol import Protocol


class ProtocolServer(Protocol):

    def __init__(self, socket_server):
        self.socket_server = socket_server
        self.clients = {}

    def handle_message(self, message: bytes):
        print(f"received message on protocol server: {message}")
        pass

    def gui_register(self, uid: str, kind: str):
        if uid in self.clients:
            raise ValueError(f"Client[{uid}] already exists")

        self.clients[uid] = {'kind': kind}
        return True

    def gui_send_event(self, uid: str, event: str):
        ...

    def gui_send_port_info(self, uid: str, port: int):
        ...

    def gui_send_command_args(self, uid: str, args: list):
        ...

    def gui_send_data(self, uid: str, data: bytes):
        ...
