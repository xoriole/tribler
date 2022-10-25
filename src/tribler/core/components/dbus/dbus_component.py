from tribler.core.components.component import Component
from tribler.core.components.dbus import dbus_interface
from tribler.core.components.dbus.dbus_interface import TriblerInterface


class DbusComponent(Component):

    def __init__(self):
        super().__init__()

    async def run(self):
        await super().run()
        await dbus_interface.enable_interface(self.session.config)
        print("DBus Component is running")

    async def shutdown(self):
        await super().shutdown()
        print("DBus Component is shutting down...")