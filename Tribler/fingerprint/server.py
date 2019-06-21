import datetime
import json
import logging
import urllib
from leveldb import LevelDB
from twisted.web import server

from twisted.internet import reactor, endpoints
from twisted.internet.task import LoopingCall
from twisted.web.resource import Resource
from twisted.web.server import Site

from Tribler.fingerprint.scheduler import CrawlerScheduler
from Tribler.fingerprint.util import get_uptime

# DB = LevelDB('statistics', create_if_missing=True)
CRAWLER_URL = "http://localhost:8085"


# def cache_geo_stat():
#     try:
#         url = CRAWLER_URL + "/crawler_geo"
#         response = urllib.urlopen(url)
#         DB.Put(b"geo", response.read().encode('utf-8'))
#     except Exception as e:
#         logging.exception(e)
#
#
# def cache_service_stat():
#     try:
#         url = CRAWLER_URL + "/service"
#         response = urllib.urlopen(url)
#         services_raw = response.read().encode('utf-8')
#
#         # Save services stat
#         DB.Put(b"services", services_raw)
#
#         # timed services stat for future reference
#         # service_key = "services-%s" % (int(time.time()))
#         # db.Put(service_key.encode('utf-8'), services_raw)
#
#     except Exception as e:
#         logging.exception(e)
#
#
# def cache_peers():
#     try:
#         url = CRAWLER_URL + "/crawler_peers"
#         response = urllib.urlopen(url)
#         peers_raw = response.read()
#         print "peers:", peers_raw
#         peer_json = json.loads(peers_raw)
#
#         new_added = 0
#         for peer in peer_json:
#             try:
#                 DB.Get(peer.encode('utf-8'))
#             except KeyError:
#                 new_added += 1
#                 DB.Put(peer.encode('utf-8'), b'True')
#         try:
#             count = int(DB.Get(b"count"))
#         except KeyError:
#             count = 0
#
#         # Save current peers
#         DB.Put(b"peers", peers_raw)
#
#         # Save count
#         new_count_str = str(count + new_added)
#         DB.Put(b"count", new_count_str)
#
#         # timed count for future reference
#         count_key = "count-%s" % datetime.datetime.now().strftime("%Y-%m-%d-%H")
#         DB.Put(count_key.encode('utf-8'), new_count_str)
#     except Exception as e:
#         logging.exception(e)
#
#
# def schedule_job():
#     cache_peers()
#     cache_geo_stat()
#     cache_service_stat()


class UniquePeersEndpoint(Resource):

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def render_GET(self, request):
        count_response = {u'unique': self.scheduler.get_unique_peers()}
        request.responseHeaders.addRawHeader(b"content-type", b"application/json")
        return json.dumps(count_response)


class CurrentPeersEndpoint(Resource):

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def render_GET(self, request):
        request.responseHeaders.addRawHeader(b"content-type", b"application/json")
        return json.dumps(self.scheduler.get_peer_statistics())


class ServicesEndpoint(Resource):

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def render_GET(self, request):
        request.responseHeaders.addRawHeader(b"content-type", b"application/json")
        return json.dumps(self.scheduler.get_services_statistics())


class GeoCountEndpoint(Resource):

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def render_GET(self, request):
        request.responseHeaders.addRawHeader(b"content-type", b"application/json")
        return json.dumps(self.scheduler.get_geo_statistics())


class StatsEndpoint(Resource):

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def render_GET(self, request):
        response_data = dict()
        response_data['countries'] = self.scheduler.get_geo_statistics()
        response_data['services'] = self.scheduler.get_services_statistics()
        response_data['unique'] = self.scheduler.get_peer_count()[1]
        response_data['online'] = self.scheduler.get_peer_count()[0]
        response_data['uptime'] = get_uptime()

        request.responseHeaders.addRawHeader(b"content-type", b"application/json")
        return json.dumps(response_data)


class FingerprintEndpoint(Resource):

    def __init__(self, scheduler):
        self.scheduler = scheduler

    def render_GET(self, request):
        request.responseHeaders.addRawHeader(b"content-type", b"application/json")

        service_id = None
        service_type = None
        version = None

        if b'service_type' in request.args and len(request.args[b'service_type']):
            service_type = request.args[b'service_type'][0]

        if b'version' in request.args and len(request.args[b'version']):
            version = request.args[b'version'][0]

        if b'service_id' in request.args and len(request.args[b'service_id']):
            service_id = request.args[b'service_id'][0]

        response_data = self.scheduler.get_services_by_version_and_type(version=version, service_type=service_type, service_id=service_id)

        # response_data = dict()
        # if service_id:
        #     response_data = self.scheduler.get_services_by_id(service_id)
        # if service_type and version:
        #     response_data = self.scheduler.get_services_by_version_and_type(version, service_type)
        # elif service_type:
        #     response_data = self.scheduler.get_services_by_type(service_type)
        # elif version:
        #     response_data = self.scheduler.get_services_by_version(version)

        return json.dumps(response_data)


class CorsRequest(server.Request):
    """
    Extended request to support CORS.
    """
    defaultContentType = b"text/json"

    def __init__(self, *args, **kw):
        server.Request.__init__(self, *args, **kw)

    def write(self, data):
        """
        Enable CORS request before writing response
        """
        self.setHeader('Access-Control-Allow-Origin', '*')
        self.setHeader('Access-Control-Allow-Methods', 'GET')
        self.setHeader('Access-Control-Allow-Headers',
                       'x-prototype-version,x-requested-with')
        self.setHeader('Access-Control-Max-Age', '2520')
        self.setHeader('Content-type', 'application/json')
        if not self.finished and self.channel:
            server.Request.write(self, data)


if __name__ == "__main__":
    # lc = LoopingCall(schedule_job)
    # lc.start(20)
    scheduler = CrawlerScheduler(CRAWLER_URL)
    lc = LoopingCall(scheduler.run)
    lc.start(20, now=True)

    com_file = "Version-fingerprint.txt"
    scheduler.load_communities_ids(com_file)

    root = Resource()
    root.putChild("stats", StatsEndpoint(scheduler))
    root.putChild("peers", CurrentPeersEndpoint(scheduler))
    root.putChild("unique", UniquePeersEndpoint(scheduler))
    root.putChild("geo", GeoCountEndpoint(scheduler))
    root.putChild("services", ServicesEndpoint(scheduler))
    root.putChild("discovery", FingerprintEndpoint(scheduler))
    factory = Site(root)
    factory.requestFactory = CorsRequest
    endpoint = endpoints.TCP4ServerEndpoint(reactor, 8880, interface="0.0.0.0")
    endpoint.listen(factory)
    reactor.run()
