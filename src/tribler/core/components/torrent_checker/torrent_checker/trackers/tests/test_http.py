from binascii import unhexlify
from unittest.mock import patch, AsyncMock, Mock

import pytest
from aiohttp import ClientResponseError

from tribler.core.components.torrent_checker.torrent_checker.dataclasses import HealthInfo
from tribler.core.components.torrent_checker.torrent_checker.trackers import TrackerException
from tribler.core.components.torrent_checker.torrent_checker.trackers.exceptions import EmptyResponseException, \
    InvalidResponseException, InvalidHttpResponse, InvalidTrackerURL
from tribler.core.components.torrent_checker.torrent_checker.trackers.http import HttpTracker

SAMPLE_INFOHASH = unhexlify("2c6b6858d61da9543d4231a71db4b1c9264b0685")  # Ubuntu 20.04
SAMPLE_VALID_TRACKER_RESPONSE = b'd5:filesd20:,khX\xd6\x1d\xa9T=B1\xa7\x1d\xb4\xb1\xc9&K\x06\x85d8' \
                          b':completei5e10:downloadedi0e10:incompletei0eeee'
SAMPLE_INVALID_TRACKER_RESPONSE = b'd8:announce36:http://tracker.example.com/invalid\n17' \
                                  b':failure reason23:invalid announce url - 1e'


@pytest.fixture
def dht_tracker():
    return HttpTracker()


def test_is_supported_url(dht_tracker):
    assert dht_tracker.is_supported_url("http://example.com")
    assert not dht_tracker.is_supported_url("udp://example.com")


def test_get_scrape_url(dht_tracker):
    tracker_url = "http://example.com/announce"
    infohashes = ["0123456789abcdef"]

    with patch("tribler.core.utilities.tracker_utils.parse_tracker_url",
               return_value=("http", ("example.com", "80"), "/announce")):
        result = dht_tracker.get_scrape_url(tracker_url, infohashes)

    assert result == "http://example.com:80/scrape?info_hash=0123456789abcdef"


def test_get_proxy_connector_with_proxy(dht_tracker):
    proxy = "socks5://127.0.0.1:9050"
    connector = dht_tracker.get_proxy_connector(proxy)
    assert connector is not None


def test_get_proxy_connector_without_proxy(dht_tracker):
    connector = dht_tracker.get_proxy_connector(None)
    assert connector is None


async def test_get_tracker_response():
    tracker_url = 'http://tracker.example.com/announce'

    # with patch('aiohttp.ClientSession') as mock_session:
    http_tracker = HttpTracker()
    http_tracker._get_http_session = lambda timeout: Mock()

    # Test success response
    http_tracker.get_http_response = AsyncMock(return_value=SAMPLE_VALID_TRACKER_RESPONSE)
    response = await http_tracker.get_tracker_response(tracker_url, [SAMPLE_INFOHASH], timeout=0.01)
    assert response.url == tracker_url
    assert len(response.torrent_health_list) == 1

    # Test HTTP error response
    http_error = ClientResponseError(Mock(), Mock())
    http_tracker.get_http_response = AsyncMock(side_effect=http_error)
    with pytest.raises(InvalidHttpResponse):
        _ = await http_tracker.get_tracker_response(tracker_url, [SAMPLE_INFOHASH], timeout=0.01)

    # Unicode error on scrape URL
    def mock_get_scrape_url(*args, **kwargs):
        url = "http://someunicodecharintracker.org"
        raise UnicodeEncodeError('utf-8', url, 1, 2, 'Fake Unicode Error!')

    http_tracker.get_scrape_url = Mock(side_effect=mock_get_scrape_url)
    http_tracker.get_http_response = AsyncMock(return_value=SAMPLE_VALID_TRACKER_RESPONSE)
    with pytest.raises(InvalidTrackerURL):
        _ = await http_tracker.get_tracker_response(tracker_url, [SAMPLE_INFOHASH], timeout=0.01)


def test_process_body_invalid_response():
    http_tracker = HttpTracker()
    with pytest.raises(TrackerException, match="Invalid bencoded response"):
        http_tracker.process_tracker_response(b'invalid bencoded response')


def test_process_body_no_response():
    http_tracker = HttpTracker()
    with pytest.raises(TrackerException, match="No response body"):
        http_tracker.process_tracker_response(None)


def test_process_body_failure():
    http_tracker = HttpTracker()
    with pytest.raises(TrackerException, match="Invalid bencoded response"):
        http_tracker.process_tracker_response(SAMPLE_INVALID_TRACKER_RESPONSE)


def test_process_body_success():
    http_tracker = HttpTracker()
    health_list = http_tracker.process_tracker_response(SAMPLE_VALID_TRACKER_RESPONSE)

    assert len(health_list) == 1
    assert health_list[0].infohash == SAMPLE_INFOHASH
    assert health_list[0].seeders == 5
    assert health_list[0].leechers == 0
