from tribler.core.components.component import Component
from tribler.core.components.exceptions import NoneComponent
from tribler.core.components.gui_process_watcher.gui_process_watcher import GuiProcessWatcher
from tribler.core.components.gui_socket.gui_socket import GuiSocketManager, get_socket_manager
from tribler.core.components.key.key_component import KeyComponent
from tribler.core.utilities.notifier import Notifier


class GuiSocketComponent(Component):
    manager: GuiSocketManager = None
    notifier: Notifier = None

    async def run(self):
        await super().run()

        key_component = await self.maybe_component(KeyComponent)
        public_key = key_component.primary_key.key.pk if not isinstance(key_component, NoneComponent) else b''

        self.manager = get_socket_manager(self.session.notifier, public_key)
        self.logger.info(f'Starting GUI socket manager on socket {self.manager.get_socket_path()}')
        self.manager.start()

    async def shutdown(self):
        await super().shutdown()
        if self.manager:
            await self.manager.stop()
