from exchanges.bitbay import BitBay
from exchanges.bitfinex import Bitfinex
from exchanges.bitstamp import Bitstamp
from exchanges.bittrex import Bittrex
from exchanges.cexio import CexIO
from exchanges.coinapult import Coinapult
from exchanges.gatecoin import GateCoin
from exchanges.hitbtc import HitBTC
from exchanges.kraken import Kraken
from exchanges.okcoin import OKCoin
from exchanges.poloniex import Poloniex

exchange_list = {
    'bitbay' : BitBay,
    'bitfinex' : Bitfinex,
    'bitstamp' : Bitstamp,
    'bittrex' : Bittrex,
    'cex.io' : CexIO,
    'coinapult' : Coinapult,
    'hitbtc' : HitBTC,
    'kraken' : Kraken,
    'okcoin' : OKCoin,
    'poloniex' : Poloniex,
    'gatecoin' : GateCoin
}

def get_exchange(s, *args, **kwargs):
    if s not in exchange_list:
        raise RuntimeError
    else:
        return exchange_list[s](*args, **kwargs)

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
    return underlying_list

def get_last_price_all():
    for exchange in get_exchanges_list():
        e = get_exchange(exchange)
        if e.get_supported_underlyings() == []:
            print("%s has no supported underlyings" % exchange)
        else:
            for underlying in e.get_supported_underlyings():
                last = e.get_last_price(underlying)
                bid = e.get_current_bid(underlying)
                ask = e.get_current_ask(underlying)
                print("%s on %s: BID: %.2f, ASK: %.2f, LAST: %.2f" % \
                      (underlying, exchange, bid, ask, last))
