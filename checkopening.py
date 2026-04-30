from chessdotcom import Client

# Khai báo thông tin của bro để Chess.com không chặn
Client.request_config['headers']['User-Agent'] = (
    "ChessTool-CheckOpening/1.0 (Contact me at thilan89757@gmail.com)"
)
import streamlit as st
import pandas as pd
import chess.pgn
import io
import json
import requests
import plotly.graph_objects as go
import random
from datetime import datetime
from chessdotcom import get_player_games_by_month_pgn

# --- SETUP ---
st.set_page_config(page_title="Chess Coach Ultimate", page_icon="🎯", layout="wide")

# --- CORE LOGIC ---
@st.cache_data
def load_db(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            return { " ".join(k.split(' ')[:4]): v for k, v in raw.items() }
    except: return {}

def fetch_chess_com(user, count):
    all_pgn, found, now = "", 0, datetime.now()
    y, m = now.year, now.month
    for _ in range(3): # Lùi tối đa 3 tháng
        try:
            pgn = get_player_games_by_month_pgn(user, y, m).json['pgn']['data']
            if pgn:
                all_pgn += pgn + "\n\n\n"
                found += len(pgn.strip().split('\n\n\n'))
            if found >= count: break
            m -= 1
            if m == 0: m, y = 12, y - 1
        except: break
    return all_pgn

def analyze(pgn_text, db, user, threshold, platform):
    pgn = io.StringIO(pgn_text)
    data = []
    while True:
        game = chess.pgn.read_game(pgn)
        if game is None: break
        
        h = game.headers
        white, black = h.get("White", "").lower(), h.get("Black", "").lower()
        event = h.get("Event", "").lower()
        is_white = white == user.lower()
        
        # Filter Bots
        if any(x in white or x in black or x in event for x in ["bot", "ai", "stockfish"]): continue

        board, info, is_broken, b_move = game.board(), {"name": "Unknown"}, False, None
        moves = list(game.mainline_moves())
        
        for i, m in enumerate(moves):
            idx = i + 1
            board.push(m)
            fen = " ".join(board.fen().split(' ')[:4])
            if fen in db: info = db[fen]
            else:
                if idx <= threshold: is_broken, b_move = True, idx
                break
        
        res, pts = h.get("Result", "*"), 0.5
        if res == "1-0": pts = 1 if is_white else 0
        elif res == "0-1": pts = 1 if not is_white else 0

        data.append({
            "Khai cuộc": info.get("name"),
            "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
            "Nước sai": b_move if is_broken else "-",
            "Điểm": pts,
            "Link": h.get("Link", h.get("Site", "#"))
        })
    return pd.DataFrame(data)

# --- UI ---
def main():
    st.sidebar.title("♟️ HLV Dashboard")
    platform = st.sidebar.selectbox("Platform", ["Lichess", "Chess.com"])
    user = st.sidebar.text_input(f"Username {platform}")
    mode = st.sidebar.radio("Chế độ", ["Gần nhất", "Ngẫu nhiên"])
    count = st.sidebar.number_input("Số ván", 5, 100, 20)
    threshold = st.sidebar.slider("Threshold", 1, 20, 5)
    rated = st.sidebar.toggle("Chỉ ván Rated", value=True)
    btn = st.sidebar.button("🚀 PHÂN TÍCH")

    db = load_db("eco.json")

    if btn and user:
        with st.spinner("Đang soi ván..."):
            if platform == "Lichess":
                p = {"max": count if mode=="Gần nhất" else count*3, "opening":"true", "variant":"standard"}
                if rated: p["rated"] = "true"
                res = requests.get(f"https://lichess.org/api/games/user/{user}", params=p, headers={"Accept": "application/x-chess-pgn"})
                pgn_data = res.text if res.status_code == 200 else None
            else: pgn_data = fetch_chess_com(user, count)

            if pgn_data:
                if mode == "Ngẫu nhiên":
                    gs = pgn_data.strip().split('\n\n\n')
                    pgn_data = '\n\n\n'.join(random.sample(gs, min(len(gs), count)))
                
                df = analyze(pgn_data, db, user, threshold, platform)
                
                if not df.empty:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        broken_pct = (len(df[df["Trạng thái"]=="💔 Vỡ bài"])/len(df))*100
                        fig = go.Figure(go.Indicator(mode="gauge+number", value=broken_pct, title={'text': "% Vỡ bài"},
                                                    gauge={'bar': {'color': "#EF553B"}, 'axis': {'range': [0, 100]}}))
                        st.plotly_chart(fig, use_container_width=True)
                    with c2:
                        st.metric("Tỉ lệ Thắng", f"{df['Điểm'].mean()*100:.1f}%")
                        st.bar_chart(df["Khai cuộc"].value_counts().head(5))

                    st.subheader("📑 Chi tiết (Copy thoải mái)")
                    st.data_editor(df, column_config={"Link": st.column_config.LinkColumn()}, use_container_width=True, hide_index=True)
                else: st.warning("Không có ván phù hợp.")
            else: st.error("Lỗi lấy dữ liệu.")

if __name__ == "__main__": main()
