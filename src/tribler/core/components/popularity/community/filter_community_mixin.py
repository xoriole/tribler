# Filter parameters
from typing import Any

from cuckoo.filter import ScalableCuckooFilter

FILTER_CAPACITY = 1000
FILTER_ERROR_RATE = 0.00001
FILTER_BUCKET_SIZE = 6


class FilterCommunityMixin:
    """
    This mixin adds support for storing state in the community based on cuckoo filter.
    """

    def __init__(self):
        self.peer_torrents_filters = {}

    def init_filters(self):
        pass

    def get_peers(self):
        raise NotImplementedError("Not implemented...")

    def new_filter(self):
        return ScalableCuckooFilter(initial_capacity=FILTER_CAPACITY, error_rate=FILTER_ERROR_RATE,
                                    bucket_size=FILTER_BUCKET_SIZE)

    def add_to_filter(self, peer, key: Any):
        peer_mid = str(peer.mid)
        filter = self.peer_torrents_filters.get(str(peer.mid), self.new_filter())
        if isinstance(key, list):
            for _key in key:
                filter.insert(_key)
        else:
            filter.insert(key)

        self.peer_torrents_filters[peer_mid] = filter

    def exists_in_filter(self, peer, key):
        filter = self.peer_torrents_filters.get(str(peer.mid), self.new_filter())
        return filter.contains(key)

    def get_filter(self, peer):
        peer_mid = str(peer.mid)
        filter = self.peer_torrents_filters.get(str(peer.mid), self.new_filter())
        return filter


