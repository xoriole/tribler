from typing import Any

from cuckoo.filter import ScalableCuckooFilter

# Filter parameters
FILTER_CAPACITY = 1000
FILTER_ERROR_RATE = 0.00001
FILTER_BUCKET_SIZE = 6


class PerPeerFilter:

    def __init__(self):
        self.filters = {}

    def _new_filter(self):
        return ScalableCuckooFilter(initial_capacity=FILTER_CAPACITY, error_rate=FILTER_ERROR_RATE,
                                    bucket_size=FILTER_BUCKET_SIZE)

    def add(self, peer, items: Any):
        """
        Adds a list of items to the cuckoo filter of the peer.
        """
        peer_mid = str(peer.mid)
        filter = self.filters.get(peer_mid, self._new_filter())

        items = items if isinstance(items, list) else [items]
        for item in items:
            item_key = self.get_item_key(item)
            if not filter.contains(item_key):
                filter.insert(item_key)

        self.filters[peer_mid] = filter

    def exists(self, peer, key):
        """
        Checks if the key exists in the filter associated with the peer.
        """
        filter = self.filters.get(str(peer.mid), None)
        return filter and filter.contains(key)

    def get_item_key(self, item: Any):
        """
        Returns the key derived from the item that will be used in the cuckoo filter.
        """
        return item

    def filter(self, peer, items: list):
        """
        Returns items that are not present in the filter.
        """
        filter = self.filters.get(str(peer.mid), None)
        if not filter:
            return items

        return [item for item in items if not filter.contains(self.get_item_key(item))]

    def prune(self, peers):
        """
        Prune filters associated with peers that are not present anymore.
        """
        peer_mids = [str(peer.mid) for peer in peers]
        for key in list(self.filters):
            if key not in peer_mids:
                self.filters.pop(key, None)


class PerPeerTorrentFilter(PerPeerFilter):

    def get_item_key(self, item: Any):
        infohash, seeders, leechers, last_check = item
        return infohash
