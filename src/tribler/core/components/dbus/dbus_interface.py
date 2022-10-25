from dbus_next.service import ServiceInterface, method, dbus_property, signal, Variant
from dbus_next.aio import MessageBus

import asyncio

from tribler.core.version import version_id

DBUS_SERVICE_NAME = 'org.tribler.dbus'
DBUS_INTERFACE_NAME = 'org.tribler.TriblerInterface'
DBUS_INTERFACE_PATH = '/org/tribler/core'
DBUS_INTROSPECTION_XML = f"""
<!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
  "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
 <node name="{DBUS_INTERFACE_PATH}">
   <interface name="{DBUS_INTERFACE_NAME}">
     <property name="app" type="s" access="readwrite"/>
     <property name="version" type="s" access="readwrite"/>
     <property name="config_json" type="s" access="readwrite"/>
   </interface>
</node>
"""


class TriblerInterface(ServiceInterface):

    def __init__(self, config=None):
        super().__init__('org.tribler.TriblerInterface')
        self._config_json = config.json() if config else "{}"
        self._app = 'Tribler'
        self._version = version_id

    @dbus_property()
    def app(self) -> 's':
        return "Tribler"

    @app.setter
    def app_setter(self, val: 's'):
        self._app = val

    @dbus_property()
    def version(self) -> 's':
        return self._version

    @version.setter
    def version_setter(self, val: 's'):
        self._version = val

    @dbus_property()
    def config_json(self) -> 's':
        return self._config_json

    @config_json.setter
    def config_json_setter(self, val: 's'):
        self._config_json = val


async def enable_interface(config=None):
    bus = await MessageBus().connect()
    interface = TriblerInterface(config)
    bus.export(DBUS_INTERFACE_PATH, interface)
    # now that we are ready to handle requests, we can request name from D-Bus
    # TODO: Handling exception cases
    await bus.request_name(DBUS_SERVICE_NAME)

