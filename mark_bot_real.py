import MetaTrader5 as mt5
import time
import os
import pandas as pd
import requests
from berth_memory import BerthMemory
from drive_sync import upload_to_drive, download_from_drive

# === ENV VARS ===
SYMBOL = "XAUUSD"
RISK_PERCENT = 2
RRR = 2
MEMORY_FILE = "berth_memory.json"

MT5_LOGIN = int(os.getenv("MT5_LOGIN"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD")
MT5_SERVER = os.getenv("MT5_SERVER")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
DRIVE_FILE_ID = os.getenv("DRIVE_FILE_ID")

# === INIT MT5 ===
def init_mt5():
    if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("❌ MT5 Init failed:", mt5.last_error())
        time.sleep(5)
        return False
    print(f"✅ Connected to MT5 | Balance: {mt5.account_info().balance}")
    return True

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": msg}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def get_balance():
    info = mt5.account_info()
    return info.balance if info else 0

def calculate_lot(sl_points, balance, risk_percent):
    risk_dollars = (risk_percent / 100.0) * balance
    tick_value = mt5.symbol_info(SYMBOL).trade_tick_value or 1
    lot = round(risk_dollars / (sl_points * tick_value), 2)
    return max(lot, 0.01)

def place_order(direction, entry_price, sl, tp, lot):
    order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": order_type,
        "price": entry_price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": 20250408,
        "comment": "Mark AI",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("❌ Order failed:", result.retcode)
    else:
        print(f"✅ Trade sent: {direction.upper()} at {entry_price}")
        return True
    return False

def get_candles(symbol, timeframe, bars=150):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    return pd.DataFrame(rates) if rates is not None else None

def vix_fix(df):
    df['L'] = df['low']
    df['C'] = df['close']
    df['wvf'] = ((df['L'].rolling(22).min() - df['C']) / df['L'].rolling(22).min()) * 100
    return df

def stochastic(df, k_period=5, d_period=3, slowing=3):
    low_min = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    df['%K'] = 100 * ((df['close'] - low_min) / (high_max - low_min))
    df['%D'] = df['%K'].rolling(window=d_period).mean()
    df['stoch_slow'] = df['%D'].rolling(window=slowing).mean()
    return df

def is_higher_tf_bullish():
    df = get_candles(SYMBOL, mt5.TIMEFRAME_H1, 200)
    if df is None or len(df) < 50:
        return False
    ema50 = df['close'].rolling(50).mean().iloc[-1]
    ema200 = df['close'].rolling(200).mean().iloc[-1]
    return ema50 > ema200

def is_higher_tf_bearish():
    df = get_candles(SYMBOL, mt5.TIMEFRAME_H1, 200)
    if df is None or len(df) < 50:
        return False
    ema50 = df['close'].rolling(50).mean().iloc[-1]
    ema200 = df['close'].rolling(200).mean().iloc[-1]
    return ema50 < ema200

def check_timeframe_for_signal(tf):
    df = get_candles(SYMBOL, tf)
    if df is None or len(df) < 30:
        return None
    df = vix_fix(df)
    df = stochastic(df)
    last = df.iloc[-1]
    mean_wvf = df['wvf'].rolling(22).mean().iloc[-1]

    if last['wvf'] > mean_wvf + 1:  # relaxed
        if last['stoch_slow'] < 30 and is_higher_tf_bullish():
            return "buy"
        elif last['stoch_slow'] > 70 and is_higher_tf_bearish():
            return "sell"
    return None

def strategy_logic():
    signal = check_timeframe_for_signal(mt5.TIMEFRAME_M5)
    if signal is None:
        signal = check_timeframe_for_signal(mt5.TIMEFRAME_M15)
    if signal is None:
        return None

    tick = mt5.symbol_info_tick(SYMBOL)
    if not tick:
        return None

    price = tick.ask if signal == "buy" else tick.bid
    point = mt5.symbol_info(SYMBOL).point
    sl = price - 100 * point if signal == "buy" else price + 100 * point
    tp = price + 200 * point if signal == "buy" else price - 200 * point
    lot = calculate_lot(100, get_balance(), RISK_PERCENT)

    if place_order(signal, price, sl, tp, lot):
        msg = f"{'📈' if signal == 'buy' else '📉'} {signal.upper()} XAUUSD\nEntry: {price:.2f}\nTP: {tp:.2f}\nSL: {sl:.2f}\nLot: {lot}"
        send_telegram(msg)
        return {"timestamp": time.ctime(), "entry": price, "sl": sl, "tp": tp, "direction": signal, "lot": lot}
    return None

def run_bot():
    if os.path.exists(MEMORY_FILE):
        download_from_drive(DRIVE_FILE_ID, MEMORY_FILE)
        memory = BerthMemory.load(MEMORY_FILE)
    else:
        memory = BerthMemory()

    while True:
        print(f"📡 Mark scanning @ {time.ctime()}")
        if not mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
            print("🔁 Reconnecting...")
            time.sleep(15)
            continue

        trade = strategy_logic()
        if trade:
            memory.add_trade(trade)
            memory.save(MEMORY_FILE)
            upload_to_drive(MEMORY_FILE, DRIVE_FILE_ID)

        mt5.shutdown()
        time.sleep(300)

if __name__ == "__main__":
    print("🤖 Mark is Live on Render with Dual-Timeframe Entries!")
    if init_mt5():
        run_bot()
    else:
        print("❌ Startup failed.")
