from binascii import unhexlify

import pytest
from pytest_asyncio import fixture

from tribler.core.components.torrent_checker.torrent_checker.checker_service import CheckerService
from tribler.core.components.torrent_checker.torrent_checker.trackers import TrackerException
from tribler.core.components.torrent_checker.torrent_checker.trackers.http import HttpTracker


SAMPLE_INFOHASH = unhexlify("99c82bb73505a3c0b453f9fa0e881d6e5a32a0c1")  # Ubuntu 20.04

HTTP_TRACKER_URL = "https://torrent.ubuntu.com/announce"
UDP_TRACKER_URL = "udp://tracker.torrent.eu.org:451"
DHT_TRACKER_URL = "DHT"


@fixture(name="checker_service")
async def checker_service_fixture():
    checker_service = CheckerService()
    await checker_service.initialize()
    yield checker_service
    await checker_service.shutdown()


@pytest.mark.asyncio
async def test_checker_service(checker_service):
    # for tracker in [HTTP_TRACKER_URL, UDP_TRACKER_URL, DHT_TRACKER_URL]:
    for tracker in [DHT_TRACKER_URL]:
        response = await checker_service.get_tracker_response(tracker, [SAMPLE_INFOHASH], timeout=1)
        print(response)

        assert response.torrent_health_list
        assert response.torrent_health_list[0].seeders >= 0
        assert response.torrent_health_list[0].leechers >= 0


@pytest.mark.asyncio
async def test_unknown_tracker(checker_service):
    unknown_tracker_url = "whatever://tracker.com"
    with pytest.raises(TrackerException):
        _ = await checker_service.get_tracker_response(unknown_tracker_url, [SAMPLE_INFOHASH], timeout=1)


@pytest.mark.asyncio
async def test_get_health_info(checker_service):
    tracker_urls = [HTTP_TRACKER_URL, UDP_TRACKER_URL, DHT_TRACKER_URL]
    response = await checker_service.get_health_info(SAMPLE_INFOHASH, tracker_urls, timeout=1)

    assert response is not None
    assert response.seeders >= 0
    assert response.leechers >= 0
