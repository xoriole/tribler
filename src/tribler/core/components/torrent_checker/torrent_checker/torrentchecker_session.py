from __future__ import annotations

from tribler.core.components.torrent_checker.torrent_checker.session.http_tracker import HttpTrackerSession
from tribler.core.components.torrent_checker.torrent_checker.session.tracker import TrackerSession
from tribler.core.components.torrent_checker.torrent_checker.session.udp_tracker import UdpTrackerSession
from tribler.core.utilities.tracker_utils import parse_tracker_url


def create_tracker_session(tracker_url, timeout, proxy, socket_manager) -> TrackerSession:
    """
    Creates a tracker session with the given tracker URL.
    :param tracker_url: The given tracker URL.
    :param timeout: The timeout for the session.
    :return: The tracker session.
    """
    tracker_type, tracker_address, announce_page = parse_tracker_url(tracker_url)

    if tracker_type == 'udp':
        return UdpTrackerSession(tracker_url, tracker_address, announce_page, timeout, proxy, socket_manager)
    return HttpTrackerSession(tracker_url, tracker_address, announce_page, timeout, proxy)
