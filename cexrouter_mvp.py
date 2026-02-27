import streamlit as st
import ccxt
import pandas as pd
import json
import os
from cryptography.fernet import Fernet

# ==================== PAGE CONFIG & DARK CRYPTO THEME ====================
st.set_page_config(page_title="CEXRouter MVP", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .stApp { background-color: #0E1117; color: #FAFAFA; }
    .stButton>button { background-color: #00FF9D; color: #000000; font-weight: bold; border-radius: 8px; }
    .stDataFrame { background-color: #1E242C; }
    .css-1d391kg { background-color: #0E1117; }
    .stAlert { background-color: #1E242C; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 CEXRouter MVP — Multi-Exchange Trading Hub")
st.markdown("**Binance • OKX • Bybit** | DCA • Arbitrage • Market Neutral | Portfolio Overview")
st.caption("✅ Builder fees disabled • Keys stored securely in Streamlit secrets")

# ==================== CONFIG (Cloud + Local fallback) ====================
def get_config():
    if "exchanges" in st.secrets:  # Deployed on Streamlit Cloud
        return {
            "exchanges": dict(st.secrets["exchanges"]),
            "testnet": st.secrets.get("testnet", False)
        }
    # Local development fallback
    CONFIG_FILE = "cexrouter_config.enc"
    KEY_FILE = "secret.key"
    if os.path.exists(CONFIG_FILE) and os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
        fernet = Fernet(key)
        with open(CONFIG_FILE, "rb") as f:
            return json.loads(fernet.decrypt(f.read()).decode())
    return {"exchanges": {}, "testnet": False}

def save_config(config):
    if "exchanges" not in st.secrets:  # Only save locally
        CONFIG_FILE = "cexrouter_config.enc"
        KEY_FILE = "secret.key"
        if not os.path.exists(KEY_FILE):
            key = Fernet.generate_key()
            with open(KEY_FILE, "wb") as f:
                f.write(key)
        else:
            with open(KEY_FILE, "rb") as f:
                key = f.read()
        fernet = Fernet(key)
        encrypted = fernet.encrypt(json.dumps(config).encode())
        with open(CONFIG_FILE, "wb") as f:
            f.write(encrypted)

config = get_config()

# ==================== EXCHANGE SETUP ====================
EXCHANGES = ["binance", "okx", "bybit"]

def get_exchange(name, testnet=False):
    creds = config["exchanges"].get(name, {})
    if not creds.get("apiKey"):
        return None
    params = {
        'apiKey': creds["apiKey"],
        'secret': creds["secret"],
        'enableRateLimit': True,
    }
    if name == "okx" and creds.get("password"):
        params['password'] = creds["password"]
    if testnet:
        params['options'] = {'defaultType': 'spot'}
    
    ex = getattr(ccxt, name)(params)
    # DISABLE BUILDER FEE
    ex.options = ex.options or {}
    ex.options['builderFee'] = False
    
    if testnet:
        ex.set_sandbox_mode(True)
    return ex

# ==================== SIDEBAR ====================
page = st.sidebar.selectbox("Navigation", 
    ["🔑 API Configuration", "📊 Portfolio Overview", "🎯 Strategy Router", "🤖 Bots"])

testnet = st.sidebar.checkbox("Use Testnet", value=config.get("testnet", False))
if testnet != config.get("testnet"):
    config["testnet"] = testnet
    save_config(config)

# ==================== PAGE 1: API CONFIG ====================
if page == "🔑 API Configuration":
    st.header("🔑 API Key Configuration")
    st.warning("⚠️ Use **read + trade only** — NO withdrawals. Keys never leave your machine/cloud secrets.")
    
    for ex_name in EXCHANGES:
        st.subheader(ex_name.upper())
        with st.expander("Edit keys", expanded=True):
            api_key = st.text_input(f"{ex_name} API Key", 
                                  value=config["exchanges"].get(ex_name, {}).get("apiKey", ""), 
                                  type="password", key=f"k_{ex_name}")
            secret = st.text_input(f"{ex_name} Secret", 
                                 value=config["exchanges"].get(ex_name, {}).get("secret", ""), 
                                 type="password", key=f"s_{ex_name}")
            password = None
            if ex_name == "okx":
                password = st.text_input(f"{ex_name} Passphrase (OKX only)", 
                                       value=config["exchanges"].get(ex_name, {}).get("password", ""), 
                                       type="password", key=f"p_{ex_name}")
            
            if st.button(f"Save & Test {ex_name}", key=f"save_{ex_name}"):
                config["exchanges"][ex_name] = {"apiKey": api_key, "secret": secret}
                if ex_name == "okx" and password:
                    config["exchanges"][ex_name]["password"] = password
                save_config(config)
                
                ex = get_exchange(ex_name, testnet)
                if ex:
                    try:
                        bal = ex.fetch_balance()
                        usdt_free = bal.get('free', {}).get('USDT', 0)
                        st.success(f"✅ {ex_name.upper()} CONNECTED! Free USDT: {usdt_free:,.2f}")
                    except Exception as e:
                        st.error(f"❌ {ex_name.upper()} error: {str(e)[:100]}...")

# ==================== PAGE 2: PORTFOLIO ====================
elif page == "📊 Portfolio Overview":
    st.header("📊 Portfolio Overview")
    data = []
    total_usd = 0.0
    positions = []
    
    for ex_name in EXCHANGES:
        ex = get_exchange(ex_name, testnet)
        if not ex: continue
        try:
            bal = ex.fetch_balance()
            usd = 0.0
            for asset, amount in bal.get('total', {}).items():
                if amount > 0.0001:
                    if asset == 'USDT':
                        usd += amount
                    else:
                        try:
                            ticker = ex.fetch_ticker(f"{asset}/USDT")
                            usd += amount * ticker['last']
                        except:
                            pass
            data.append({"Exchange": ex_name.upper(), "Total USD": round(usd, 2)})
            total_usd += usd
            
            # Fetch positions (futures)
            try:
                pos = ex.fetch_positions() if hasattr(ex, 'fetch_positions') else []
                for p in pos:
                    if float(p.get('contracts', 0)) != 0:
                        positions.append({
                            "Exchange": ex_name.upper(),
                            "Symbol": p['symbol'],
                            "Side": p.get('side', '–'),
                            "Contracts": p.get('contracts'),
                            "Unrealized PnL": p.get('unrealizedPnl')
                        })
            except:
                pass
        except:
            pass
    
    if data:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
        st.metric("Total Portfolio Value", f"${total_usd:,.2f}")
        st.bar_chart(df.set_index("Exchange")["Total USD"])
        
        if positions:
            st.subheader("Open Positions")
            st.dataframe(pd.DataFrame(positions), use_container_width=True)
    else:
        st.info("Add API keys in the Configuration page first")

# ==================== PAGE 3: STRATEGY ROUTER ====================
elif page == "🎯 Strategy Router":
    st.header("🎯 Strategy Router — Auto Choose Best Exchange")
    symbol = st.text_input("Symbol (e.g. BTC/USDT)", "BTC/USDT").upper()
    amount_usd = st.number_input("Amount in USDT", min_value=10.0, value=100.0, step=10.0)
    
    if st.button("🔍 Find Best Exchange & Execute", type="primary"):
        results = []
        best_ex = None
        best_score = -999999
        
        for ex_name in EXCHANGES:
            ex = get_exchange(ex_name, testnet)
            if not ex: continue
            try:
                ticker = ex.fetch_ticker(symbol)
                bal = ex.fetch_balance()
                free_usdt = bal.get('free', {}).get('USDT', 0)
                
                fees = ex.fetch_trading_fees() if hasattr(ex, 'fetch_trading_fees') else {'taker': 0.001}
                spread = (ticker['ask'] - ticker['bid']) / ticker['bid'] * 100
                
                score = free_usdt - (fees.get('taker', 0.001) * amount_usd) - (spread * 10)
                
                results.append({
                    "Exchange": ex_name.upper(),
                    "Free USDT": round(free_usdt, 2),
                    "Taker Fee %": round(fees.get('taker', 0) * 100, 3),
                    "Spread %": round(spread, 4),
                    "Score": round(score, 2)
                })
                
                if score > best_score:
                    best_score = score
                    best_ex = ex
                    best_name = ex_name
            except Exception as e:
                results.append({"Exchange": ex_name.upper(), "Free USDT": 0, "Taker Fee %": 0, "Spread %": 0, "Score": -999})
        
        if results:
            df_res = pd.DataFrame(results)
            st.dataframe(df_res, use_container_width=True)
            st.success(f"🏆 **Best Exchange: {best_name.upper()}** (highest score)")
            
            if st.button(f"EXECUTE MARKET BUY on {best_name.upper()}", type="primary"):
                try:
                    price = best_ex.fetch_ticker(symbol)['last']
                    amount = amount_usd / price
                    order = best_ex.create_market_buy_order(symbol, amount)
                    st.balloons()
                    st.success("Order placed successfully!")
                    st.json(order)
                except Exception as e:
                    st.error(f"Execution failed: {str(e)}")

# ==================== PAGE 4: BOTS ====================
else:
    st.header("🤖 Prebuilt Bots")
    tab1, tab2, tab3 = st.tabs(["DCA Bot", "Arbitrage Scanner", "Market Neutral Monitor"])
    
    with tab1:
        st.subheader("DCA Bot — Top 4 Coins")
        coins = st.multiselect("Select coins", ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"], default=["BTC/USDT", "ETH/USDT"])
        dca_usd = st.number_input("USD per coin per run", 50.0, step=10.0)
        
        if st.button("🚀 Run DCA Now on All Connected Exchanges"):
            for ex_name in EXCHANGES:
                ex = get_exchange(ex_name, testnet)
                if not ex: continue
                for sym in coins:
                    try:
                        ticker = ex.fetch_ticker(sym)
                        amt = dca_usd / ticker['last']
                        order = ex.create_market_buy_order(sym, amt)
                        st.success(f"✅ Bought {amt:.6f} {sym} on {ex_name.upper()}")
                    except Exception as e:
                        st.warning(f"{ex_name.upper()} {sym}: {str(e)[:80]}")
    
    with tab2:
        st.subheader("Cross-Exchange Arbitrage Scanner")
        pairs = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        if st.button("Scan for Opportunities Now"):
            prices = {}
            for ex_name in EXCHANGES:
                ex = get_exchange(ex_name, testnet)
                if not ex: continue
                for p in pairs:
                    try:
                        prices.setdefault(p, {})[ex_name.upper()] = ex.fetch_ticker(p)['last']
                    except:
                        pass
            for p, ex_prices in prices.items():
                if len(ex_prices) >= 2:
                    min_ex = min(ex_prices, key=ex_prices.get)
                    max_ex = max(ex_prices, key=ex_prices.get)
                    diff = (ex_prices[max_ex] - ex_prices[min_ex]) / ex_prices[min_ex] * 100
                    if diff > 0.35:
                        st.success(f"🔥 ARB: Buy {min_ex} → Sell {max_ex}  |  {p}  |  +{diff:.2f}%")
                    else:
                        st.info(f"{p}: {diff:.2f}% spread")
    
    with tab3:
        st.subheader("Market Neutral Monitor")
        st.info("All open positions across exchanges")
        all_pos = []
        for ex_name in EXCHANGES:
            ex = get_exchange(ex_name, testnet)
            if not ex: continue
            try:
                pos = ex.fetch_positions() if hasattr(ex, 'fetch_positions') else []
                for p in pos:
                    if abs(float(p.get('contracts', 0))) > 0:
                        all_pos.append({"Exchange": ex_name.upper(), **p})
            except:
                pass
        if all_pos:
            st.dataframe(pd.DataFrame(all_pos), use_container_width=True)
        else:
            st.info("No open futures positions detected")

st.caption("Educational tool only • Trading involves substantial risk of loss • Built with ❤️ using CCXT + Streamlit")
