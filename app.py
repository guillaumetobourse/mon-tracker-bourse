import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import time

# --- FONCTION DE SCRAPING ROBUSTE ---
def fetch_boursorama_live(ticker):
    url = f"https://www.boursorama.com/cours/1rP{ticker}/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            price = soup.find("span", class_="c-instrument c-instrument--last").text.replace(" ", "").replace(",", ".").strip()
            return float(price)
    except Exception as e:
        st.error(f"Erreur de connexion Serveur -> Boursorama : {e}")
    return None

# --- LOGIQUE SERVEUR ---
st.title("🛰️ SBF120 Server-Side Monitor")

# On définit le ticker (ex: LVMH)
symbol = "MC"

# Récupération de la donnée
live_price = fetch_boursorama_live(symbol)

if live_price:
    st.metric(label=f"Cours Temps Réel {symbol}", value=f"{live_price} €")
    
    # Ici le serveur peut faire ses calculs (EMA, Min/Max)
    # et les afficher au lecteur distant.
    st.write(f"Dernière mise à jour : {time.strftime('%H:%M:%S')}")
else:
    st.warning("Le serveur tente de joindre Boursorama...")

# --- LE LIEN AVEC LE LECTEUR ---
# Cette commande dit au navigateur du lecteur de recharger la page toutes les 60s
st.info("Cette page se rafraîchit automatiquement toutes les minutes.")
time.sleep(60)
st.rerun()