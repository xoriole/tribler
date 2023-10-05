import json
import logging
import time

from PyQt5.QtCore import pyqtSignal, QObject

from tribler.core import notifications
from tribler.core.components.reporter.reported_error import ReportedError
from tribler.core.utilities.notifier import Notifier
from tribler.gui import gui_sentry_reporter

received_events = []


class EventRequestManager(QObject):
    """
    The EventRequestManager class handles the events connection over which important events in Tribler are pushed.
    """

    node_info_updated = pyqtSignal(object)
    received_remote_query_results = pyqtSignal(object)
    core_connected = pyqtSignal(object)
    core_port_known = pyqtSignal(int)
    new_version_available = pyqtSignal(str)
    discovered_channel = pyqtSignal(object)
    torrent_finished = pyqtSignal(object)
    low_storage_signal = pyqtSignal(object)
    tribler_shutdown_signal = pyqtSignal(str)
    change_loading_text = pyqtSignal(str)
    config_error_signal = pyqtSignal(str)

    def __init__(self, error_handler):
        QObject.__init__(self)
        self.current_event_string = ""
        self.shutting_down = False
        self.error_handler = error_handler
        self._logger = logging.getLogger(self.__class__.__name__)

        self.notifier = notifier = Notifier()
        notifier.add_observer(notifications.events_start, self.on_events_start)
        notifier.add_observer(notifications.rest_api_started, self.on_events_rest_api_started)
        notifier.add_observer(notifications.tribler_exception, self.on_tribler_exception)
        notifier.add_observer(notifications.channel_entity_updated, self.on_channel_entity_updated)
        notifier.add_observer(notifications.tribler_new_version, self.on_tribler_new_version)
        notifier.add_observer(notifications.channel_discovered, self.on_channel_discovered)
        notifier.add_observer(notifications.torrent_finished, self.on_torrent_finished)
        notifier.add_observer(notifications.low_space, self.on_low_space)
        notifier.add_observer(notifications.remote_query_results, self.on_remote_query_results)
        notifier.add_observer(notifications.tribler_shutdown_state, self.on_tribler_shutdown_state)
        notifier.add_observer(notifications.report_config_error, self.on_report_config_error)

    def on_events_start(self, public_key: str, version: str):
        # if public key format is changed, don't forget to change it at the core side as well
        if public_key:
            gui_sentry_reporter.set_user(public_key.encode('utf-8'))
        self.core_connected.emit(version)

    def on_events_rest_api_started(self, api_port: int):
        self.core_port_known.emit(api_port)

    def on_tribler_exception(self, error: dict):
        self.error_handler.core_error(ReportedError(**error))

    def on_channel_entity_updated(self, channel_update_dict: dict):
        self.node_info_updated.emit(channel_update_dict)

    def on_tribler_new_version(self, version: str):
        self.new_version_available.emit(version)

    def on_channel_discovered(self, data: dict):
        self.discovered_channel.emit(data)

    def on_torrent_finished(self, infohash: str, name: str, hidden: bool):
        self.torrent_finished.emit(dict(infohash=infohash, name=name, hidden=hidden))

    def on_low_space(self, disk_usage_data: dict):
        self.low_storage_signal.emit(disk_usage_data)

    def on_remote_query_results(self, data: dict):
        self.received_remote_query_results.emit(data)

    def on_tribler_shutdown_state(self, state: str):
        self.tribler_shutdown_signal.emit(state)

    def on_report_config_error(self, error):
        self.config_error_signal.emit(error)

    def process_data(self, data):
        self.current_event_string += bytes(data).decode('utf8')
        if len(self.current_event_string) > 0 and self.current_event_string[-2:] == '\n\n':
            for event in self.current_event_string.split('\n\n'):
                if len(event) == 0:
                    continue

                self.process_event(event)

            self.current_event_string = ""

    def process_event(self, event: str):
        event = event[5:] if event.startswith('data:') else event
        json_dict = json.loads(event)

        received_events.insert(0, (json_dict, time.time()))
        if len(received_events) > 100:  # Only buffer the last 100 events
            received_events.pop()

        topic_name = json_dict.get("topic", "noname")
        args = json_dict.get("args", [])
        kwargs = json_dict.get("kwargs", {})
        self.notifier.notify_by_topic_name(topic_name, *args, **kwargs)
