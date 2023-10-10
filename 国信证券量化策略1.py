#encoding:gbk
'''

低策略
'''
from datetime import datetime
from datetime import timedelta
import talib as tb
import json
import numpy as np
import math


class GlobalData():
    pass
g=GlobalData()

def init(context):
    # 配置择时
    g.MA = ['399001.SZ', 10] # 均线择时
    context.data_info_level = 0
    context.set_universe([g.MA[0]])
    myscheduler(context)
    g.isbull = False # 是否牛市
    g.chosen_stock_list = [] # 存储选出来的股票
    g.nohold = True # 空仓专用信号
    g.sold_stock = {} # 近期卖出的股票及卖出天数
    g.acct= '620000022137' #账号为模型交易界面选择账号
    g.acct_type= 'stock' #账号类型为模型交易界面选择账号
    
def myscheduler(context):
    set_param(context)

def isnan(v):
    return math.isnan(v)
    
def set_param(context):
    # 交易设置
    g.stocknum = 4 # 理想持股数量
    g.bearpercent = 0.3 # 熊市仓位
    g.bearposition = True # 熊市是否持仓
    g.sellrank = 10 # 排名多少位之后(不含)卖出
    g.buyrank = 9 # 排名多少位之前(含)可以买入

    # 初始筛选
    g.tradeday = 300 # 上市天数
    g.increase1d = 0.087 # 前一日涨幅
    g.tradevaluemin = 300 # 最小流通市值 单位（亿）
    g.tradevaluemax = 5000 # 最大流通市值 单位（亿）
    g.pbmin = 0.01 # 最小市净率
    g.pbmax = 30 # 最大市净率

    # 排名条件及权重，正数代表从小到大，负数表示从大到小
    # 各因子权重：总市值，流通市值，最新价格，5日平均成交量，60日涨幅
    g.weights = [5,5,8,4,10]
    
    
    g.choose_time_signal = True # 启用择时信号
    g.threshold = 0.003 # 牛熊切换阈值
    g.buyagain = 5 # 再次买入的间隔时间
    
# 获取前n个单位时间当时的收盘价
def get_close_price(context,security, n, unit='1d'):
    data = context.get_market_data_ex(['close'],stock_code=[security], count=n, period=unit)[security]
    return data['close'][0]
# 计算20天内的涨幅
def get_growth_rate(context,security, n=20):
    data = context.get_market_data_ex(['close'],stock_code=[security],count=n, period='1d')[security]
    #lc = data['close'][0]
    lc = min(data['close'])
    
    c = data['close'][-1]
    #print(f'lc: {lc} c:{c}')
    if not isnan(lc) and not isnan(c) and lc != 0:
        return (c - lc) / lc
    else:
        print(f"数据非法, security: {security}, {n}日收盘价: {lc}, 当前价:  c" )
        return 0
def get_growth_rate60(context,security):
    data = context.get_market_data_ex(['close'],stock_code=[security],count=60, period='1d')[security]
    price60d = min(data['close'])
    pricenow = data['close'][-1]
    if not isnan(pricenow) and not isnan(price60d) and price60d != 0:
        return (pricenow) / price60d
    else:
        return 100
# 过滤涨幅超过5%的股票
def filter_limitup_stock(context, stock_list):
    data = context.get_full_tick(stock_list)
    last_prices = data

    holdings = get_trade_detail_data(g.acct, g.acct_type, 'position')
    # 已存在于持仓的股票即使涨停也不过滤，避免此股票再次可买，但因被过滤而导致选择别的股票
    return [stock for stock in stock_list if stock in holdings 
        or last_prices[stock]['lastPrice'] < last_prices[stock]['open']*1.05]

# 过滤停牌股票
def filter_paused_stock(context,stock_list):

    return [stock for stock in stock_list if not context.is_suspended_stock(stock)]

# 过滤ST及其他具有退市标签的股票
def filter_st_stock(context,stock_list):
    return [stock for stock in stock_list 
        if 'ST' not in context.get_stock_name(stock) 
        and '*' not in context.get_stock_name(stock)
        and '退' not in context.get_stock_name(stock)]
# 只选60\00开头的股票
def filter_gem_stock(context, stock_list):
    return [stock for stock in stock_list if stock[0:2] == '00' ]

# 平仓，卖出指定持仓
def close_position(context,security):
    order_target_value(security,0,context,g.acct)
    # 可能会因停牌或跌停失败
    holdings = get_holdings()
    if security not in holdings:
        g.sold_stock[security] = 0
        
# 过滤次新股
def filter_new_stock(context, stock_list):
    now = datetime.now()
    return [stock for stock in stock_list if (now - timedelta(days=g.tradeday)) > datetime.strptime(str(context.get_open_date(stock)),'%Y%m%d')]

# 过滤昨日涨幅过高的股票
def filter_increase1d(context,stock_list):
    return [stock for stock in stock_list if get_close_price(context,stock, 1) / get_close_price(context,stock, 2) < (1 + g.increase1d)]

# 过滤卖出不足buyagain日的股票
def filter_buyagain(stock_list):
    return [stock for stock in stock_list if stock not in g.sold_stock.keys()]
    
# 清空卖出所有持仓
def clear_position(context):
    holdings = get_holdings()
    if len(holdings)>0:
        print("==> 清仓，卖出所有股票")
        for stock in holdings:
            #print(stock)
            close_position(context,stock)
#获取当前持仓
def get_holdings():
    holdinglist = {}
    resultlist = get_trade_detail_data(g.acct, g.acct_type, "POSITION")
    for obj in resultlist:
        holdinglist[obj.m_strInstrumentID + "." + obj.m_strExchangeID] = obj.m_nCanUseVolume
    return holdinglist
#获取可用资金    
def get_avaliable_cash():
    result = 0
    resultlist = get_trade_detail_data(g.acct, g.acct_type, "ACCOUNT")
    for obj in resultlist:
        result = obj.m_dAvailable
    return result
    
def get_stock_list(context):
    df = get_fundamentals(query(valuation.code).filter(valuation.pb_ratio.between(g.pbmin, g.pbmax)
        ).order_by(valuation.circulating_market_cap.asc()).limit(1000)).dropna()
    stock_list = list(df['code'])
    
    # 过滤创业板、ST、停牌、当日涨停、次新股、昨日涨幅过高
    stock_list = filter_gem_stock(context, stock_list)
    stock_list = filter_st_stock(stock_list)
    stock_list = filter_paused_stock(stock_list)
    stock_list = filter_limitup_stock(context, stock_list)
    stock_list = filter_new_stock(context, stock_list)
    stock_list = filter_increase1d(stock_list)
    stock_list = filter_buyagain(stock_list)
    return stock_list
    
def handlebar(context):
    #跳过历史k线
    if not context.is_last_bar():
        return
    now = datetime.now()
    now_time = now.strftime('%H%M%S')
    #跳过非交易时间
    if now_time < '093000' or now_time > "150000":
        return
    account = get_trade_detail_data(g.acct, g.acct_type, 'account')
    if len(account)==0:
        print(f'账号{g.acct} 未登录 请检查')
        return
    #print(datetime.strptime(str(context.get_open_date('000001.SZ')),'%Y%m%d'))
    
    #print(filter_increase1d(context,['000001.SZ','600589.SH']))
    
    fieldList = ['Valuation_and_Market_Cap.MktValue']
    stockList = ['600000.SH', '000001.SZ']
    startDate = '20231001'
    endDate = '20231012'
    d=context.get_factor_data(fieldList, stockList, startDate, endDate)
    print(str(d['000001.SZ']))






