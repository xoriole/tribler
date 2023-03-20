from __future__ import annotations

import time
from typing import List

from aiohttp import ClientSession, ClientTimeout, ClientResponseError

from tribler.core.components.socks_servers.socks5.aiohttp_connector import Socks5Connector
from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse, HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.session.tracker import TrackerSession
from tribler.core.utilities.tracker_utils import add_url_params
from tribler.core.utilities.utilities import bdecode_compat


class HttpTrackerSession(TrackerSession):
    def __init__(self, tracker_url, tracker_address, announce_page, timeout, proxy):
        super().__init__('http', tracker_url, tracker_address, announce_page, timeout)
        self._session = ClientSession(connector=Socks5Connector(proxy) if proxy else None,
                                      raise_for_status=True,
                                      timeout=ClientTimeout(total=self.timeout))

    async def connect_to_tracker(self) -> TrackerResponse:
        # create the HTTP GET message
        # Note: some trackers have strange URLs, e.g.,
        #       http://moviezone.ws/announce.php?passkey=8ae51c4b47d3e7d0774a720fa511cc2a
        #       which has some sort of 'key' as parameter, so we need to use the add_url_params
        #       utility function to handle such cases.

        url = add_url_params("http://%s:%s%s" %
                             (self.tracker_address[0], self.tracker_address[1],
                              self.announce_page.replace('announce', 'scrape')),
                             {"info_hash": self.infohash_list})

        # no more requests can be appended to this session
        self.is_initiated = True
        self.last_contact = int(time.time())

        try:
            self._logger.debug("%s HTTP SCRAPE message sent: %s", self, url)
            async with self._session:
                async with self._session.get(url.encode('ascii').decode('utf-8')) as response:
                    body = await response.read()
        except UnicodeEncodeError as e:
            raise e
        except ClientResponseError as e:
            self._logger.warning("%s HTTP SCRAPE error response code %s", self, e.status)
            self.failed(msg=f"error code {e.status}")
        except Exception as e:
            self.failed(msg=str(e))

        return self._process_scrape_response(body)

    def _process_scrape_response(self, body) -> TrackerResponse:
        """
        This function handles the response body of an HTTP result from an HTTP tracker
        """
        if body is None:
            self.failed(msg="no response body")

        response_dict = bdecode_compat(body)
        if not response_dict:
            self.failed(msg="no valid response")

        health_list: List[HealthInfo] = []
        now = int(time.time())

        unprocessed_infohashes = set(self.infohash_list)
        files = response_dict.get(b'files')
        if isinstance(files, dict):
            for infohash, file_info in files.items():
                seeders = leechers = 0
                if isinstance(file_info, dict):
                    # "complete: number of peers with the entire file, i.e. seeders (integer)"
                    #  - https://wiki.theory.org/BitTorrentSpecification#Tracker_.27scrape.27_Convention
                    seeders = file_info.get(b'complete', 0)
                    leechers = file_info.get(b'incomplete', 0)

                unprocessed_infohashes.discard(infohash)
                health_list.append(HealthInfo(infohash, seeders, leechers, last_check=now, self_checked=True))

        elif b'failure reason' in response_dict:
            self._logger.info("%s Failure as reported by tracker [%s]", self, repr(response_dict[b'failure reason']))
            self.failed(msg=repr(response_dict[b'failure reason']))

        # handle the infohashes with no result (seeders/leechers = 0/0)
        health_list.extend(HealthInfo(infohash=infohash, last_check=now, self_checked=True)
                           for infohash in unprocessed_infohashes)

        self.is_finished = True
        return TrackerResponse(url=self.tracker_url, torrent_health_list=health_list)

    async def cleanup(self):
        """
        Cleans the session by cancelling all deferreds and closing sockets.
        :return: A deferred that fires once the cleanup is done.
        """
        await self._session.close()
        await super().cleanup()
