import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime
import time
import json

from streamlit_autorefresh import st_autorefresh

# Force le rafraîchissement toutes les 60 secondes
# On lui donne un nom (key) pour éviter les conflits
#st_autorefresh(interval=60 * 1000, key="datarefresh")

# --- 1. INITIALISATION (CRITIQUE : Doit être au tout début) ---
if 'tickers' not in st.session_state:
    st.session_state.tickers = {}

st.set_page_config(layout="wide", page_title="Market Live Monitor")

# --- 2. FONCTIONS DE RÉCUPÉRATION ---

def get_init_market_data(symbol):
    """Initialisation Yahoo Finance : Stats 15j + Volatilité 5j"""
    t = f"{symbol}.PA"
    try:
        df = yf.download(t, period="20d", interval="1d", auto_adjust=True, progress=False)
        if df.empty: return None
        # Aplatir les colonnes MultiIndex de Yahoo
        highs = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']
        lows = df['Low'].iloc[:, 0] if isinstance(df['Low'], pd.DataFrame) else df['Low']
        closes = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']

        log_ret = np.log(closes / closes.shift(1))
        return {
            'max15': float(highs.tail(15).max()),
            'min15': float(lows.tail(15).min()),
            'max5': float(highs.tail(5).max()),
            'min5': float(lows.tail(5).min()),
            'vol5j': float(log_ret.tail(5).std() * np.sqrt(252) * 100)
        }
    except: return None

def scrape_boursorama_data(symbol):
    """Scraping Prix et Volume sur Boursorama"""
    url = f"https://www.boursorama.com/cours/1rP{symbol}/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')

        price = float(soup.find("span", {"class": "c-instrument--last"}).text.replace(" ", "").replace(",",".").strip())
        vol_tag = soup.find("div", string="Volume")
        volume = int(''.join(filter(str.isdigit, vol_tag.find_next("div").text))) if vol_tag else 0
        return {"price": price, "volume": volume}
    except: return None

# --- 3. INTERFACE UTILISATEUR ---

tab1, tab2 = st.tabs(["🎯 Suivi Live Multi-Graphes", "🌍 Comparatif Marché"])


# --- ONGLET 1 : GRAPHIQUES EN TEMPS RÉEL ---
with tab1:
    st.sidebar.header("Ajouter un titre")
    new_s = st.sidebar.text_input("Symbole (ex: GLE)").upper().strip()
    if st.sidebar.button("Ajouter"):
        if new_s not in st.session_state.tickers:
            stats = get_init_market_data(new_s)
            if stats:
                st.session_state.tickers[new_s] = {'stats': stats, 'live_df': pd.DataFrame(columns=['Time', 'Price', 'Volat', 'Volume'])}
                st.rerun()

    # On crée une fonction décorée avec @st.fragment
    # Elle va se rafraîchir SEULE toutes les 60s sans bloquer le reste du script
    @st.fragment(run_every=60)
    def update_charts():
        if not st.session_state.tickers:
            st.info("Ajoutez des tickers dans la barre latérale pour commencer.")
            return

        cols = st.columns(2)
        for idx, (symb, data) in enumerate(list(st.session_state.tickers.items())):
            live = scrape_boursorama_data(symb)
            if live:
                now = datetime.now().strftime("%H:%M")
                v = data['live_df']['Price'].tail(5).pct_change().std() * 100 if len(data['live_df']) >= 5 else 0
                new_row = pd.DataFrame({'Time':[now], 'Price':[live['price']], 'Volat':[v], 'Volume':[live['volume']]})
                data['live_df'] = pd.concat([data['live_df'], new_row]).tail(100)

                # Titre dynamique sans lignes horizontales
                s = data['stats']
                title = f"<b>{symb} : {live['price']:.2f}€</b><br><span style='font-size:12px;color:gray'>H/L Jour: {data['live_df']['Price'].max():.2f}/{data['live_df']['Price'].min():.2f} | 5J: {s['max5']:.2f}/{s['min5']:.2f} | 15J: {s['max15']:.2f}/{s['min15']:.2f}</span>"

                fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.5, 0.25], subplot_titles=(title, "Volatilité"))
                fig.add_trace(go.Scatter(x=data['live_df']['Time'], y=data['live_df']['Price'], line=dict(color="#00f2ff", width=2)), row=1, col=1)
                fig.add_trace(go.Scatter(x=data['live_df']['Time'], y=data['live_df']['Volat'], fill='tozeroy', line=dict(color="orange")), row=2, col=1)
                fig.update_layout(height=600, template="plotly_dark", showlegend=False, margin=dict(t=80))

                with cols[idx % 2]:
                    st.plotly_chart(fig, use_container_width=True, key=f"fig_{symb}")
                    if st.button(f"Retirer {symb}", key=f"del_{symb}"):
                        del st.session_state.tickers[symb]
                        st.rerun()

    update_charts()

# --- ONGLET 2 : RÉSUMÉ DU MARCHÉ ---
with tab2:
    st.header("🌍 Analyse Comparative & Fondamentaux")
    indice_name = st.selectbox("Choisir l'indice", ["CAC 40", "SBF 120"])
    
    if st.button("🚀 Lancer l'analyse du marché"):
        # Liste simplifiée (Top CAC 40) - À étendre pour le SBF 120
        market_list = ["AC", "AI", "AIR", "MT", "BNP", "EN", "CAP", "CA", "ACA", "BN", "DSY", "ENGI", "EL", "ERF", "RMS", "KER", "OR", "LR", "MC", "ML", "ORA", "RI", "PUB", "RNO", "SAF", "SGO", "SAN", "SU", "GLE", "SW", "TEP", "TTE", "HO", "URW", "VIE", "VIV", "VGP", "WLN"]
        
        summary = []
        bar = st.progress(0)
        
        for i, s in enumerate(market_list):
            ticker_symbol = f"{s}.PA"
            tk = yf.Ticker(ticker_symbol)
            
            # 1. Récupération historique (plus fiable pour le prix et les bornes)
            hist = yf.download(ticker_symbol, period="20d", interval="1d", auto_adjust=True, progress=False)
            
            if not hist.empty:
                # SÉCURITÉ MULTI-INDEX : on extrait les séries proprement
                def get_series(df, column):
                    if column in df.columns:
                        col_data = df[column]
                        if isinstance(col_data, pd.DataFrame):
                            return col_data.iloc[:, 0] # Prend la 1ère colonne si MultiIndex
                        return col_data
                    return None

                closes = get_series(hist, 'Close')
                highs = get_series(hist, 'High')
                lows = get_series(hist, 'Low')

                print(closes.head())

                if closes is not None and len(closes) > 0:
                    # Prix actuel (dernière clôture connue)
                    current_p = float(closes.iloc[-1])
                    
                    # Bornes 15 jours
                    m15 = float(lows.tail(15).min())
                    x15 = float(highs.tail(15).max())
                    
                    # Calcul Position (0% = Min, 100% = Max)
                    diff = x15 - m15
                    pos_15 = ((current_p - m15) / diff * 100) if diff != 0 else 50
                    
                    # 2. Récupération Fondamentale (yfinance info)
                    info = tk.info
                    
                    summary.append({
                        "Ticker": s,
                        "Nom": info.get('longName', s),
                        "Secteur": info.get('sector', 'N/A'),
                        "Prix (€)": current_p,
                        "Position 15j (%)": pos_15,
                        "PER (P/E)": info.get('trailingPE'),
                        "Rendement (%)": (info.get('dividendYield', 0) * 100) if info.get('dividendYield') else 0,
                        "PEG Ratio": info.get('pegRatio'),
                        "EV/EBITDA": info.get('enterpriseToEbitda')
                    })
            
            bar.progress((i + 1) / len(market_list))
        
        # 3. Création du DataFrame et Affichage
        df_res = pd.DataFrame(summary)
        
        if not df_res.empty:
            st.subheader(f"Résultats pour le {indice_name}")
            st.dataframe(
                df_res.style.background_gradient(subset=['Position 15j (%)'], cmap='RdYlGn')
                .background_gradient(subset=['PER (P/E)'], cmap='YlGn_r')
                .format({
                    "Prix (€)": "{:.2f}",
                    "Position 15j (%)": "{:.1f}%",
                    "PER (P/E)": "{:.1f}",
                    "Rendement (%)": "{:.2f}%",
                    "PEG Ratio": "{:.2f}",
                    "EV/EBITDA": "{:.1f}"
                }, na_rep="N/A"),
                use_container_width=True
            )
        else:
            st.error("Impossible de récupérer les données. Vérifiez les symboles ou la connexion.")
        summary = []
        bar = st.progress(0)
        
        for i, s in enumerate(market_list):
            ticker_name = f"{s}.PA"
            tk = yf.Ticker(ticker_name)
            
            # 1. Données Historiques (Technique)
            hist = tk.history(period="20d")
            if hist.empty: continue
            
            # 2. Données Fondamentales (Info)
            info = tk.info
            
            # Calcul Position 15j
            max_15 = hist['High'].tail(15).max()
            min_15 = hist['Low'].tail(15).min()
            price = hist['Close'].iloc[-1]
            pos_15 = ((price - min_15) / (max_15 - min_15) * 100) if (max_15 - min_15) != 0 else 50
            
            summary.append({
                "Ticker": s,
                "Nom": info.get('longName', s),
                "Secteur": info.get('sector', 'N/A'),
                "Prix (€)": round(price, 2),
                "Position 15j (%)": round(pos_15, 1),
                "P/E (PER)": info.get('trailingPE', None),
                "Rendement (%)": round(info.get('dividendYield', 0) * 100, 2) if info.get('dividendYield') else 0,
                "PEG Ratio": info.get('pegRatio', None),
                "EV/EBITDA": info.get('enterpriseToEbitda', None)
            })
            bar.progress((i + 1) / len(market_list))
        
        df_market = pd.DataFrame(summary)
        
        # --- Affichage avec mise en forme ---
        st.subheader(f"Tableau de bord comparatif : {len(df_market)} actions")
        
        # On définit des règles de couleurs pour le P/E (PER)
        # Un PER faible (< 15) est souvent considéré comme une action "value"
        st.dataframe(
            df_market.style.background_gradient(subset=['Position 15j (%)'], cmap='RdYlGn')
            .background_gradient(subset=['P/E (PER)'], cmap='YlGn_r')
            .format({
                "Prix (€)": "{:.2f}",
                "Position 15j (%)": "{:.1f}%",
                "P/E (PER)": "{:.1f}",
                "Rendement (%)": "{:.2f}%",
                "PEG Ratio": "{:.2f}",
                "EV/EBITDA": "{:.1f}"
            }, na_rep="N/A")  # <--- AJOUT CRUCIAL : gère les valeurs None
            , use_container_width=True
        )
        
        # --- Analyse Graphique par Secteur ---
        st.subheader("Analyse Sectorielle : Position Moyenne")
        secteur_analysis = df_market.groupby('Secteur')['Position 15j (%)'].mean().sort_values()
        st.bar_chart(secteur_analysis)
