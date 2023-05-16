import pytest

from tribler.core.components.torrent_checker.torrent_checker.socket_manager import UdpTrackerDataProtocol
from tribler.core.components.torrent_checker.torrent_checker.trackers.dht.dht import DHTTracker


class MockUdpTrackerDataProtocol(UdpTrackerDataProtocol):
    pass


@pytest.fixture
def dht_tracker():
    socket_manager = MockUdpTrackerDataProtocol()
    return DHTTracker(socket_manager)


supported_urls = [
    (None, True),
    ("dht", True),
    ("DHT", True),
    ("udp://tracker.example.com:1337", False),
    ("http://tracker.example.com", False),
    ("https://tracker.example.com", False),
]


@pytest.mark.parametrize("url, expected", supported_urls)
def test_is_supported_url(url, expected, dht_tracker):
    assert dht_tracker.is_supported_url(url) is expected







