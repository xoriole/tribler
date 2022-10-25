from sdbus import (DbusInterfaceCommonAsync, dbus_method_async,
                   dbus_property_async, dbus_signal_async)

from tribler.core.version import version_id


class TriblerInterface(
    DbusInterfaceCommonAsync,
    interface_name='org.tribler.interface'
):
    _CONFIG = None

    def set_config(self, config):
        TriblerInterface._CONFIG = config

    @dbus_method_async(
        input_signature='s',
        result_signature='s',
    )
    async def upper(self, string: str) -> str:
        return string.upper()

    @dbus_property_async(
        property_signature='s',
    )
    def hello_world(self) -> str:
        return 'Hello, World!'

    @dbus_property_async(
        property_signature='s',
    )
    def name(self) -> str:
        return 'Tribler'

    @dbus_property_async(
        property_signature='s',
    )
    def version(self) -> str:
        return version_id

    @dbus_property_async(
        property_signature='s',
    )
    def state_dir(self) -> str:
        if TriblerInterface._CONFIG:
            return str(TriblerInterface._CONFIG.state_dir)
        return None

    @dbus_property_async(
        property_signature='s',
    )
    def config(self) -> str:
        if TriblerInterface._CONFIG:
            return TriblerInterface._CONFIG.json()
        return "{}"
