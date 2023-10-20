import json

from tribler.core.components.gui_socket.protocol import Protocol, BaseMessage

PREFIXES = [
    "data: "
]


class ProtocolServer(Protocol):

    def __init__(self, socket_server):
        self.socket_server = socket_server
        self.clients = {}

    def _prepare_for_parsing(self, data: bytes):
        data = data.decode('utf-8').strip()
        for prefix in PREFIXES:
            if data.startswith(prefix):
                data = data.replace(prefix, "", 1).strip()
        return data

    def handle_data(self, data: bytes):
        print(f"received message on protocol server: {data}")
        data: str = self._prepare_for_parsing(data)
        if not data:
            print("No data")
            return

        try:
            message: BaseMessage = json.loads(data)
        except json.decoder.JSONDecodeError:
            print(f"failed to deserialize data: |{data}|")
            raise

        uid = message.get('uid', None)
        if not uid:
            print(f"uid is None")
            return

        method_name = message.get('method', None)
        if not method_name and not hasattr(self, method_name):
            print(f"method name not found :{method_name}")
            return

        extra_args = {k: v for k, v in message.items() if k not in ['uid', 'method']}
        method = getattr(self, method_name)
        method(uid, **extra_args)

    def gui_register(self, uid: str, kind: str):
        print(f"calling gui_register with uid: {uid}, kind: {kind}")
        if uid in self.clients:
            raise ValueError(f"Client[{uid}] already exists")

        self.clients[uid] = {'kind': kind}
        return True

    def gui_send_event(self, uid: str, event: str):
        print(f"calling gui_send_events with uid: {uid}")
        ...

    def gui_send_port_info(self, uid: str, port: int):
        print(f"calling gui_send_port_info with uid: {uid}")
        ...

    def gui_send_command_args(self, uid: str, args: list):
        print(f"calling gui_send_command_args with uid: {uid}")
        ...

    def gui_send_data(self, uid: str, data: bytes):
        print(f"calling gui_send_data with uid: {uid}")
        ...
