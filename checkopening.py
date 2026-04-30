import streamlit as st
import pandas as pd
import chess.pgn
import io, json, requests, random
from datetime import datetime
from chessdotcom import Client, get_player_games_by_month_pgn
import streamlit.components.v1 as components
import plotly.graph_objects as go
import plotly.express as px

# --- SETUP HỆ THỐNG ---
Client.request_config['headers']['User-Agent'] = "ChessTool-CheckOpening/1.3 (thilan89757@gmail.com)"
st.set_page_config(page_title="ChessTool CheckOpening", page_icon="🎯", layout="wide")

# --- GOOGLE ANALYTICS (GA4) ---
GA_ID = "G-GK0V9TT1PV"
ga_code = f"""
    <script async src="[https://www.googletagmanager.com/gtag/js?id=](https://www.googletagmanager.com/gtag/js?id=){GA_ID}"></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){{dataLayer.push(arguments);}}
        gtag('js', new Date()); gtag('config', '{GA_ID}');
    </script>
"""
components.html(ga_code, height=0)

# --- UTILS ---
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
    for _ in range(3):
        try:
            res = get_player_games_by_month_pgn(user, y, m).json['pgn']['data']
            if res:
                all_pgn += res + "\n\n\n"
                found += len([g for g in res.split('\n\n\n') if g])
            if found >= count: break
            m -= 1
            if m == 0: m, y = 12, y - 1
        except: break
    return all_pgn

def analyze(pgn_text, db, user, threshold):
    if not pgn_text: return pd.DataFrame()
    pgn_io = io.StringIO(pgn_text)
    data, max_games, processed = [], 150, 0
    
    while processed < max_games:
        game = chess.pgn.read_game(pgn_io)
        if game is None: break 
        
        h = game.headers
        white, black = h.get("White", "").lower(), h.get("Black", "").lower()
        is_white = white == user.lower()
        if any(x in white or x in black or x in h.get("Event", "").lower() for x in ["bot", "ai", "stockfish", "computer"]): continue

        board, info, break_move, theo_len = game.board(), {"name": "Khai cuộc lạ"}, None, 0
        moves = list(game.mainline_moves())
        
        for i, move in enumerate(moves):
            board.push(move)
            fen = " ".join(board.fen().split(' ')[:4])
            if fen in db:
                info, theo_len = db[fen], i + 1
            else:
                # Chỉ coi là "Vỡ bài" nếu nước đi sai nằm TRONG ngưỡng threshold
                if (i + 1) <= threshold:
                    break_move = i + 1
                break
        
        res_val = h.get("Result", "*")
        pts = 1 if (res_val=="1-0" and is_white) or (res_val=="0-1" and not is_white) else (0.5 if res_val=="1/2-1/2" else 0)

        data.append({
            "Khai cuộc": info.get("name"),
            "Trạng thái": "💔 Vỡ bài" if break_move else "✅ Thuộc bài",
            "Nước sai": break_move if break_move else "-",
            "Số nước thuộc": theo_len,
            "Kết quả": pts,
            "Link": h.get("Link", h.get("Site", "#"))
        })
        processed += 1
    return pd.DataFrame(data)

# --- UI MAIN ---
def main():
    st.sidebar.title("♟️ Check Opening V1.3")
    with st.sidebar:
        plat = st.selectbox("Nền tảng", ["Lichess", "Chess.com"])
        user = st.text_input(f"Username {plat}")
        mode = st.radio("Chế độ", ["Gần nhất", "Ngẫu nhiên"])
        count = st.slider("Số lượng ván", 5, 100, 20)
        ts = st.slider("Threshold (Ngưỡng thuộc)", 1, 25, 8)
        rated = st.toggle("Chỉ ván Rated", value=True)
        btn = st.button("🚀 PHÂN TÍCH NGAY", use_container_width=True)

    db = load_db("eco.json")

    if btn and user:
        with st.spinner(f"Đang soi ván của {user}..."):
            if plat == "Lichess":
                params = {"max": count if mode=="Gần nhất" else count*3, "opening":"true", "variant":"standard"}
                if rated: params["rated"] = "true"
                try:
                    r = requests.get(f"[https://lichess.org/api/games/user/](https://lichess.org/api/games/user/){user}", params=params, timeout=15)
                    pgn = r.text if r.status_code == 200 else None
                except: pgn = None
            else: pgn = fetch_chess_com(user, count)

            if pgn:
                if mode == "Ngẫu nhiên":
                    gs = [g for g in pgn.strip().split('\n\n\n') if g]
                    if gs: pgn = '\n\n\n'.join(random.sample(gs, min(len(gs), count)))
                
                df = analyze(pgn, db, user, ts)
                if not df.empty:
                    st.subheader("📊 Thống kê tổng quan")
                    c1, c2, c3, c4 = st.columns(4)
                    broken_df = df[df["Trạng thái"]=="💔 Vỡ bài"]
                    c1.metric("Tỉ lệ Thắng", f"{df['Kết quả'].mean()*100:.1f}%")
                    c2.metric("Tỉ lệ Vỡ bài", f"{(len(broken_df)/len(df))*100:.1f}%")
                    c3.metric("Thuộc dài nhất", f"{df['Số nước thuộc'].max()}")
                    c4.metric("Trung bình thuộc", f"{df['Số nước thuộc'].mean():.1f}")

                    st.divider()
                    t1, t2, t3 = st.tabs(["🎯 Gauge", "📈 Tần suất", "🔥 Heatmap"])
                    with t1:
                        st.plotly_chart(go.Figure(go.Indicator(mode="gauge+number", value=(len(broken_df)/len(df))*100, title={'text': "% Vỡ bài (Trong ngưỡng)"}, gauge={'bar': {'color': "#EF553B"}, 'axis': {'range': [0, 100]}})), use_container_width=True)
                    with t2: st.bar_chart(df["Khai cuộc"].value_counts().head(10))
                    with t3:
                        if not broken_df.empty: st.plotly_chart(px.density_heatmap(broken_df, x="Nước sai", y="Khai cuộc", text_auto=True), use_container_width=True)
                        else: st.write("Học sinh thuộc bài quá, không có gì để vẽ heatmap!")

                    st.subheader("🏆 Hiệu quả Khai cuộc")
                    sum_df = df.groupby("Khai cuộc").agg(Ván=("Kết quả", "count"), Thắng=("Kết quả", lambda x: (x==1).sum()), Hòa=("Kết quả", lambda x: (x==0.5).sum()), Thua=("Kết quả", lambda x: (x==0).sum())).reset_index()
                    st.data_editor(sum_df.sort_values("Ván", ascending=False), use_container_width=True, hide_index=True)

                    st.subheader("📑 Chi tiết ván đấu")
                    st.data_editor(df, column_config={"Link": st.column_config.LinkColumn()}, use_container_width=True, hide_index=True)
                    st.download_button("📥 Tải file CSV", df.to_csv(index=False).encode('utf-8'), "bao_cao_khai_cuoc.csv", "text/csv")
                else: st.warning("Không tìm thấy ván phù hợp.")
            else: st.error("Lỗi kết nối API.")

if __name__ == "__main__":
    main()
