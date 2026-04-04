import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from collections import deque
import time

# --- CONFIGURATION ---
TICKERS_LIST = {"MC": "^FCHI", "TTE": "^FCHI", "AI": "^FCHI", "OR": "^FCHI", "SAN": "^FCHI"}

if 'buffers' not in st.session_state:
    st.session_state.buffers = {t: deque(maxlen=60) for t in TICKERS_LIST}
if 'last_alerts' not in st.session_state:
    st.session_state.last_alerts = {t: None for t in TICKERS_LIST}

# --- SCRAPER & DATA ---
def get_boursorama_live(ticker):
    try:
        url = f"https://www.boursorama.com/cours/1rP{ticker}/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        price = soup.find("span", class_="c-instrument c-instrument--last").text.replace(" ", "").replace(",", ".").strip()        
        return float(price)
    except: return None

def get_processed_data(ticker):
    # 1. Fondamentaux (Cache pour éviter de saturer l'API)
    # L'astuce est de passer la session à l'objet Ticker
    stock = yf.Ticker(f"{ticker}.PA")

    info = stock.info
    fundamental = {
        "PER": info.get("trailingPE", 0),
        "Marge": info.get("profitMargins", 0) * 100,
        "Secteur": info.get("sector", "N/A")
    }

    # 2. Historique & Buffer
    try:
        # On utilise directement yf.download ou Ticker sans argument 'session'
        df_hist = yf.download(f"{ticker}.PA", period="3d", interval="15m", progress=False)
        
        # Sécurité MultiIndex (comme vu précédemment)
        if isinstance(df_hist.columns, pd.MultiIndex):
            df_hist = df_hist['Close'][[f"{ticker}.PA"]]
            df_hist.columns = ['Close']
        else:
            df_hist = df_hist[['Close']]
            
    except Exception as e:
        st.error(f"Erreur Yahoo Finance : {e}")
        df_hist = pd.DataFrame(columns=['Close'])

    # On renomme la colonne en 'Close' pour qu'elle corresponde exactement au buffer
    df_hist.columns = ['Close']
    
    live_p = get_boursorama_live(ticker)
    
    if live_p:
        st.session_state.buffers[ticker].append({'Datetime': pd.Timestamp.now(), 'Close': live_p})
    
    df_buf = pd.DataFrame(list(st.session_state.buffers[ticker]))
    if not df_buf.empty:
        df_buf.set_index('Datetime', inplace=True)
        df_final = pd.concat([df_hist.iloc[:-1], df_buf])
    else:
        df_final = df_hist

    # 3. Indicateurs (Technique + Volatilité)
    df_final['EMA'] = df_final['Close'].ewm(span=10).mean()
    df_final['Min_L'] = df_final['EMA'].rolling(window=30).min()
    df_final['Max_L'] = df_final['EMA'].rolling(window=30).max()
    
    # Volatilité sur le buffer (Standardisée)
    if len(st.session_state.buffers[ticker]) > 10:
        returns = df_buf['Close'].pct_change().dropna()
        volat_buffer = returns.std() * np.sqrt(252 * 480) # Annualisée sur base minutes
    else:
        volat_buffer = 0
        
    return df_final, live_p, fundamental, volat_buffer

# --- GUI ---
st.set_page_config(page_title="SBF120 Quant-Station", layout="wide")
st.title("🏛️ Quant-Station : Live Buffer & Volatility")

# Dashboard métriques
cols = st.columns(len(TICKERS_LIST))
for i, (t, bench) in enumerate(TICKERS_LIST.items()):
    df, p, fund, vol = get_processed_data(t)
    with cols[i]:
        st.subheader(f"{t}")
        st.metric("Prix", f"{p} €", f"{vol:.1f}% Volat", delta_color="inverse" if vol > 25 else "normal")
        st.caption(f"PER: {fund['PER']:.1f} | Marge: {fund['Marge']:.1f}%")
        
        # Logique Alerte
        ema_now = df['EMA'].iloc[-1]
        if ema_now <= df['Min_L'].iloc[-1] and st.session_state.last_alerts[t] != "BUY":
            st.success("🟢 BUY DIP")
            # Envoi Mail ici...
            st.session_state.last_alerts[t] = "BUY"
        elif ema_now >= df['Max_L'].iloc[-1] and st.session_state.last_alerts[t] != "SELL":
            st.error("🔴 SELL PEAK")
            # Envoi Mail ici...
            st.session_state.last_alerts[t] = "SELL"
        elif not (ema_now <= df['Min_L'].iloc[-1] or ema_now >= df['Max_L'].iloc[-1]):
            st.session_state.last_alerts[t] = None

# Graphique interactif
st.divider()
target = st.selectbox("Inspection technique détaillée", list(TICKERS_LIST.keys()))
df_viz, _, _, _ = get_processed_data(target)

fig = go.Figure()
fig.add_trace(go.Scatter(x=df_viz.index, y=df_viz['Close'], name="Prix", line=dict(color='white', width=1)))
fig.add_trace(go.Scatter(x=df_viz.index, y=df_viz['EMA'], name="EMA Lissage", line=dict(color='orange', width=2)))
fig.add_trace(go.Scatter(x=df_viz.index, y=df_viz['Min_L'], name="Support", line=dict(color='green', dash='dash')))
fig.add_trace(go.Scatter(x=df_viz.index, y=df_viz['Max_L'], name="Résistance", line=dict(color='red', dash='dash')))

fig.update_layout(template="plotly_dark", height=500, xaxis_rangeslider_visible=False)
st.plotly_chart(fig, use_container_width=True)

time.sleep(60)
st.rerun()
