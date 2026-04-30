import streamlit as st
import pandas as pd
import chess.pgn
import io
import json
import requests
import plotly.graph_objects as go
import plotly.express as px
import random
from datetime import datetime
from chessdotcom import Client, get_player_games_by_month_pgn
import streamlit.components.v1 as components

# --- 1. KHẮC PHỤC LỖI USER-AGENT (CHESS.COM) ---
Client.request_config['headers']['User-Agent'] = "ChessTool-CheckOpening/1.2 (Contact: thilan89757@gmail.com)"

# --- CONFIG TRANG ---
st.set_page_config(page_title="ChessTool CheckOpening", page_icon="🎯", layout="wide")

# --- GOOGLE ANALYTICS SETUP ---
GA_ID = "G-GK0V9TT1PV" 

# Lưu ý: Không để link trong Markdown [], phải để link trần trong script
ga_code = f"""
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){{dataLayer.push(arguments);}}
        gtag('js', new Date());
        gtag('config', '{GA_ID}');
    </script>
"""
components.html(ga_code, height=0)

# --- 2. HÀM LOAD DB (CACHED) ---
@st.cache_data
def load_db(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            return { " ".join(k.split(' ')[:4]): v for k, v in raw.items() }
    except Exception as e:
        st.error(f"Lỗi load file ECO: {e}")
        return {}

# --- 3. FETCH DATA TỪ CHESS.COM (CÓ TIMEOUT) ---
def fetch_chess_com(user, count):
    all_pgn, found, now = "", 0, datetime.now()
    y, m = now.year, now.month
    for _ in range(3):
        try:
            res = get_player_games_by_month_pgn(user, y, m).json['pgn']['data']
            if res:
                all_pgn += res + "\n\n\n"
                found += len(res.strip().split('\n\n\n'))
            if found >= count: break
            m -= 1
            if m == 0: m, y = 12, y - 1
        except: break
    return all_pgn

# --- 4. HÀM PHÂN TÍCH ---
def analyze(pgn_text, db, user, threshold):
    if not pgn_text: return pd.DataFrame()
    pgn = io.StringIO(pgn_text)
    data, max_games, games_processed = [], 150, 0
    
    while games_processed < max_games:
        try:
            game = chess.pgn.read_game(pgn)
            if game is None: break 
            
            h = game.headers
            white, black = h.get("White", "").lower(), h.get("Black", "").lower()
            is_white = white == user.lower()
            
            if any(x in white or x in black or x in h.get("Event", "").lower() 
                   for x in ["bot", "ai", "stockfish", "computer", "komodo"]): continue

            board, info, is_broken, b_move, theo_len = game.board(), {"name": "Khai cuộc lạ"}, False, None, 0
            moves = list(game.mainline_moves())
            
            for i, move in enumerate(moves):
                board.push(move)
                fen = " ".join(board.fen().split(' ')[:4])
                if fen in db:
                    info, theo_len = db[fen], i + 1
                else:
                    if (i + 1) <= threshold: is_broken, b_move = True, i + 1
                    break
            
            res, pts = h.get("Result", "*"), 0.5
            if res == "1-0": pts = 1 if is_white else 0
            elif res == "0-1": pts = 1 if not is_white else 0

            data.append({
                "Khai cuộc": info.get("name"),
                "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
                "Nước sai": b_move if is_broken else "-",
                "Số nước thuộc": theo_len,
                "Kết quả": pts,
                "Link": h.get("Link", h.get("Site", "#"))
            })
            games_processed += 1
        except: continue
    return pd.DataFrame(data)

# --- 5. GIAO DIỆN (UI) ---
def main():
    st.sidebar.title("♟️ Check Opening")
    with st.sidebar:
        platform = st.selectbox("Nền tảng", ["Lichess", "Chess.com"])
        user = st.text_input(f"Username {platform}")
        mode = st.radio("Chế độ", ["Gần nhất", "Ngẫu nhiên"])
        count = st.slider("Số lượng ván", 5, 100, 20)
        threshold = st.slider("Threshold (Ngưỡng thuộc)", 1, 25, 8)
        rated = st.toggle("Chỉ ván Rated", value=True)
        st.info("Phiên bản 1.2")
        btn = st.button("🚀 PHÂN TÍCH NGAY", use_container_width=True)

    db = load_db("eco.json")

    if btn and user:
        with st.spinner(f"Đang soi ván của {user}..."):
            if platform == "Lichess":
                p = {"max": count if mode=="Gần nhất" else count*3, "opening":"true", "variant":"standard"}
                if rated: p["rated"] = "true"
                try:
                    r = requests.get(f"https://lichess.org/api/games/user/{user}", params=p, timeout=15)
                    pgn = r.text if r.status_code == 200 else None
                except: pgn = None
            else: pgn = fetch_chess_com(user, count)

            if pgn:
                if mode == "Ngẫu nhiên":
                    gs = [g for g in pgn.strip().split('\n\n\n') if g]
                    if gs: pgn = '\n\n\n'.join(random.sample(gs, min(len(gs), count)))
                
                df = analyze(pgn, db, user, threshold)
                if not df.empty:
                    st.subheader("📊 Thống kê tổng quan")
                    c1, c2, c3, c4 = st.columns(4)
                    win_r = df["Kết quả"].mean() * 100
                    broken = df[df["Trạng thái"]=="💔 Vỡ bài"]
                    c1.metric("Tỉ lệ Thắng", f"{win_r:.1f}%")
                    c2.metric("Tỉ lệ Vỡ bài", f"{(len(broken)/len(df))*100:.1f}%")
                    c3.metric("Thuộc max", f"{df['Số nước thuộc'].max()}")
                    c4.metric("Avg thuộc", f"{df['Số nước thuộc'].mean():.1f}")

                    st.divider()
                    t1, t2, t3 = st.tabs(["🎯 Gauge", "📈 Tần suất", "🔥 Heatmap"])
                    with t1:
                        fig = go.Figure(go.Indicator(mode="gauge+number", value=(len(broken)/len(df))*100, 
                                                    gauge={'bar': {'color': "#EF553B"}, 'axis': {'range': [0, 100]}}))
                        st.plotly_chart(fig, use_container_width=True)
                    with t2: st.bar_chart(df["Khai cuộc"].value_counts().head(10))
                    with t3:
                        if not broken.empty: st.plotly_chart(px.density_heatmap(broken, x="Nước sai", y="Khai cuộc", text_auto=True), use_container_width=True)
                        else: st.write("Không có ván vỡ bài.")

                    st.subheader("🏆 Hiệu quả Khai cuộc")
                    sum_df = df.groupby("Khai cuộc").agg(Ván=("Kết quả", "count"), Thắng=("Kết quả", lambda x: (x==1).sum()), Hòa=("Kết quả", lambda x: (x==0.5).sum()), Thua=("Kết quả", lambda x: (x==0).sum())).reset_index()
                    st.data_editor(sum_df.sort_values("Ván", ascending=False), use_container_width=True, hide_index=True)

                    st.subheader("📑 Chi tiết ván đấu")
                    st.data_editor(df, column_config={"Link": st.column_config.LinkColumn()}, use_container_width=True, hide_index=True)
                else: st.warning("Không tìm thấy ván phù hợp.")
            else: st.error("Lỗi kết nối API hoặc Username sai.")

if __name__ == "__main__":
    main()
