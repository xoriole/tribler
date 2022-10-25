from asyncio import new_event_loop

from tribler.core.components.dbus.dbus_interface import TriblerInterface

# Create a new proxied object
example_object = TriblerInterface.new_proxy('org.tribler.core', '/')


async def print_clock() -> None:
    # Use async for loop to print clock signals we receive
    async for x in example_object.clock:
        print('Got clock: ', x)


async def call_upper() -> None:
    s = 'test string'
    s_after = await example_object.upper(s)

    print('Initial string: ', s)
    print('After call: ', s_after)


async def get_hello_world() -> None:
    print('Remote property: ', await example_object.hello_world)


async def get_name() -> None:
    print('Remote property: ', await example_object.name)


async def get_version() -> None:
    print('Remote property: ', await example_object.version)


async def get_state_dir() -> None:
    print('Remote property State Dir: ', await example_object.state_dir)


async def get_config() -> None:
    print('Remote property Config: ', await example_object.config)

loop = new_event_loop()

# Always binds your tasks to a variable
task_upper = loop.create_task(call_upper())
# task_clock = loop.create_task(print_clock())
task_hello_world = loop.create_task(get_hello_world())
task_name = loop.create_task(get_name())
task_version = loop.create_task(get_version())
task_version = loop.create_task(get_state_dir())
task_config = loop.create_task(get_config())

loop.run_forever()