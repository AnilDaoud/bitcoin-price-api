import websocket
import threading
import logging
import time
import hmac
from urllib.parse import urlparse, urlunparse
import hashlib
from time import sleep
import json
import traceback

class Exchange_WebSocket(object):

    MAX_TABLE_LEN = 200

    def __init__(self, exchangeName, key, secret, loggerObject = None, *args, **kwargs):
        if type(loggerObject) is not logging.getLoggerClass():
            print("New Logger")
            self.logger = logging.getLogger(exchangeName)
            # default log to stdout. override this if needed
            self.logger.setLevel(logging.DEBUG)
            lh = logging.StreamHandler()
            lh.setFormatter(logging.Formatter("%(asctime)s [%(threadName)-12.12s] [%(levelname)-5.5s]  %(message)s"))
            self.logger.addHandler(lh)
        else:
            self.logger = loggerObject
        self.ws = None
        self.key = key
        self.secret = secret
        self.data = {}
        self.keys = {}
        self.exited = False
        self._error = None
        self.connected = False

    def get_key(self):
        return self.key

    def get_secret(self):
        return self.secret

    def exit(self):
        self.exited = True
        if self.ws is not None:
            self.ws.close()
        self.connected = False

    def error(self, err):
        self._error = err
        self.logger.error(err)
        self.exit()

    def connect(self, endpoint = "", symbol = "XBTU17"):
        self.symbol = symbol
        subscriptions = [sub + ":" + symbol for sub in ['quote', 'trade', 'orderBook10']]
        subscriptions += ['instrument']
        # requires Auth
        subscriptions += [sub + ":" + symbol for sub in ['order', 'execution']]
        subscriptions += ['margin', 'position']
        self.logger.info("Subscribing to %s" % subscriptions)
        urlParts = list(urlparse(endpoint))
        urlParts[0] = urlParts[0].replace('http','ws')
        urlParts[2] = "/realtime?subscribe=" + ",".join(subscriptions)
        wsURL = urlunparse(urlParts)
        self.logger.info("Connecting to %s" % wsURL)
        self.__connect(wsURL)
        if not self.exited:
            self.logger.info("Connected to WS. Waiting for data images, could take a while")
            self.__wait_for_symbol(symbol)
            self.__wait_for_account()
            self.logger.info("Got all market data. Starting")
            self.connected = True

    def __wait_for_account(self):
        while not {'margin','position','order'} <= set(self.data):
            sleep(0.1)

    def __wait_for_symbol(self, symbol):
        while not {'instrument','trade','order'} <= set(self.data):
            sleep(0.1)

    def __connect(self, wsURL):
        # to use for debugging
        #websocket.enableTrace(True)
        self.ws = websocket.WebSocketApp(wsURL, on_message = self.__on_message, on_close = self.__on_close, on_open = self.__on_open, on_error = self.__on_error, header = self.__get_auth())
        self.wst = threading.Thread(target = lambda: self.ws.run_forever())
        self.wst.daemon = True
        self.wst.start()
        self.logger.info("Started thread")

        # wait for connect before continuing
        conn_timeout = 10
        while(not self.ws.sock or not self.ws.sock.connected) and conn_timeout and not self._error:
            sleep(1)
            conn_timeout -= 1
            self.logger.debug(conn_timeout)

        if not conn_timeout or self._error:
            self.logger.error("Couldn't connect to WS")
            self.exit()
            return

    def __on_error(self, error):
        if not self.exited:
            self.error(error)

    def __get_auth(self):
        self.logger.info("Authenticating to WS with API Key")
        if self.get_secret() == None or self.get_secret() == "":
            self.logger.error("Credentials not found. Check your config.ini")
            self.error("AuthFailed")
            return None
        nonce = self.generate_nonce()
        return ["api-nonce: " + str(nonce), "api-signature: " + self.generate_signature(self.secret, 'GET', '/realtime', nonce, ''), "api-key: " + self.key]

    def __on_message(self, message):
        message = json.loads(message)
        self.logger.debug(json.dumps(message))

        table = message['table'] if 'table' in message else None
        action = message['action'] if 'action' in message else None

        try:
            if 'subscribe' in message:
                if message['success']:
                    self.logger.debug("Subscribed to %s." % message['subscribe'])
                else:
                    self.error("Unable to subscribe to %s. Error '%s'. Please check and restart." % (message['request']['args'][0], message['error']))
            elif 'status' in message:
                if message['status'] == 400:
                    self.error(message['error'])
                if message['status'] == 401:
                    self.error("API Key incorrect, please check and restart")
            elif action:
                if table not in self.data:
                    self.data[table] = []
                if table not in self.keys:
                    self.keys[table] = []

                if action == 'partial':
                    self.logger.debug("%s: partial" % table)
                    self.data[table] += message['data']
                    self.keys[table] = message['keys']
                elif action == 'insert':
                    self.logger.debug("%s: inserting %s" % (table, message['data']))
                    self.data[table] += message['data']
                    if table != 'order' and len(self.data[table]) > Exchange_WebSocket.MAX_TABLE_LEN:
                        self.data[table] = self.data[table][(Exchange_WebSocket.MAX_TABLE_LEN // 2):]
                elif action == 'update':
                    self.logger.debug('%s: updating %s' % (table, message['data']))
                    for updateData in message['data']:
                        item = self.findItemByKeys(self.keys[table], self.data[table], updateData)
                        if not item:
                            continue
                        if table == 'order':
                            is_canceled = 'ordStatus' in updateData and updateData['ordStatus'] == 'Canceled'
                            if 'cumQty' in updateData and not is_canceled:
                                contExecuted = updateData['cumQty'] - item['cumQty']
                                if contExecuted > 0:
                                    instrument = self.get_instrument(item['symbol'])
                                    self.logger.info("Execution: %s %d Contracts of %s at %.*f" % (item['side'], contExecuted, item['symbol'], instrument['tickLog'], item['price']))
                        item.update(updateData)
                        if table == 'order' and item['leavesQty'] <= 0:
                            self.data[table].remove(item)
                elif action == 'delete':
                    self.logger.debug('%s: deleting %s' % (table, message['data']))
                    for deleteData in message['data']:
                        item = self.findItemByKeys(self.keys[table], self.data[table], deleteData)
                        self.data[table].remove(item)
                else:
                    raise Exception("Uknown action: %s" % action)
        except:
            self.logger.error(traceback.format_exc())

    def __on_close(self):
        self.logger.info("Websocket Closed")
        self.exit()

    def __on_open(self):
        self.logger.debug("Websocket Opened")

    def generate_nonce(self):
        return int(round(time.time() * 1000))

    def generate_signature(self, secret, verb, url, nonce, data):
        parsedURL = urlparse(url)
        path = parsedURL.path
        if parsedURL.query:
            path = path + '?' + parsedURL.query
        message = verb + path + str(nonce) + data
        signature = hmac.new(bytes(secret, 'utf8'), bytes(message, 'utf8'), digestmod=hashlib.sha256).hexdigest()
        return signature

    def findItemByKeys(self, keys, table, matchData):
        for item in table:
            matched = True
            for key in keys:
                if item[key] != matchData[key]:
                    matched = False
            if matched:
                return item


