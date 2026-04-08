import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

# --- 1. MAPPING DES UNIVERS (CAC40 & SBF120) ---
TICKER_MAP_CAC40 = {
    "AC.PA": "1rPAC", "AI.PA": "1rPAI", "AIR.PA": "1rPAIR", "ALO.PA": "1rPALO",
    "MT.AS": "1rPMT", "CS.PA": "1rPCS", "BNP.PA": "1rPBNP", "EN.PA": "1rPEN",
    "CAP.PA": "1rPCAP", "CA.PA": "1rPCA", "ACA.PA": "1rPACA", "BN.PA": "1rPBN",
    "DSY.PA": "1rPDSY", "EDEN.PA": "1rPEDEN", "ENGI.PA": "1rPENGI", "EL.PA": "1rPEL",
    "ERF.PA": "1rPERF", "RMS.PA": "1rPRMS", "KER.PA": "1rPKER", "OR.PA": "1rPOR",
    "LR.PA": "1rPLR", "MC.PA": "1rPMC", "ML.PA": "1rPML", "ORA.PA": "1rPORA",
    "RI.PA": "1rPRI", "PUB.PA": "1rPPUB", "RNO.PA": "1rPRNO", "SAF.PA": "1rPSAF",
    "SGO.PA": "1rPSGO", "SAN.PA": "1rPSAN", "SU.PA": "1rPSU", "GLE.PA": "1rPGLE",
    "STLAP.PA": "1rPSTLAP", "STMPA.PA": "1rPSTMPA", "TEP.PA": "1rPTEP", "HO.PA": "1rPHO",
    "TTE.PA": "1rPTTE", "URW.PA": "1rPURW", "VIE.PA": "1rPVIE", "DG.PA": "1rPDG",
    "VLA.PA":"1rPVLA", "MMT.PA":"1rPMMT", "MMT.PA":"1rPMMT", "TFI.PA":"1rPTFI","MEDCL.PA":"1rMEDCL"
}

TICKER_MAP_SBF120_EXT = {
    "ABCA.PA": "1rPABCA", "AKE.PA": "1rPAKE", "AMUN.PA": "1rPAMUN", "ARG.PA": "1rPARG",
    "BOL.PA": "1rPBOL", "FDJ.PA": "1rPFDJ", "FORVIA.PA": "1rPFORVIA", "GET.PA": "1rPGET",
    "VIV.PA": "1rPVIV", "WLN.PA": "1rPWLN", "NXI.PA": "1rPNXI", "DIM.PA": "1rPDIM"
}
TICKER_MAP_SBF120 = {**TICKER_MAP_CAC40, **TICKER_MAP_SBF120_EXT}

# --- 2. FONCTIONS TECHNIQUES ---
def get_boursorama_live(ticker_yahoo, mapping):
    tag = mapping.get(ticker_yahoo)
    if not tag: return None
    url = f"https://www.boursorama.com/cours/{tag}/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        price_text = soup.find("span", class_="c-instrument--last").text
        price = float(price_text.replace(" ", "").replace(",", "."))
        return {"Close": price, "Time": datetime.now()}
    except: return None

def run_strategy_engine(df, f_win, s_win, f_buy, f_sell, trail_pct):
    if len(df) < s_win + 5: return df, []
    df = df.copy()
    
    # Indicateurs
    df['MA_Fast'] = df['Close'].rolling(f_win).mean()
    df['MA_Slow'] = df['Close'].rolling(s_win).mean()
    df['Min_Local'] = df['Close'].rolling(5).min()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / (loss + 1e-9)))

    # --- 2. Indicateur Horizontal (Pondération) ---
    # On regarde le Min/Max sur les 168 dernières heures de trading (~1 mois)
    df['Min_Month'] = df['Close'].rolling(168).min()
    df['Max_Month'] = df['Close'].rolling(168).max()
    # Calcul de la position relative (0 = Min, 1 = Max)
    df['Price_Loc'] = (df['Close'] - df['Min_Month']) / (df['Max_Month'] - df['Min_Month'])  

    signals = np.zeros(len(df))
    costs = np.zeros(len(df))
    trades = []
    pos, max_p, buy_p = 0, 0.0, 0.0
    
    c, mf, ms, ml, rs, pl = df['Close'].values, df['MA_Fast'].values, df['MA_Slow'].values, df['Min_Local'].values, df['RSI'].values, df['Price_Loc'].values

    for i in range(1, len(df)):
        if i < s_win or np.isnan(rs[i]): continue
        if pos == 0:

            is_low_zone = (pl[i] < 0.40) # Filtre Horizontal : On achète que dans les 40% inférieurs            
            c_min = False#(c[i] <= ml[i])# and (rs[i] > rs[i-1]) and (rs[i] < 42)
            c_cross = (mf[i-1] <= ms[i-1]) and (mf[i] > ms[i])
            if (c_min or c_cross) and is_low_zone:
                signals[i] = 1; pos = 1; buy_p = c[i]; max_p = buy_p
                costs[i] = f_buy # Frais à l'achat
                trades.append({"Date": df.index[i], "Type": "ACHAT", "Prix": round(buy_p, 2), "Motif": "Rebond" if c_min else "Cross"})
        elif pos == 1:
            if c[i] > max_p: max_p = c[i]
            c_trail = ((c[i] < max_p * (1 - 2*trail_pct)) and c[i]> (buy_p*(1+f_sell+f_buy))) or (c[i] < buy_p*(1-3*trail_pct))
            c_exit = False#(mf[i] < ms[i])
            if c_trail or c_exit:
                signals[i] = -1; pos = 0
                costs[i] = f_sell # Frais à la vente
                perf_n = ((c[i]/buy_p)-1 - f_buy - f_sell)*100
                trades.append({"Date": df.index[i], "Type": "VENTE", "Prix": round(c[i], 2), "Perf Net": f"{perf_n:.2f}%", "Motif": "Trail" if c_trail else "MA"})
    
    # Harmonisation des noms de colonnes pour l'interface
    df['Signal_Point'] = signals
    df['Position'] = pd.Series(signals).replace(0, np.nan).ffill().fillna(0).values
    df['Returns'] = df['Close'].pct_change().fillna(0)
    # Performance Nette = (Position_hier * Var_Prix_Aujourdhui) - Frais_Transaction_Aujourdhui
    df['Strat_Ret'] = (df['Position'].shift(1) * df['Returns']) - costs
    df['Cum_Strat'] = (1 + df['Strat_Ret']).cumprod()
    return df, trades

# --- 3. INTERFACE STREAMLIT ---
st.set_page_config(layout="wide", page_title="SBF NEXUS V25", page_icon="📈")

with st.sidebar:
    st.header("⚙️ Configuration")
    universe_choice = st.radio("Marché", ["CAC 40", "SBF 120"])
    current_map = TICKER_MAP_CAC40 if universe_choice == "CAC 40" else TICKER_MAP_SBF120
    ticker_focus = st.selectbox("Action Focus", list(current_map.keys()))
    
    st.subheader("🗓️ Calendrier Backtest")
    start_d = st.date_input("Début", datetime.now() - timedelta(days=60))
    end_d = st.date_input("Fin", datetime.now())
    
    st.divider()
    f_win = st.slider("MA Rapide", 5, 25, 10)
    s_win = st.slider("MA Lente", 25, 150, 50)
    trail = st.slider("Trailing Stop (%)", 0.5, 10.0, 3.0) / 100
    fees_val = st.number_input("Frais (A+V) %", 0.0, 1.0, 0.2) / 100

# --- 4. CHARGEMENT DONNÉES ---
@st.cache_data(ttl=600)
def load_market_data(universe_dict):
    data = yf.download(list(universe_dict.keys()), period="15d", interval="1d", progress=False)
    return data['Close'] if not data.empty else pd.DataFrame()

@st.cache_data(ttl=600)
def load_single_hist(t, s, e):
    d = yf.download(t, start=s, end=e, interval="1h", progress=False)
    if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    return d[['High', 'Low', 'Close', 'Volume']]

# --- 5. ONGLETS ---
tab_radar, tab_bridge, tab_offline, tab_journal = st.tabs(["⚡ RADAR GLOBAL", "🔴 LIVE BRIDGE", "📉 BACKTEST STRATÉGIE", "📋 JOURNAL"])

# --- TAB 1 : RADAR GLOBAL ---
with tab_radar:
    st.subheader(f"Positionnement Tactique : {universe_choice}")
    market_closes = load_market_data(current_map)
    radar_list = []
    if not market_closes.empty:
        for t in current_map.keys():
            if t in market_closes.columns:
                series = market_closes[t].dropna()
                if len(series) < 10: continue
                lp, m15, mx15 = series.iloc[-1], series.min(), series.max()
                score = ((lp - m15) / (mx15 - m15)) * 100 if mx15 != m15 else 50
                radar_list.append({
                    "Ticker": t, "Prix": round(lp, 2), 
                    "vs Min 15j (%)": round(((lp/m15)-1)*100, 2),
                    "Position Range": round(score, 1)
                })
        df_radar = pd.DataFrame(radar_list).sort_values("vs Min 15j (%)")
        st.dataframe(df_radar.style.background_gradient(cmap='RdYlGn_r', subset=['Position Range']), use_container_width=True)

# --- TAB 2 : LIVE BRIDGE ---
with tab_bridge:
    st.subheader(f"Direct Boursorama : {ticker_focus}")
    df_h = load_single_hist(ticker_focus, start_d, end_d)
    live_p = get_boursorama_live(ticker_focus, current_map)
    if live_p and not df_h.empty:
        df_hyb = pd.concat([df_h, pd.DataFrame([live_p['Close']], columns=['Close'], index=[live_p['Time']])])
        df_res, _ = run_strategy_engine(df_hyb, f_win, s_win, fees_val/2, fees_val/2, trail)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Prix Boursorama", f"{live_p['Close']:.2f} €")
        # Utilisation de 'Position' harmonisé
        status = "ACHAT" if df_res['Position'].iloc[-1] == 1 else "ATTENTE"
        c2.metric("Statut Strat", status)
        c3.metric("RSI (14h)", f"{df_res['RSI'].iloc[-1]:.1f}")
        
        fig_l = go.Figure()
        fig_l.add_trace(go.Scatter(x=df_res.index[-60:], y=df_res['Close'][-60:], name="Prix Hybrid", line=dict(color='cyan', width=2)))
        fig_l.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0))
        st.plotly_chart(fig_l, use_container_width=True)
    st.info("🔄 Rafraîchissement automatique 60s...")

# --- TAB 3 : BACKTEST ---
with tab_offline:
    st.subheader(f"Audit Stratégie : {ticker_focus}")
    if not df_h.empty:
        df_off, journal_off = run_strategy_engine(df_h, f_win, s_win, fees_val/2, fees_val/2, trail)
        
        vol_5j = ((df_h['High'] - df_h['Low']) / df_h['Close']).iloc[-120:].mean() * 100
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Perf Nette Totale", f"{(df_off['Cum_Strat'].iloc[-1]-1)*100:.2f} %")
        m2.metric("Volatilité Moy. (5j)", f"{vol_5j:.2f} %")
        m3.metric("Nombre de Trades", len(journal_off))
        
        fig_off = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
        fig_off.add_trace(go.Scatter(x=df_off.index, y=df_off['Close'], name="Prix", line=dict(color='white')), row=1, col=1)
        fig_off.add_trace(go.Scatter(x=df_off.index, y=df_off['MA_Fast'], name="Fast MA", line=dict(color='cyan', width=1)), row=1, col=1)
        
        # Marqueurs ACHAT/VENTE
        buys = df_off[df_off['Signal_Point'] == 1]
        sells = df_off[df_off['Signal_Point'] == -1]
        fig_off.add_trace(go.Scatter(x=buys.index, y=buys['Close'], mode='markers', name='BUY', marker=dict(symbol='triangle-up', size=12, color='lime')), row=1, col=1)
        fig_off.add_trace(go.Scatter(x=sells.index, y=sells['Close'], mode='markers', name='SELL', marker=dict(symbol='triangle-down', size=12, color='orange')), row=1, col=1)
        
        fig_off.add_trace(go.Scatter(x=df_off.index, y=df_off['Cum_Strat'], name="Perf Cumulée", fill='tozeroy', line=dict(color='gray')), row=2, col=1)
        fig_off.update_layout(template="plotly_dark", height=700, showlegend=True, xaxis_rangeslider_visible=False)
        st.plotly_chart(fig_off, use_container_width=True)

# --- TAB 4 : JOURNAL ---
with tab_journal:
    st.subheader("Journal des Transactions")
    if 'journal_off' in locals() and journal_off: 
        st.dataframe(pd.DataFrame(journal_off), use_container_width=True)
    else: 
        st.info("Aucun signal détecté.")

# Auto-refresh
time.sleep(60); st.rerun()
