import datetime
import json
import logging
import time
import urllib
from leveldb import LevelDB
from twisted.web import server

import psutil
from twisted.internet import reactor, endpoints
from twisted.internet.task import LoopingCall
from twisted.web.resource import Resource
from twisted.web.server import Site

from Tribler.fingerprint.scheduler import CrawlerScheduler

DB = LevelDB('statistics', create_if_missing=True)
CRAWLER_URL = "http://localhost:8085"


def pp_seconds(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    years, days = divmod(days, 365)
    out = ""
    if years > 0:
        out = str(years) + (" years" if years > 1 else " year")
    if days > 0:
        if out:
            out += ", "
        out += str(days) + (" days"  if days > 1 else " day")
    if hours > 0:
        if out:
            out += ", "
        out += str(hours) + (" hours" if hours > 1 else " hour")
    if minutes > 0:
        if out:
            out += ", "
        out += str(minutes) + (" minutes" if minutes > 1 else " minute")
    if seconds > 0:
        if out:
            out += ", "
        out += str(seconds) + (" seconds"  if seconds > 1 else " second")
    return out


def get_uptime():
    for pid in psutil.pids():
        p = psutil.Process(pid)
        cmd = p.cmdline()
        if (len(cmd) > 1) and (cmd[0].endswith('python')) and (cmd[1] == 'ipv8_service.py'):
            return pp_seconds(time.time() - p.create_time())
    return ""


class StatsEndpoint(Resource):

    def __init__(self, db):
        self.db = db

    def render_GET(self, request):
        try:
            count = int(self.db.Get(b"count"))
        except KeyError:
            count = 0

        try:
            countries = json.loads(self.db.Get(b"geo"))
        except KeyError:
            countries = dict()

        try:
            services = json.loads(self.db.Get(b"services"))
        except KeyError:
            services = dict()

        response_data = dict()
        response_data['countries'] = countries
        response_data['services'] = services
        response_data['unique'] = count
        response_data['uptime'] = get_uptime()

        request.responseHeaders.addRawHeader(b"content-type", b"application/json")
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
        self.setHeader('Access-Control-Max-Age', 2520)
        self.setHeader('Content-type', 'application/json')
        if not self.finished and self.channel:
            server.Request.write(self, data)


if __name__ == "__main__":
    scheduler = CrawlerScheduler(CRAWLER_URL)
    lc = LoopingCall(scheduler.run)
    lc.start(20, now=True)

    root = Resource()
    root.putChild("stats", StatsEndpoint(DB))
    # root.putChild("peers", CurrentPeersEndpoint(DB))
    # root.putChild("unique", UniquePeersEndpoint(DB))
    # root.putChild("geo", GeoCountEndpoint(DB))
    # root.putChild("services", ServicesEndpoint(DB))
    factory = Site(root)
    factory.requestFactory = CorsRequest
    endpoint = endpoints.TCP4ServerEndpoint(reactor, 8880, interface="0.0.0.0")
    endpoint.listen(factory)
    reactor.run()
