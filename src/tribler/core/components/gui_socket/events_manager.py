import time
from asyncio import Queue
from typing import Dict, Any

from ipv8.messaging.anonymization.tunnel import Circuit

from tribler.core import notifications
from tribler.core.utilities.async_group.async_group import AsyncGroup

topics_to_send_to_gui = [
    notifications.tunnel_removed,
    notifications.watch_folder_corrupt_file,
    notifications.tribler_new_version,
    notifications.channel_discovered,
    notifications.torrent_finished,
    notifications.channel_entity_updated,
    notifications.tribler_shutdown_state,
    notifications.remote_query_results,
    notifications.low_space,
    notifications.report_config_error,
    notifications.rest_api_started,
]

MessageDict = Dict[str, Any]


class CoreEventsManager:

    def __init__(self, notifier, public_key: str = None):
        self.public_key = public_key
        self.queue = Queue()
        self.async_group = AsyncGroup()
        self.async_group.add_task(self.process_queue())

        self.notifier = notifier
        self.notifier.add_observer(notifications.circuit_removed, self.on_circuit_removed)
        self.notifier.add_generic_observer(self.on_notification)

    def on_notification(self, topic, *args, **kwargs):
        if topic in topics_to_send_to_gui:
            self.send_event({"topic": topic.__name__, "args": args, "kwargs": kwargs})

    def on_circuit_removed(self, circuit: Circuit, additional_info: str):
        # The original notification contains non-JSON-serializable argument, so we send another one to GUI
        self.notifier[notifications.tunnel_removed](circuit_id=circuit.circuit_id, bytes_up=circuit.bytes_up,
                                                    bytes_down=circuit.bytes_down,
                                                    uptime=time.time() - circuit.creation_time,
                                                    additional_info=additional_info)

    def has_connection_to_gui(self) -> bool:
        return bool(self.events_responses) or self.gui_socket_manager.is_connected()

    def should_skip_message(self, message: MessageDict) -> bool:
        """
        Returns True if EventsEndpoint should skip sending message to GUI due to a shutdown or no connection to GUI.
        Issue an appropriate warning if the message cannot be sent.
        """
        if self._shutdown:
            self._logger.warning(f"Shutdown is in progress, skip message: {message}")
            return True

        if not self.has_connection_to_gui():
            self._logger.warning(f"No connections to GUI, skip message: {message}")
            return True

        return False

    def send_event(self, message: MessageDict):
        """
        Put event message to a queue to be sent to GUI
        """
        if not self.should_skip_message(message):
            self.queue.put_nowait(message)

    async def process_queue(self):
        while True:
            message = await self.queue.get()
            if not self.should_skip_message(message):
                await self._write_data(message)

    async def _write_data(self, message: MessageDict):
        """
        Write data over the event socket if it's open.
        """
        self._logger.debug(f'Write message: {message}')
        try:
            message_bytes = self.encode_message(message)
            self.gui_socket_manager.send_data(message_bytes)
        except Exception as e:  # pylint: disable=broad-except
            # if a notification arguments contains non-JSON-serializable data, the exception should be logged
            self._logger.exception(e)
            return

        processed_responses = []
        for response in self.events_responses:
            print(f"response: {response}")
            try:
                await response.write(message_bytes)
                # by creating the list with processed responses we want to remove responses with
                # ConnectionResetError from `self.events_responses`:
                processed_responses.append(response)
            except ConnectionResetError as e:
                # The connection was closed by GUI
                self._logger.warning(e, exc_info=True)
        self.events_responses = processed_responses
