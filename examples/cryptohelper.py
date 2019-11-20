#!/usr/bin/env python3

import sys
import slack
from telegram import InlineQueryResultArticle,InputTextMessageContent
from telegram.ext import Updater
from telegram.ext import CommandHandler, MessageHandler, Filters, InlineQueryHandler
from uuid import uuid4
import logging
import exchanges
import requests
import math
from datetime import datetime, timedelta
import re
import time

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s-%(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOTNAME = '@BotName_Bot'
TOKEN = 'TELEGRAMTOKEN'
CL_API_KEY = 'CLAPIKEY'
SLACK_BOT_TOKEN = "SLACKTOKEN"
SLACK_MENTION_REGEX = "^<@(|[WU].+?)>(.*)"

millnames = ['',' k',' mio',' bio',' trillion']

bm = exchanges.get_exchange('bitmex')

def millify(n):
    try:
        n = float(n)
    except:
        n = 0
    millidx = max(0,min(len(millnames)-1, int(math.floor(0 if n == 0 else math.log10(abs(n))/3))))
    return '{:.1f}{}'.format(n / 10**(3 * millidx), millnames[millidx])

def startMsg(update, context):
    context.bot.send_message(chat_id=update.message.chat_id, text="Type /list to get a list of supported exchanges and underlyings.\nType /price <underlying> <exchange> to retrieve a price.\nFor example /price btcusd kraken")

def bitmexMsg(update, context):
    logger.info("Received /bitmex command from %s" % update.effective_user)
    if update.message.text.split().__len__()<=1:
        context.bot.send_message(chat_id=update.message.chat_id, text="Syntax is /bitmex <future>. For example /bitmex XBTH18")
    else:
        futlist  = update.message.text.upper().split()[1:]
        message_text = ""
        for i, fut in enumerate(futlist):
            message_text+=bitmex(fut)
            if i != len(futlist)-1:
                message_text+='\n------------\n'
        update.message.reply_text(message_text)

def bitmex(fut):
    if len(fut) == 3:
        fut = 'XBT'+fut
    if fut[:3] == 'XBT':
        exch = ['gdax', 'bitstamp']
        spot = 'BTCUSD'
    else:
        exch = ['poloniex','bittrex']
        spot = fut[:3] + 'BTC'
    fut_stream = bm.get_stream(fut)
    if fut_stream == None:
        fut_stream = bm.init_symbol(fut)
    fut_bid = bm.get_quote(fut, 'bid')
    fut_ask = bm.get_quote(fut, 'ask')
    if fut_bid == None or fut_ask == None:
        message = "Something went wrong, check future code " + fut
        return message
    expiry = bm.get_instrument(fut)['expiry']
    nowdate = datetime.now()
    if expiry is None:
        expdate = nowdate
    else:
        expdate = datetime.strptime(bm.get_instrument(fut)['expiry'],'%Y-%m-%dT%H:%M:%S.%fZ')
    yearstoexp = (expdate - nowdate).total_seconds()/3600/24/365.25
    spot_bid = 0
    spot_ask = 0
    i = 0
    for en in exch:
        e = exchanges.get_exchange(en)
        if spot in e.get_supported_underlyings():
            spot_bid += e.get_quote(spot, 'bid')
            spot_ask += e.get_quote(spot, 'ask')
            i+=1
    spot_bid = float(spot_bid / i)
    spot_ask = float(spot_ask / i)
    basis_bid = fut_bid - spot_ask
    basis_ask = fut_ask - spot_bid
    spot_mid = (spot_bid + spot_ask)/2
    fut_mid = (fut_ask + fut_bid)/2
    basis_mid = (basis_ask + basis_bid)/2
    message = ""
    if basis_ask < 0:
        basis_premium = 100 * basis_ask / spot_mid
    elif spot_mid != 0:
        basis_premium = 100 * basis_bid / spot_mid
    else:
        basis_premium = 0
        message += "Couldn't find supported exchange for spot price.\n"
    if yearstoexp == 0:
        annualized_premium = 0
    else:
        annualized_premium = 100*((1+basis_premium/100)**(1/yearstoexp)-1)
    if spot_bid > 1:
        message += "Spot %s price is %.2f: %.2f / %.2f" % (spot, spot_mid, spot_bid, spot_ask) + '\n'
        message += "Fut %s price is %.2f: %.2f / %.2f" % (fut, fut_mid, fut_bid,fut_ask) + '\n'
        message += "Basis is %.2f: %.2f / %.2f. Premium of %.1f%%" % (basis_mid, basis_bid, basis_ask, basis_premium)
    else:
        message += "Spot %s price is %.4g: %.4g / %.4g" % (spot, spot_mid, spot_bid, spot_ask) + '\n'
        message += "Fut %s price is %.4g: %.4g / %.4g" % (fut,fut_mid, fut_bid, fut_ask) + '\n'
        message += "Basis is %.4g: %.4g / %.4g. Premium of %.1f%%" % (basis_mid, basis_bid, basis_ask, basis_premium)
    if annualized_premium !=0:
        message += " (%.1f%% annualised)" % annualized_premium
    return message

def unknownMsg(update, context):
    logger.info("Received unknown command from %s: %s" % (update.effective_user, update.message.text))
    context.bot.send_message(chat_id=update.message.chat_id, text="Sorry, try /start again?")

def listExchangesMsg(update, context):
    logger.info("Received /list command from %s" % update.effective_user)
    update.message.reply_text(list_text())

def list_text():
    exchange_text = 'List of supported exchanges:\n'+'\n'.join(sorted(exchanges.exchange_list.keys()))
    underlyings_text = 'List of available underlyings:\n'+'\n'.join(sorted(exchanges.get_underlyings_list()))
    end_text = 'Try /exchange <exchange> to price all underlyings availablle on an exchange'
    return exchange_text + '\n\n' + underlyings_text + '\n\n' + end_text

def summaryMsg(update, context):
    logger.info("Received /summary command from %s" % update.effective_user)
    logger.info("Command content: %s" % update.message.text)
    if update.message.text.split().__len__() <= 1:
        ccy = ['globalsummary']
    else:
        ccy = update.message.text.split()[1:]
    update.message.reply_text('\n'.join(summary(ccy)))

def summary(ccy_list):
    mapping = {
        'btc' : 'bitcoin',
        'eth' : 'ethereum',
        'snt' : 'status',
        'xrp' : 'ripple',
        'xmr' : 'monero',
        'gno' : 'gnosis-gno',
        'gnosis' : 'gnosis-gno',
        'pay' : 'tenx',
        'cvc' : 'civic',
        'dnt' : 'district0x',
        'san' : 'santiment',
        'omg' : 'omisego',
        'zerox' : '0x',
        'request' : 'request-network',
        'req' : 'request-network',
        'bch' : 'bitcoin-cash',
        'cash' : 'cash-poker-pro',
        'zec' : 'zcash',
        'lgo' : 'legolas-exchange',
        'legolas' : 'legolas-exchange',
        'xlm' : 'stellar',
        'zrx' : '0x'
    }
    results = []
    for ccy in ccy_list:
        ccy = ccy.lower()
        url = 'https://api.coinmarketcap.com/v1/ticker/%s' % ccy
        if ccy in mapping.keys():
            ccy = mapping[ccy]
            url = 'https://api.coinmarketcap.com/v1/ticker/%s' % ccy
        elif ccy == 'globalsummary':
            url = 'https://api.coinmarketcap.com/v1/global/'
        try:
            r = requests.get(url)
            r.raise_for_status()
            j = r.json()
        except requests.exceptions.RequestException as err:
            print(err)
            results.append("Something went wrong for currency %s" % ccy)
            results.append('')
            continue
        if ccy == 'globalsummary':
            mkt_cap_usd = millify(j['total_market_cap_usd'])
            vol_usd = millify(j['total_24h_volume_usd'])
            btc_pct = j['bitcoin_percentage_of_market_cap']
            nb_ccy = int(j['active_currencies']) + int(j['active_assets'])
            results.append('Total crypto market cap: %s (USD)' % mkt_cap_usd)
            results.append('Last 24h volume: %s (USD)'% vol_usd)
            results.append('Bitcoin share of total market cap: %s%%' % btc_pct)
            results.append('Number of tokens in circulation: %s' % nb_ccy)
        else:
            name = j[0]['name']
            price_usd = j[0]['price_usd']
            price_btc = j[0]['price_btc']
            vol_usd = millify(j[0]['24h_volume_usd'])
            mktcap_usd = millify(j[0]['market_cap_usd'])
            rank = int(j[0]['rank'])
            pchg_1h = j[0]['percent_change_1h']
            pchg_24h = j[0]['percent_change_24h']
            pchg_7d = j[0]['percent_change_7d']
            results.append('%s: %s (USD), %s (BTC). Changes: %s%% (1h), %s%% (24h), %s%% (7d).' % (name, price_usd, price_btc, pchg_1h, pchg_24h, pchg_7d))
            if str(rank)[-1:] == '1' and str(rank)[-2:] != '11':
                suffix = 'st'
            elif str(rank)[-1:] == '2' and str(rank)[-2:] != '12':
                suffix = 'nd'
            elif str(rank)[-1:] == '3' and str(rank)[-2:] != '13':
                suffix = 'rd'
            else:
                suffix = 'th'
            results.append('%s: Volumes in past 24h: %s USD. Market cap: %s USD. %s%s market cap.' % (name, vol_usd, mktcap_usd, rank, suffix))
            results.append('')
    return results

def exchangeMsg(update, context):
    logger.info("Received /exchange command from %s" % update.effective_user)
    logger.info("Command content: %s" % update.message.text)
    if update.message.text.split().__len__() <= 1:
        update.message.reply_text('Syntax is "/exchange <exchange1> <exchange2> <...>".\nTry "/exchange all" to price all underlying on all supported exchanges (can take a while).\nType /list to see supported exchanges')
        return
    exchange_list = update.message.text.split()[1:]
    if exchange_list == ['all']:
        exchange_list = exchanges.get_exchanges_list()
    update.message.reply_text('\n'.join(exchange(exchange_list)))

def exchange(exchange_list):
    results = []
    for en in exchange_list:
        try:
            e = exchanges.get_exchange(en.lower())
        except:
            results.append("Uknown exchange %s" % en)
            continue
        results.append("%s:\n" % en)
        for ul in e.get_supported_underlyings():
            bid = e.get_quote(ul,'bid')
            ask = e.get_quote(ul,'ask')
            last = e.get_quote(ul,'last')
            if bid == 0 or ask == 0:
                spread = 1
            else:
                spread = (ask - bid) / ((ask+bid)/2)
            if last > 1:
                results.append("%s: Last trade %.2f. Market %.2f/ %.2f (%.1f%% wide)" % (ul,last, bid, ask, spread * 100))
            else:
                results.append("%s: Last trade %.3g. Market %.3g / %.3g (%.1f%% wide)" % (ul,last, bid, ask, spread * 100))
        results.append("--------------")
    return results

def price(underlying, exchange_list):
    if underlying == 'BITCOIN':
        underlying = 'BTCUSD'
    all_requested = False
    if exchange_list == ['all']:
        all_requested = True
        exchange_list = exchanges.get_exchanges_list_for_underlying(underlying)
    if exchange_list == []:
        return ['No exchange support %s' % underlying]
    bestbid = 0.00000001
    bestask = 1000000000
    bestspread = 100
    bestbid_exch = exchange_list[0]
    bestask_exch = exchange_list[0]
    bestspread_exch = exchange_list[0]
    results = []
    i = 0
    for exchange_name in exchange_list:
        if exchange_name.lower() in exchanges.exchange_list.keys():
            exchange = exchanges.get_exchange(exchange_name.lower())
            if underlying in exchange.get_supported_underlyings():
                bid = exchange.get_quote(underlying, 'bid')
                ask = exchange.get_quote(underlying, 'ask')
                try:
                    price = (bid + ask) / 2
                    spread = 100 * (ask - bid) / price
                    if not all_requested or spread < 3.5:
                        if bid > bestbid:
                            bestbid = bid
                            bestbid_exch = exchange_name
                        if ask < bestask:
                            bestask = ask
                            bestask_exch = exchange_name
                        if spread < bestspread:
                            bestspread = spread
                            bestspread_exch = exchange_name
                        i = i + 1
                    if  price > 1:
                        results.append("%s %s price is %.2f: %.2f / %.2f (%.2f%% wide)" % (exchange_name, underlying, price, bid, ask, spread))
                    else:
                        results.append("%s %s price is %.4g: %.4g / %.4g (%.2f%% wide)" % (exchange_name, underlying, price, bid, ask, spread))
                except:
                    results.append("%s price update failed" % exchange_name)
            else:
                results.append('%s not supported for %s' % (underlying, exchange_name))
        else:
            results.append("Unknown exchange: %s" % exchange_name)
    if i >= 2:
        spread = 100 *(bestask / bestbid - 1)
        if price > 1:
            results.append("Max bid is on %s: %.2f\nMin offer is on %s: %.2f.\nBest spread is on %s: %.2f%%\nAggregated price is %.1f%% wide (negative means arbitrageable)" % (bestbid_exch, bestbid, bestask_exch, bestask, bestspread_exch, bestspread, spread))
        else:
            results.append("Max bid is on %s: %.4g\nMin offer is on %s: %.4g.\nBest spread is on %s: %.2f%%\nAggregated price is %.1f%% wide (negative means arbitrageable)" % (bestbid_exch, bestbid, bestask_exch, bestask, bestspread_exch, bestspread, spread))
    return results

def fx(underlying, exchange, cross_ccy):
    FORCCY = underlying[:3].upper()
    DOMCCY = underlying[-3:].upper()

    if cross_ccy in ('USD','EUR','JPY'):
        FORPAIR = DOMCCY+cross_ccy
        DOMPAIR = FORCCY+cross_ccy
    else:
        FORPAIR = cross_ccy+FORCCY
        DOMPAIR = cross_ccy+DOMCCY

    if exchange == "all":
        forExchanges = exchanges.get_exchanges_list_for_underlying(FORPAIR)
        domExchanges = exchanges.get_exchanges_list_for_underlying(DOMPAIR)
        intersectExchanges = list(set(forExchanges).intersection(domExchanges))
    elif exchange.lower() not in exchanges.get_exchanges_list():
        return ['Unsupported exchange %s' % exchange]
    else:
        if (FORPAIR in exchanges.get_exchange(exchange.lower()).get_supported_underlyings()) and (DOMPAIR in exchanges.get_exchange(exchange.lower()).get_supported_underlyings()):
            intersectExchanges = [exchange]
        else:
            return ["Exchange %s does not support %s and %s" % (exchange, FORPAIR, DOMPAIR)]
    results = []
    if not intersectExchanges:
        return ["No exchange supports %s and %s" % (FORPAIR, DOMPAIR)]

    try:
        e = exchanges.get_exchange(intersectExchanges[0].lower())
        fxRate = float(e.get_quote(underlying,'last'))
        results.append('%s rate for %s is %.5g' % (intersectExchanges[0], underlying, fxRate))
    except:
        url = 'http://www.apilayer.net/api/live?access_key='+CL_API_KEY+'&currencies='+FORCCY+','+DOMCCY
        r = requests.get(url)
        r.raise_for_status()
        j = r.json()
        if j['success'] and 'quotes'in j:
            if 'USD'+DOMCCY in j['quotes'] and 'USD'+FORCCY in j['quotes']:
                domOfficialRate = j['quotes']['USD'+DOMCCY]
                forOfficialRate = j['quotes']['USD'+FORCCY]
                fxRate = domOfficialRate / forOfficialRate
                results.append('Currency Layer %s FX rate is %.5g' % (underlying, fxRate))
            else:
                fxRate = 0
                results.append('Could not retrieve %s FX rate from CurrencyLayer' % underlying)
        else:
            fxRate = 0
            results.append('Could not retrieve %s FX rate from CurrencyLayer' % underlying)

    results.append('Using %s as the cross currency: %s and %s' % (cross_ccy.upper(), FORPAIR, DOMPAIR))

    for exch in intersectExchanges:
        e = exchanges.get_exchange(exch.lower())
        try:
            fx_bid = e.get_quote(DOMPAIR,'bid') / e.get_quote(FORPAIR,'ask')
            fx_ask = e.get_quote(DOMPAIR,'ask') / e.get_quote(FORPAIR,'bid')
            if fxRate != 0 and (fx_bid > fxRate or fx_ask < fxRate):
                if fx_bid > fxRate:
                    arb = 100 * (float(fx_bid) / fxRate - 1)
                else:
                    arb = 100 * (fxRate / float(fx_ask) - 1)
                results.append('%s on %s: bid %.5g / %.5g ask. %.2f%% arb vs %.5g official rate' % (underlying, exch, fx_bid, fx_ask, arb, fxRate))
            else:
                results.append('%s on %s: bid %.5g / %.5g ask' % (underlying, exch, fx_bid, fx_ask))
        except ZeroDivisionError:
            results.append('%s: one of the quotes is worth 0' % exch)
    return results

def priceMsg(update, context):
    logger.info("Received /price command from %s" % update.effective_user)
    logger.info("Command content: %s" % update.message.text)
    if update.message.text.split().__len__() <= 2:
        update.message.reply_text('Syntax is "/price <underlying> <exchange1> <exchange2> <...>".\nTry "/price <underlying> all" to price your underlying on all supported exchanges.\nType /list to see supported exchanges')
        return
    underlying = update.message.text.split()[1].upper()
    exchange_list = update.message.text.split()[2:]
    if exchange_list == []:
        exchange_list = ['all']
    messages = price(underlying, exchange_list)
    update.message.reply_text('\n'.join(messages))

def fxMsg(update, context):
    logger.info("Received /fx command from %s" % update.effective_user)
    logger.info("Command content: %s" % update.message.text)
    if update.message.text.split().__len__() <= 2:
        update.message.reply_text('Syntax is "/fx <fxpair> <exchange> <cross>".\nTry "/fx <fxpair> all eth" to price your underlying on all supported exchanges with eth as the cross cryotocurrency.\nType /list to see supported exchanges')
        return
    underlying = update.message.text.split()[1].upper()
    exchange_list = update.message.text.split()[2]
    if update.message.text.split().__len__() == 4:
        cross_ccy = update.message.text.split()[3].upper()
    else:
        if underlying[-3:].upper() == 'BTC' or underlying[:3].upper() == 'BTC':
            cross_ccy = 'USD'
        else:
            cross_ccy = 'BTC'
    if exchange_list == []:
        update.message.reply_text('No exchange specified. Try all or gatecoin for example')
        return
    messages = fx(underlying, exchange_list, cross_ccy)
    update.message.reply_text('\n'.join(messages))

def inline_query(update, context):
    query = update.inline_query.query
    if not query:
        return
    logger.info("Inline query received from %s: %s" % (update.inline_query.from_user, query))
    results = list()
    query_type = query.split()[0]
    messages = [BOTNAME]
    if query_type.lower() == 'price':
        if query.split().__len__() <= 2:
            return
        underlying = query.split()[1].upper()
        exchange_list = query.split()[2:]
        if exchange_list == []:
            return
        messages.extend(price(underlying, exchange_list))
    elif query_type.lower() == 'list':
        messages.append(list_text())
    else:
        messages.append('Try ' + BOTNAME + ' price bitcoin bitfinex, or ' + BOTNAME + ' list')
    reply_text = '\n'.join(messages)
    results.append(InlineQueryResultArticle(id=uuid4(), title='Enter to display results', input_message_content=InputTextMessageContent(reply_text)))
    bot.answer_inline_query(update.inline_query.id, results)

def error(update, context):
    logger.warn('Update "%s" caused error "%s"' % (update, context.error))

def main_telegram():
    # Create the EventHandler and pass it to the bot's token
    updater = Updater(token=TOKEN, use_context=True)

    # Get the dispathcher to register handlers
    dispatcher = updater.dispatcher

    # Add handlers
    start_handler = CommandHandler('start', startMsg)
    list_exchanges_handler = CommandHandler('list', listExchangesMsg)
    price_handler = CommandHandler('price', priceMsg)
    fx_handler = CommandHandler('fx',fxMsg)
    exchange_handler = CommandHandler('exchange',exchangeMsg)
    summary_handler = CommandHandler('summary',summaryMsg)
    bitmex_handler = CommandHandler('bitmex', bitmexMsg)
    inline_query_handler = InlineQueryHandler(inline_query)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(list_exchanges_handler)
    dispatcher.add_handler(price_handler)
    dispatcher.add_handler(fx_handler)
    dispatcher.add_handler(exchange_handler)
    dispatcher.add_handler(summary_handler)
    dispatcher.add_handler(bitmex_handler)
    dispatcher.add_handler(inline_query_handler)

    unknown_handler = MessageHandler(Filters.text, unknownMsg)
    dispatcher.add_handler(unknown_handler)

    # log all errors
    dispatcher.add_error_handler(error)

    # start the bot
    logger.info("Starting bot.")
    updater.start_polling()

    # The above runs the bot until CTRL-C or SIGINT, SIGTERM, or SIGABRT is
    # received. start_polling() is non-blocking and this will stop the bot
    # gracefully
    updater.idle()
    logger.info("Exiting bot.")

def slack_parse_bot_commands(bot_id, slack_events):
    for event in slack_events:
        if event["type"] == "message" and not "subtype" in event:
            matches = re.search(SLACK_MENTION_REGEX, event["text"])
            user_id, message = (matches.group(1), matches.group(2).strip()) if matches else (None, None)
            if user_id == bot_id:
                return message, event["channel"]
    return None, None

def slack_handle_command(client, command, channel):
    default_response = "Not sure what you mean. Try:\n  *summary* <list of tokens>\n  *fx* <FORDOM> <exchange> <CROSS>\n  *bitmex* <list of futures>\n  *price* <ticker> <list of exchanges>"
    response = None
    if command.lower().startswith("summary"):
        if command.split().__len__() <= 1:
            ccy = ['globalsummary']
        else:
            ccy = command.split()[1:]
        response = '\n'.join(summary(ccy))
    elif command.lower().startswith("fx"):
        if command.split().__len__() <= 2:
            response = 'Syntax is "*fx* <fxpair> <exchange> <cross>".\nTry "*fx* <fxpair> all eth" to price your underlying on all supported exchanges with eth as the cross ccy.'
        else:
            underlying = command.split()[1].upper()
            exchange_list = command.split()[2]
            if command.split().__len__() >= 4:
                cross_ccy = command.split()[3].upper()
            else:
                if underlying[-3:].upper() == 'BTC' or underlying[:3].upper() == 'BTC':
                    cross_ccy = 'USD'
                else:
                    cross_ccy = 'BTC'
            if exchange_list == []:
                response = 'No exchange specified. Try all or gdax for example'
            else:
                messages = fx(underlying, exchange_list, cross_ccy)
                response = '\n'.join(messages)
    elif command.lower().startswith("bitmex"):
        if command.split().__len__()<=1:
            response = "Syntax is *bitmex* <future>. For example *bitmex* XBTM18"
        else:
            futlist  = command.upper().split()[1:]
            message_text = ""
            for i, fut in enumerate(futlist):
                message_text+=bitmex(fut)
                if i != len(futlist)-1:
                    message_text+='\n------------\n'
            response = message_text
    elif command.lower().startswith("price"):
        if command.split().__len__() <= 2:
            response = 'Syntax is "*price* <underlying> <exchange1> <exchange2> <...>".\nTry "*price* <underlying> all" to price your underlying on all supported exchanges.'
        else:
            underlying = command.split()[1].upper()
            exchange_list = command.split()[2:]
            if exchange_list == []:
                exchange_list = ['all']
            messages = price(underlying, exchange_list)
            response = '\n'.join(messages)
    client.api_call("chat.postMessage",channel=channel,text=response or default_response)

def main_slack():
    # instantiate Slack client
    slack_client = slack.WebClient(SLACK_BOT_TOKEN)
    slack_bot_id = None
    # Constants
    RTM_READ_DELAY = 1 # 1 second delay between reading from RTM

    if slack_client.rtm_connect(with_team_state=False, auto_reconnect=True):
        logger.info("Slack Bot connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        slack_bot_id = slack_client.api_call("auth.test")["user_id"]
        while slack_client.server.connected is True:
            command, channel = slack_parse_bot_commands(slack_bot_id, slack_client.rtm_read())
            if command:
                slack_handle_command(slack_client, command, channel)
            time.sleep(RTM_READ_DELAY)
    else:
        logger.error("Connection failed. Exception traceback printed above")

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'slack':
        main_slack()
    else:
        main_telegram()

