from pathlib import Path

from dbus_next.aio import MessageBus

import asyncio


loop = asyncio.get_event_loop()

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


async def main():
    bus = await MessageBus().connect()
    obj = bus.get_proxy_object(DBUS_SERVICE_NAME, DBUS_INTERFACE_PATH, DBUS_INTROSPECTION_XML)
    interface = obj.get_interface(DBUS_INTERFACE_NAME)

    app_name = await interface.get_app()
    version = await interface.get_version()
    config = await interface.get_config_json()
    print(app_name)
    print(version)
    print(config)

    await loop.create_future()

loop.run_until_complete(main())
