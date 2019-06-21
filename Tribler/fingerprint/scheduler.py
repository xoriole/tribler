import datetime
import json
import logging
from leveldb import LevelDB
import urllib


class CrawlerScheduler(object):

    def __init__(self, crawler_url, db_name='statistics'):
        self.logger = logging.getLogger(__name__)
        self.base_url = crawler_url
        self.DB = LevelDB(db_name, create_if_missing=True)

        self.online = 0
        self.unique = 0

        self.geo_stats = dict()
        self.peer_stats = dict()
        self.service_stats = dict()

        self.service_to_type = dict()
        self.type_to_services = dict()

        self.service_to_version = dict()
        self.version_to_services = dict()

    def load_communities_ids(self, filename):
        indx = 0
        with open(filename, 'r') as fingerprint_file:
            for line in fingerprint_file:
                if line:
                    indx += 1
                    version, com_type, com_id = line.strip().split(":")
                    # self.service_to_type[com_id] = com_type
                    # self.service_to_version[com_id] = version

                    service_types = self.service_to_type.get(com_id, set())
                    service_types.add(com_type)
                    self.service_to_type[com_id] = service_types

                    service_versions = self.service_to_version.get(com_id, set())
                    service_versions.add(version)
                    self.service_to_version[com_id] = service_versions

                    type_services = self.type_to_services.get(com_type, set())
                    type_services.add(com_id)
                    self.type_to_services[com_type] = type_services

                    version_services = self.version_to_services.get(version, set())
                    version_services.add(com_id)
                    self.version_to_services[version] = version_services

    def fetch_geo_statistics(self):
        try:
            geo_response = urllib.urlopen("%s/crawler_geo" % self.base_url).read()
            self.geo_stats = json.loads(geo_response)
            self.DB.Put(b"geo", geo_response.encode('utf-8'))
        except Exception as e:
            self.logger.exception(e)

    def fetch_service_statistics(self):
        try:
            service_response = urllib.urlopen("%s/service" % self.base_url).read()
            self.service_stats = json.loads(service_response)
            self.DB.Put(b"services", service_response.encode('utf-8'))

            # timed services stat for future reference
            # service_key = "services-%s" % (int(time.time()))
            # db.Put(service_key.encode('utf-8'), services_raw)

        except Exception as e:
            self.logger.exception(e)

    def fetch_peer_statistics(self):
        try:
            peers_response = urllib.urlopen("%s/crawler_peers" % self.base_url).read()
            self.peer_stats = json.loads(peers_response)

            new_added = 0
            for peer in self.peer_stats:
                try:
                    self.DB.Get(peer.encode('utf-8'))
                except KeyError:
                    new_added += 1
                    self.DB.Put(peer.encode('utf-8'), b'True')
            try:
                count = int(self.DB.Get(b"count"))
            except KeyError:
                count = 0

            # Save current peers
            self.DB.Put(b"peers", peers_response)

            # Save count
            self.online = len(self.peer_stats)
            self.unique = count + new_added
            self.DB.Put(b"count", str(self.unique))

            # timed count for future reference
            count_key = "count-%s" % datetime.datetime.now().strftime("%Y-%m-%d-%H")
            self.DB.Put(count_key.encode('utf-8'), str(self.unique))

        except Exception as e:
            self.logger.exception(e)

    def get_geo_statistics(self):
        return self.geo_stats

    def get_peer_statistics(self):
        return self.peer_stats

    def get_peer_count(self):
        return self.online, self.unique

    def get_services_statistics(self):
        return self.service_stats

    def get_services_by_id(self, service_id):
        return {'service_type': self.service_to_type.get(service_id, set()),
                'version': self.service_to_version.get(service_id, set())}

    def get_services_by_version(self, version):
        return {service_id: ([version], self.service_to_type[service_id])
                for service_id in self.version_to_services.get(version, set())}

    def get_services_by_type(self, service_type):
        return {service_id: ([self.service_to_version[service_id]], [service_type])
                for service_id in self.type_to_services.get(service_type, set())}

    def get_services_by_version_and_type(self, version=None, service_type=None, service_id=None):
        services = dict()

        if version:
            for _service_id in self.version_to_services[version]:
                if service_type and not _service_id in self.type_to_services.get(service_type, set()):
                    continue
                services[_service_id] = {b'version': list(self.service_to_version[_service_id]),
                                        b'service_type': list(self.service_to_type[_service_id])}
        elif service_type:
            for _service_id in self.type_to_services[service_type]:
                services[_service_id] = {b'version': list(self.service_to_version[_service_id]),
                                        b'service_type': list(self.service_to_type[_service_id])}
        elif service_id:
            services[service_id] = {b'version': list(self.service_to_version[service_id]),
                                    b'service_type': list(self.service_to_type[service_id])}
        else:
            services = {service_id: {b'version': list(self.service_to_version[service_id]),
             b'service_type': list(self.service_to_type[service_id])} for service_id in self.service_to_version.keys()}

        return services

    def run(self):
        self.fetch_peer_statistics()
        self.fetch_geo_statistics()
        self.fetch_service_statistics()
