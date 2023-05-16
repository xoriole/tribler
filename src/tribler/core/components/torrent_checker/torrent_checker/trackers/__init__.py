

class Tracker:

    async def init(self, *args, **kwargs):
        pass

    async def shutdown(self):
        pass

    def is_supported_url(self, tracker_url: str):
        pass

    async def get_tracker_response(self, tracker_url, infohashes, timeout=5):
        pass

    async def get_torrent_health(self, tracker_url, infohash, timeout=5):
        pass


class TrackerException(Exception):

    def __init__(self, msg="Failed to get tracker response"):
        super(TrackerException, self).__init__(msg)
