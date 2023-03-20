from __future__ import annotations

import logging
from abc import ABCMeta, abstractmethod

from ipv8.taskmanager import TaskManager

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse

MAX_INFOHASHES_IN_SCRAPE = 60


class TrackerSession(TaskManager):
    __meta__ = ABCMeta

    def __init__(self, tracker_type, tracker_url, tracker_address, announce_page, timeout):
        super().__init__()

        self._logger = logging.getLogger(self.__class__.__name__)
        # tracker type in lowercase
        self.tracker_type = tracker_type
        self.tracker_url = tracker_url
        self.tracker_address = tracker_address
        # if this is a nonempty string it starts with '/'.
        self.announce_page = announce_page
        self.timeout = timeout
        self.infohash_list = []
        self.last_contact = None

        # some flags
        self.is_initiated = False  # you cannot add requests to a session if it has been initiated
        self.is_finished = False
        self.is_failed = False

    def __str__(self):
        return f"{self.__class__.__name__}[{self.tracker_type}, {self.tracker_url}]"

    async def cleanup(self):
        await self.shutdown_task_manager()
        self.infohash_list = None

    def has_infohash(self, infohash):
        return infohash in self.infohash_list

    def add_infohash(self, infohash):
        """
        Adds an infohash into this session.
        :param infohash: The infohash to be added.
        """
        assert not self.is_initiated, "Must not add request to an initiated session."
        assert not self.has_infohash(infohash), "Must not add duplicate requests"
        if len(self.infohash_list) < MAX_INFOHASHES_IN_SCRAPE:
            self.infohash_list.append(infohash)

    def failed(self, msg=None):
        """
        This method handles everything that needs to be done when one step
        in the session has failed and thus no data can be obtained.
        """
        if not self.is_failed:
            self.is_failed = True
            result_msg = f"{self.tracker_type} tracker failed for url {self.tracker_url}"
            if msg:
                result_msg += f" (error: {msg})"
            raise ValueError(result_msg)

    @abstractmethod
    async def connect_to_tracker(self) -> TrackerResponse:
        """Does some work when a connection has been established."""
