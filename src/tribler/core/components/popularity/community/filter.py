# Filter parameters
from typing import Any

from cuckoo.filter import ScalableCuckooFilter

FILTER_CAPACITY = 1000
FILTER_ERROR_RATE = 0.00001
FILTER_BUCKET_SIZE = 6


class PerPeerFilter:

    def __init__(self):
        self.filters = {}
        self.filter_fn = lambda x: False

    def get_filter_key(self, data_item):
        return data_item

    def _new_filter(self):
        return ScalableCuckooFilter(initial_capacity=FILTER_CAPACITY, error_rate=FILTER_ERROR_RATE,
                                    bucket_size=FILTER_BUCKET_SIZE)

    def add(self, peer, items: Any):
        peer_mid = str(peer.mid)
        filter = self.filters.get(peer_mid, self._new_filter())

        items = items if isinstance(items, list) else [items]
        for item in items:
            item_key = self.get_item_key(item)
            if not filter.contains(item_key):
                filter.insert(item_key)

        self.filters[peer_mid] = filter

    def exists(self, peer, key):
        filter = self.filters.get(str(peer.mid), None)
        return filter and filter.contains(key)

    def get_filter_instance(self, peer, create=False):
        peer_mid = str(peer.mid)
        default = None if not create else self._new_filter()
        filter = self.filters.get(str(peer.mid), default)
        return filter

    def get_item_key(self, item: Any):
        return item

    def is_filtered(self, filter, item: Any):
        item_key = self.get_item_key(item)
        if not filter.contains(item_key):
            return item
        return None

    def filter(self, peer, items: list, filter_fn=None):
        filter = self.get_filter_instance(peer)
        if not filter:
            return items

        if not filter_fn:
            filter_fn = lambda item: self.filter_fn(item)

        filtered_items = []
        for item in items:
            item_key = self.get_item_key(item)
            if filter.contains(item_key) or filter_fn(item):
                continue
            filtered_items.append(item)

        return filtered_items

    def prune(self, peers):
        peer_mids = [str(peer.mid) for peer in peers]
        for key in list(self.filters):
            if key not in peer_mids:
                self.filters.pop(key, None)


class PerPeerTorrentFilter(PerPeerFilter):

    def get_item_key(self, item: Any):
        infohash, seeders, leechers, last_check = item
        return infohash

    def filter_fn(self, item: Any):
        infohash, seeders, leechers, last_check = item
        if seeders == 0:
            return True
        return False