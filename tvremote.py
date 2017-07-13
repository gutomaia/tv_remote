#!/usr/bin/env python3
try:
    from http.client import HTTPConnection
except:
    from httplib import HTTPConnection

import xml.etree.ElementTree as etree
import socket
from re import search
from contextlib import closing
import xmltodict
import json

APP_TYPE_ALL=1
APP_TYPE_PREMIUM=2
APP_TYPE_MY_APPS=3

class NotFound(Exception):
    pass

class Unauthorized(Exception):
    pass

def ipaddress_required(func):
    def wrapper(self, *args, **kwargs):
        if self.ipaddress == None:
            self.ipaddress = self.resolve_ip()
        return func(self, *args, **kwargs)
    return wrapper

def auth_required(func):
    def wrapper(self, *args, **kwargs):
        if self.session_id == None:
            self.session_id = self.start_session()
        return func(self, *args, **kwargs)
    return wrapper

class TVRemote(object):
    headers = {"Content-Type": "application/atom+xml"}
    endline = '\r\n'

    def __init__(self, ipaddress=None, key=None):
        self.ipaddress = ipaddress
        self.key = key
        self.session_id = None
        self.connection = None

    def get_msearch(self):
        msearch = [
            'M-SEARCH * HTTP/1.1',
            'HOST: 239.255.255.250:1900',
            'MAN: "ssdp:discover"',
            'MX: 2',
            'ST: urn:schemas-upnp-org:device:MediaRenderer:1',
            'USER-AGENT: Linux UDAP/2.0 1',
        ]

        return self.endline.join(msearch) + 2 * self.endline


    def resolve_ip(self):
        request = self.get_msearch()
        request_bytes = request.encode()

        with closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
            sock.settimeout(3)
            for attempt in range(5):
                try:
                    sock.sendto(request_bytes, ('239.255.255.250', 1900))
                    gotbytes, addressport = sock.recvfrom(512)
                    gotstr = gotbytes.decode()
                    if search('lge', gotstr):
                        ipaddress, port = addressport
                        print ipaddress
                        return ipaddress
                except:
                    pass
        raise Exception('dammit')

    @ipaddress_required
    def get_connection(self):
        if self.connection == None or True:
            self.connection =  HTTPConnection(self.ipaddress, port=8080)
        return self.connection

    def get(self, url):
        conn = self.get_connection()
        conn.request('GET', url, headers=self.headers)
        return conn.getresponse()

    def post_xml(self, url, xml):
        conn = self.get_connection()
        conn.request('POST', url, xml, headers=self.headers)
        return conn.getresponse()

    def show_key(self):
        xml = '<auth><type>AuthKeyReq</type></auth>'
        res = self.post_xml('/roap/api/auth', xml)
        # if httpResponse.reason != "OK" : sys.exit("Network error")

    def start_session(self):
        print 'start_session'
        xml = '<auth><type>AuthReq</type><value>%s</value></auth>' % self.key
        res = self.post_xml('/roap/api/auth', xml)
        # if httpResponse.reason != "OK" : return httpResponse.reason
        # xml = res.read()
        tree = etree.XML(res.read())
        return tree.find('session').text


    @auth_required
    def send_inputkey(self, command, value):
        xml = (
            '<command>'
                '<name>HandleKeyInput</name>'
                '<value>%i</value>'
            '</command>'
            ) % command
        self.post_xml('/roap/api/command', xml)

    @auth_required
    def get_data(self, target, **kwargs):
        url = '/udap/api/data?target=%s' % target
        # url = '/roap/api/data?target=%s' % target
        if kwargs:
            url += '&' + '&'.join("%s=%s" % (key,val) for (key,val) in kwargs.iteritems())
        self.headers['User-Agent'] = 'UDAP/2.0'
        return self.get(url)

    def volume_up(self):
        return self.send_inputkey(24)

    def volume_down(self):
        return self.send_inputkey(25)

    def get_current_channel(self):
        return self.get_data('cur_channel')

    def get_channel_list(self):
        return self.get_data('channel_list')

    def get_volume_info(self):
        return self.get_data('volume_info')

    def get_schema(self):
        return self.get('/udap/api/data?target=rootservice.xml')

    def get_volume(self):
        res = self.get_volume_info()
        if res.status == 200:
            body = res.read()
            data = xmltodict.parse(body)
            return json.dumps(data)


            print body
            tree = etree.XML(body)
            level = tree.find('data/level')

            print level
            if level:
                return int(level.text)
        raise Exception('dd') #todo

    def get_terms(self):
        return self.get_data('termsAgree')

    def get_search(self):
        return self.get_data('SearchQRYEpgInfo')


    def get_applist(self, type=APP_TYPE_ALL, index=0, number=21):
        # self.headers['User-Agent'] = 'UDAP/2.0'
        return self.get_data('applist_get',
            type=type,
            index=index,
            number=number)

    def get_premium_apps(self):
        return self.get_applist(type=APP_TYPE_PREMIUM)

    def get_my_apps(self):
        return self.get_applist(type=APP_TYPE_MY_APPS)

    def app_execute(self, auid, appname, content_id):
        payload = """<envelope>
                <api type="command">
                    <name>AppExecute</name>
                    <auid>{auid}</auid>
                    <appname>{appname}</appname>
                    <contentId>{content_id}</contentId>
                </api>
            </envelope>""".format(
                auid=auid, appname=appname, content_id=content_id)
        return self.post_xml('/udap/api/command', payload)

    def app_terminate(self, auid, appname):
        payload = """<envelope>
                <api type="command">
                    <name>AppTerminate</name>
                    <auid>{auid}</auid>
                    <appname>{appname}</appname>
                </api>
            </envelope>""".format(
                auid=auid, appname=appname)
        return self.post_xml('/udap/api/command', payload)


    def get_appnum(self):
        return self.get_data('appnum_get',
            type=APP_TYPE_ALL)

    def set_volume(self, volume):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ipaddress, 8080))
        data = s.recv(2000)
        s.close()
        print "received data", data
        actual = self.get_volume()
        direction =  volume - actual
        for i in range(abs(direction)):
            if (direction > 0):
                self.volume_up()
            elif (direction < 0):
                self.volume_down()
