import logging
import time
from asyncio.exceptions import TimeoutError
from typing import List

import async_timeout
from aiohttp import ClientSession, ClientTimeout, ClientResponseError

from tribler.core.components.socks_servers.socks5.aiohttp_connector import Socks5Connector
from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse, HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.trackers import Tracker, TrackerException
from tribler.core.components.torrent_checker.torrent_checker.trackers.exceptions import EmptyResponseException, \
    InvalidResponseException, ExceptionWithReason, TimeoutException, InvalidTrackerURL, InvalidHttpResponse
from tribler.core.utilities.tracker_utils import add_url_params, parse_tracker_url
from tribler.core.utilities.utilities import bdecode_compat


class HttpTracker(Tracker):

    def __init__(self, proxy=None):
        self._logger = logging.getLogger(self.__class__.__name__)
        self.proxy_connector = self.get_proxy_connector(proxy)

    async def get_torrent_health(self, tracker_url, infohash, timeout=5):
        tracker_response: TrackerResponse = await self.get_tracker_response(tracker_url, [infohash], timeout=timeout)
        if tracker_response and tracker_response.torrent_health_list:
            return tracker_response.torrent_health_list[0]
        return None

    async def get_tracker_response(self, tracker_url, infohashes, timeout=5) -> TrackerResponse:
        scrape_url = self.get_scrape_url(tracker_url, infohashes)

        try:
            async with async_timeout.timeout(timeout):
                session = self.get_http_session(timeout)
                tracker_response = await self.get_http_response(session, scrape_url)
                health_list = self.process_tracker_response(tracker_response)
                return TrackerResponse(url=tracker_url, torrent_health_list=health_list)

        except TimeoutError as ex:
            raise TimeoutException(timeout) from ex
        except UnicodeEncodeError as unicode_error:
            raise InvalidTrackerURL(tracker_url) from unicode_error
        except ClientResponseError as http_error:
            raise InvalidHttpResponse(http_error.status) from http_error
        except Exception as other_exceptions:
            raise TrackerException() from other_exceptions

    @staticmethod
    def get_scrape_url(tracker_url, infohashes):
        tracker_type, tracker_address, announce_page = parse_tracker_url(tracker_url)

        scrape_page = announce_page.replace('announce', 'scrape')
        scrape_url = "%s://%s:%s%s" % (tracker_type, tracker_address[0], tracker_address[1], scrape_page)
        scrape_url = scrape_url.encode('ascii').decode('utf-8')

        # Add infohashes to the scrape URL
        scrape_url = add_url_params(scrape_url, {"info_hash": infohashes})
        return scrape_url

    def get_http_session(self, timeout):
        return ClientSession(connector=self.proxy_connector,
                             raise_for_status=True,
                             timeout=ClientTimeout(total=timeout))

    @staticmethod
    def get_proxy_connector(proxy):
        return Socks5Connector(proxy) if proxy else None

    @staticmethod
    async def get_http_response(session, url):
        async with session:
            async with session.get(url) as response:
                return await response.read()

    @staticmethod
    def process_tracker_response(body) -> List[HealthInfo]:
        if body is None:
            raise EmptyResponseException()

        response_dict = bdecode_compat(body)
        if not response_dict:
            raise InvalidResponseException()

        if b'failure reason' in response_dict:
            raise ExceptionWithReason(response_dict[b'failure reason'])

        files = response_dict.get(b'files')
        if not isinstance(files, dict):
            return []

        health_list: List[HealthInfo] = []
        now = int(time.time())

        for infohash, file_info in files.items():
            seeders, leechers = HttpTracker.get_health_from_file_info(file_info)
            healthinfo = HealthInfo(infohash, last_check=now, seeders=seeders, leechers=leechers, self_checked=True)
            health_list.append(healthinfo)

        return health_list

    @staticmethod
    def get_health_from_file_info(file_info):
        seeders = leechers = 0
        if isinstance(file_info, dict):
            # "complete: number of peers with the entire file, i.e. seeders (integer)"
            #  - https://wiki.theory.org/BitTorrentSpecification#Tracker_.27scrape.27_Convention
            seeders = file_info.get(b'complete', 0)
            leechers = file_info.get(b'incomplete', 0)
        return seeders, leechers
