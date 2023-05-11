from tribler.core.components.torrent_checker.torrent_checker.trackers import TrackerException


class EmptyResponseException(TrackerException):
    def __init__(self):
        super().__init__("No response body")


class InvalidResponseException(TrackerException):
    def __init__(self):
        super().__init__("Invalid bencoded response")


class ExceptionWithReason(TrackerException):
    def __init__(self, failure_reason):
        super().__init__(repr(failure_reason))


class TimeoutException(TrackerException):
    def __init__(self, timeout):
        super().__init__(f"Failed to get tracker response in {timeout} seconds")


class InvalidTrackerURL(TrackerException):
    def __init__(self, tracker_url):
        super().__init__(f"Invalid tracker URL: {tracker_url}")


class InvalidHttpResponse(TrackerException):
    def __init__(self, status):
        super().__init__(f"HTTP Error {status}")


# TrackerException("UDP socket transport is not ready yet")
class UDPSocketTransportNotReady(TrackerException):
    def __init__(self):
        super().__init__("UDP socket transport is not ready yet")
