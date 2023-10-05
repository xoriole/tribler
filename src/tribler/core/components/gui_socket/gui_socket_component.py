from tribler.core.components.component import Component
from tribler.core.components.gui_process_watcher.gui_process_watcher import GuiProcessWatcher
from tribler.core.components.gui_socket.gui_socket import GuiSocketManager, gui_socket_manager


class GuiSocketComponent(Component):
    manager: GuiSocketManager = None

    async def run(self):
        await super().run()

        self.manager = gui_socket_manager
        self.logger.info(f'Starting GUI socket manager on socket {self.manager.get_socket_path()}')
        self.manager.start()

    async def shutdown(self):
        await super().shutdown()
        if self.manager:
            await self.manager.stop()
