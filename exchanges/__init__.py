from exchanges.bitbay import BitBay
from exchanges.bitfinex import Bitfinex
from exchanges.bitflyer import BitFlyer
from exchanges.bitmex import BitMEX
from exchanges.bitstamp import Bitstamp
from exchanges.bittrex import Bittrex
from exchanges.cexio import CexIO
from exchanges.gatecoin import GateCoin
from exchanges.gdax import GDAX
from exchanges.gemini import Gemini
from exchanges.hitbtc import HitBTC
from exchanges.kraken import Kraken
from exchanges.liqui import Liqui
from exchanges.okcoin import OKCoin
from exchanges.okex import OKEx
from exchanges.poloniex import Poloniex

exchange_list = {
    'bitbay' : BitBay,
    'bitfinex' : Bitfinex,
    'bitflyer' : BitFlyer,
    'bitstamp' : Bitstamp,
    'bittrex' : Bittrex,
    'cex.io' : CexIO,
    'gatecoin' : GateCoin,
    'gdax' : GDAX,
    'gemini' : Gemini,
    'hitbtc' : HitBTC,
    'kraken' : Kraken,
    'liqui' : Liqui,
    'okcoin' : OKCoin,
    'poloniex' : Poloniex
}

fut_exchange_list = {
    'bitmex' : BitMEX,
    'okex' : OKEx
}

def get_exchange(s, *args, **kwargs):
    if s not in exchange_list and s not in fut_exchange_list:
        raise RuntimeError
    else:
        if s in exchange_list:
            return exchange_list[s](s, *args, **kwargs)
        else:
            return fut_exchange_list[s](s, *args, **kwargs)

def get_exchanges_list():
    return sorted(exchange_list.keys())

def get_exchanges_list_for_underlying(underlying):
    exchange_list_filtered = []
    for exchange in get_exchanges_list():
        if underlying in get_exchange(exchange).get_supported_underlyings():
            exchange_list_filtered.append(exchange)
    return exchange_list_filtered

def get_underlyings_list():
    underlying_list = []
    for exchange in get_exchanges_list():
        if not set(get_exchange(exchange).get_supported_underlyings()).issubset(set(underlying_list)):
            underlying_list += get_exchange(exchange).get_supported_underlyings()
    return list(set(underlying_list))

def get_all_quotes(underlyingList = []):
    if underlyingList == []:
        exchangeList = get_exchanges_list()
    else:
        exchangeList = []
        for underlying in underlyingList:
            exchangeList += get_exchanges_list_for_underlying(underlying)
        exchangeList = list(set(exchangeList))
    print(exchangeList)
    for exchange in exchangeList:
        e = get_exchange(exchange)
        if e.get_supported_underlyings() == []:
            print("%s has no supported underlyings" % exchange)
        else:
            if underlyingList == []:
                underlyingList = e.get_supported_underlyings()
            for underlying in underlyingList:
                last = e.get_quote(underlying, 'last')
                bid = e.get_quote(underlying, 'bid')
                ask = e.get_quote(underlying, 'ask')
                print("%s on %s: BID: %s, ASK: %s, LAST: %s" % (underlying, exchange, bid, ask, last))

