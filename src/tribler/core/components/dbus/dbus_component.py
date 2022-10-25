from sdbus import request_default_bus_name_async

from tribler.core.components.component import Component
from tribler.core.components.dbus.dbus_interface import TriblerInterface


class DbusComponent(Component):

    def __init__(self):
        super().__init__()
        self.export_object = None

    async def run(self):
        await super().run()
        self.export_object = TriblerInterface()
        self.export_object.set_config(self.session.config)
        # Acquire a known name on the bus
        # Clients will use that name to address this server
        await request_default_bus_name_async('org.tribler.core')
        # Export the object to dbus
        self.export_object.export_to_dbus('/')
        print("DBus Component is running")

    async def shutdown(self):
        await super().shutdown()
        print("DBus Component is shutting down...")
