import logging
import time
from asyncio.exceptions import TimeoutError
from typing import List, Dict, Tuple, Optional

import async_timeout
from aiohttp import ClientSession, ClientTimeout, ClientResponseError

from tribler.core.components.socks_servers.socks5.aiohttp_connector import Socks5Connector
from tribler.core.components.torrent_checker.torrent_checker.dataclasses import TrackerResponse, HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.trackers import Tracker, TrackerException
from tribler.core.components.torrent_checker.torrent_checker.trackers.exceptions import EmptyResponseException, \
    InvalidResponseException, ExceptionWithReason, TimeoutException, InvalidTrackerURL, InvalidHttpResponse
from tribler.core.utilities.tracker_utils import add_url_params, parse_tracker_url
from tribler.core.utilities.utilities import bdecode_compat

# Keys found in tracker response dictionary
KEY_FILES = b'files'
KEY_FAILURE_REASON = b'failure reason'
KEY_COMPLETE = b'complete'
KEY_INCOMPLETE = b'incomplete'


class HttpTracker(Tracker):
    """
    HTTP Tracker with support for using proxy for anonymized requests.
    It supports fetching tracker response from both HTTP and HTTPS trackers.

    Usage:

    # Without Proxy
    http_tracker = HttpTracker()

    # With Proxy
    https_tracker = HttpTracker(proxy='localhost:5000')

    # To get torrent health info
    torrent_health_info = await http_tracker.get_torrent_health(b'infohash', 'https://sometracker.com', timeout=5)
    """

    def __init__(self, proxy: Optional[str] = None):
        """
        Args:
            proxy: Optional proxy to use for http request. eg. localhost:5000
        """
        self._logger = logging.getLogger(self.__class__.__name__)
        self.proxy_connector = self.get_proxy_connector(proxy)

    def is_supported_url(self, tracker_url: str) -> bool:
        """
        Return True if the tracker_url is supported.

        Args:
            tracker_url: Tracker URL.

        Returns:
            True: If the tracker URL starts with http
            False: Otherwise
        """
        return tracker_url.lower().startswith("http")

    async def get_torrent_health(
            self,
            infohash: bytes,
            tracker_url: str,
            timeout: Optional[int] = 5
    ) -> Optional[HealthInfo]:
        """
        Get torrent health info for the given torrent from the given tracker.

        Args:
            infohash: Torrent infohash
            tracker_url: Tracker URL. Could be http or https URL.
            timeout: Timeout in seconds.

        Raises:
            TrackerException: If there is failure in retrieving the tracker response

        Returns:
            HealthInfo : HealthInfo of the torrent including seeders and leechers if the request is successful.
                         None otherwise.
        """
        tracker_response: TrackerResponse = await self.get_tracker_response(tracker_url, [infohash], timeout=timeout)
        if tracker_response and tracker_response.torrent_health_list:
            return tracker_response.torrent_health_list[0]
        return None

    async def get_tracker_response(
            self,
            tracker_url: str,
            infohashes: List[bytes],
            timeout: Optional[int] = 5
    ) -> TrackerResponse:
        """
        Return Tracker response for a given tracker URL with a list of infohashes.

        Args:
            tracker_url: Tracker URL.
            infohashes: List of torrent infohashes (bytes)
            timeout: Timeout in seconds to wait for a response.

        Returns:
            TrackerResponse: TrackerResponse with torrent health info of included torrents.

        Raises:
            TimeoutException: If the response was not received from the tracker within time.
            InvalidTrackerURL: If encoding the tracker URL raises UnicodeEncodeError.
            InvalidHttpResponse: If HTTP Response other than HTTP_OK (status_code:200) is returned by the tracker.
            TrackerException: For all other exceptions.
        """
        try:
            async with async_timeout.timeout(timeout):
                session = self._get_http_session(timeout)
                scrape_url = self.get_scrape_url(tracker_url, infohashes)
                raw_response = await self.get_http_response(session, scrape_url)
                health_list = self.process_tracker_response(raw_response)
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
    def get_scrape_url(tracker_url: str, infohashes: List[bytes]) -> str:
        """
        Get proper scrape URL from the tracker announce URL and list of torrent infohashes.

        Args:
            tracker_url: Tracker URL. Usually ends with /announce.
            infohashes: List of torrent infohashes.

        Returns:
            A properly encoded scrape URL.

        Raises:
            MalformedTrackerURLException: If the tracker URL cannot be parsed properly.
            UnicodeEncodeError: If there is exception on encoding the URL.
        """
        tracker_type, tracker_address, announce_page = parse_tracker_url(tracker_url)

        scrape_page = announce_page.replace('announce', 'scrape')
        scrape_url = "%s://%s:%s%s" % (tracker_type, tracker_address[0], tracker_address[1], scrape_page)
        scrape_url = scrape_url.encode('ascii').decode('utf-8')

        # Add infohashes to the scrape URL
        scrape_url = add_url_params(scrape_url, {"info_hash": infohashes})
        return scrape_url

    def _get_http_session(self, timeout: int) -> ClientSession:
        return ClientSession(connector=self.proxy_connector,
                             raise_for_status=True,
                             timeout=ClientTimeout(total=timeout))

    @staticmethod
    def get_proxy_connector(proxy: Optional[str]) -> Socks5Connector:
        return Socks5Connector(proxy) if proxy else None

    @staticmethod
    async def get_http_response(session: ClientSession, url: str) -> Optional[bytes]:
        async with session:
            async with session.get(url) as response:
                return await response.read()

    @staticmethod
    def process_tracker_response(body: Optional[bytes]) -> List[HealthInfo]:
        if body is None:
            raise EmptyResponseException()

        response_dict = bdecode_compat(body)
        if not response_dict:
            raise InvalidResponseException()

        if KEY_FAILURE_REASON in response_dict:
            raise ExceptionWithReason(response_dict[KEY_FAILURE_REASON])

        files = response_dict.get(KEY_FILES)
        if not isinstance(files, dict):
            return []

        health_list: List[HealthInfo] = []
        now = int(time.time())

        for infohash, file_info in files.items():
            seeders, leechers = HttpTracker.parse_file_info(file_info)
            healthinfo = HealthInfo(infohash, last_check=now, seeders=seeders, leechers=leechers, self_checked=True)
            health_list.append(healthinfo)

        return health_list

    @staticmethod
    def parse_file_info(file_info: Dict) -> Tuple[int, int]:
        seeders = leechers = 0
        if isinstance(file_info, dict):
            # "complete: number of peers with the entire file, i.e. seeders (integer)"
            #  - https://wiki.theory.org/BitTorrentSpecification#Tracker_.27scrape.27_Convention
            seeders = file_info.get(KEY_COMPLETE, 0)
            leechers = file_info.get(KEY_INCOMPLETE, 0)
        return seeders, leechers
