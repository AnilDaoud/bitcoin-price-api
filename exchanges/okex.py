from decimal import Decimal

import time, base64, hmac, json, hashlib, requests, uuid
from urllib.parse import urlparse

from exchanges.base import Exchange
from exchanges.ws import Exchange_WebSocket
import logging


class OKEx(Exchange):
    TICKER_URL = 'https://www.okex.com/api/v1'
    WS_TICKER_URL = 'wss://real.okex.com:10440/websocket/okexapi'
    stream = {}

    QUOTE_DICT = {
        'bid': 'buy',
        'ask': 'sell'
    }

    UNDERLYING_DICT = {
        'BTCUSD': 'btc_usd',
        'LTCUSD': 'ltc_usd',
        'ETHUSD': 'eth_usd',
        'ETCUSD': 'etc_usd',
        'BCHUSD': 'bch_usd'
    }

    def init_symbol(self, symbol):
        self.logger.setLevel(logging.INFO)
        if symbol in self.stream.keys():
            if (not self.stream[symbol].connected) or self.stream[symbol].exited:
                ws = Exchange_WebSocket(self.name, self.key, self.secret, self.logger)
                ws.connect(self.WS_TICKER_URL, symbol)
                self.stream[symbol] = ws
        else:
            self.stream[symbol] = Exchange_WebSocket(self.name, self.key, self.secret, self.logger)
            self.stream[symbol].connect(self.WS_TICKER_URL, symbol)
        return self.stream[symbol].connected

    def get_instrument(self, symbol):
        for s in self.stream.keys():
            if self.stream[s].connected:
                instruments = self.stream[s].data['instrument']
                m = [i for i in instruments if i['symbol'] == symbol]
                if len(m) == 0:
                    self.logger.error("No match for %s" % symbol)
                    continue
                i = m[0]
                i['tickLog'] = Decimal(str(i['tickSize'])).as_tuple().exponent * -1
                return i
        self.logger.error("No match for %s or no stream connected" % symbol)
        return None

    def get_quote(self, symbol, quote):
        i = self.get_instrument(symbol)
        if i is None:
            return None
        if i['symbol'][0] == '.':
            return i['markPrice']
        if quote.lower() == 'bid':
            return i['bidPrice']
        elif quote.lower() == 'ask':
            return i['askPrice']
        elif quote.lower() == 'last':
            return i['lastPrice']

    def get_stream(self, symbol):
        if symbol in self.stream.keys():
            if self.stream[symbol].connected:
                return self.stream[symbol].data
            else:
                self.logger.error("Stream %s not connected" % symbol)
                return None
        else:
            return None

    def get_balance(self):
        if self.stream is not None:
            # there might be a connected stream
            for symbol in self.stream.keys():
                if self.stream[symbol].connected:
                    return self.stream[symbol].data['margin'][0]
        return "Not connected"

    def get_depth(self, symbol, bid_size=0, ask_size=0):
        if symbol in self.stream.keys():
            if self.stream[symbol].connected:
                asks = self.stream[symbol].data['orderBook10'][0]['asks']
                bids = self.stream[symbol].data['orderBook10'][0]['bids']
                work_ask_size = 0
                ask = 0
                i = 0
                while (work_ask_size <= ask_size and i < len(asks)):
                    prev_size = work_ask_size
                    prev = prev_size * ask
                    work_ask_size += asks[i][1]
                    if ask_size != 0:
                        work_ask_size = min(ask_size, work_ask_size)
                    ask = ((work_ask_size - prev_size) * asks[i][0] + prev) / (work_ask_size)
                    i += 1
                work_bid_size = 0
                bid = 0
                i = 0
                while (work_bid_size <= bid_size and i < len(bids)):
                    prev_size = work_bid_size
                    prev = prev_size * bid
                    work_bid_size += bids[i][1]
                    if bid_size != 0:
                        work_bid_size = min(bid_size, work_bid_size)
                    bid = ((work_bid_size - prev_size) * bids[i][0] + prev) / (work_bid_size)
                    i += 1
                return [bid, ask, work_bid_size, work_ask_size]
        return [0, 0, 0, 0]

    def delete_order(self, order_id):
        self.logger.info("Cancelling order %s" % order_id)
        params = {'clOrdID': order_id}
        return self._send_request('order', 'DELETE', params)

    def place_order(self, symbol, quantity, price):
        if price < 0:
            self.logger.error("Price must be postive")
            return None
        clOrdID = self.name + base64.b64encode(uuid.uuid4().bytes).decode('utf-8').rstrip('=\n')
        params = {'symbol': symbol, 'orderQty': quantity, 'price': price, 'clOrdID': clOrdID}
        return self._send_request('order', 'POST', params)

    def buy(self, symbol, quantity, price):
        return self.place_order(symbol, quantity, price)

    def sell(self, symbol, quantity, price):
        return self.place_order(symbol, -quantity, price)

    def _send_request(self, command, httpMethod, params={}):
        contentType = "" if httpMethod == "GET" else "application/json"
        url = self.TICKER_URL + command
        now = time.time()
        nonce = int(round(now * 1000))
        data = json.dumps(params)
        parsedURL = urlparse(url)
        path = parsedURL.path
        if parsedURL.query:
            path = path + '?' + parsedURL.query
        message = httpMethod + path + str(nonce) + data
        if self.get_secret() == None:
            self.logger.error("Credentials not found. Check your config.ini")
            self.error = "AuthFailed"
            return None
        signature = hmac.new(self.get_secret().encode(), message.encode(), digestmod=hashlib.sha256).hexdigest()
        headers = {
            'api-nonce': str(nonce),
            'api-key': self.get_key(),
            'api-signature': signature,
            'Content-Type': contentType
        }
        if httpMethod == 'DELETE':
            R = requests.delete
        elif httpMethod == 'GET':
            R = requests.get
        elif httpMethod == 'POST':
            R = requests.post
        try:
            response = R(url, data=data, headers=headers)
        except requests.exceptions.ConnectionError as err:
            self.logger.debug("command: %r" % command)
            self.logger.debug("url: %r" % url)
            self.logger.debug("headers: %r" % headers)
            self.logger.debug("params: %r" % params)
            self.logger.debug("message: %r" % message)
            self.logger.debug("data: %r" % data)
            self.logger.error(err)
            return None
        try:
            return response.json()
        except ValueError as err:
            self.logger.error(str(url) + ":" + str(response) + ", " + str(err))
            return None
