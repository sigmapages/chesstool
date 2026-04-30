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

# --- SETUP & CONFIG ---
Client.request_config['headers']['User-Agent'] = "ChessTool-CheckOpening/1.0 (Contact: thilan89757@gmail.com)"
st.set_page_config(page_title="ChessTool CheckOpening VN", layout="wide")

# --- HÀM HỖ TRỢ ---
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
                all_pgn += res + "\n\n\n"; found += len(res.strip().split('\n\n\n'))
            if found >= count: break
            m -= 1
            if m == 0: m, y = 12, y - 1
        except: break
    return all_pgn

def analyze(pgn_text, db, user, threshold):
    pgn = io.StringIO(pgn_text)
    data = []
    while True:
        game = chess.pgn.read_game(pgn)
        if game is None: break
        
        h = game.headers
        white, black = h.get("White", "").lower(), h.get("Black", "").lower()
        is_white = white == user.lower()
        
        # Filter Bots
        if any(x in white or x in black or x in h.get("Event", "").lower() for x in ["bot", "ai", "stockfish"]): continue

        board, info, is_broken, b_move = game.board(), {"name": "Khai cuộc lạ", "eco": "???"}, False, None
        moves = list(game.mainline_moves())
        
        # Theo dõi chiều dài lý thuyết thuộc được
        theo_len = 0
        for i, m in enumerate(moves):
            board.push(m)
            fen = " ".join(board.fen().split(' ')[:4])
            if fen in db:
                info = db[fen]
                theo_len = i + 1
            else:
                if (i + 1) <= threshold:
                    is_broken, b_move = True, i + 1
                break
        
        res_str = h.get("Result", "*")
        pts = 0.5
        if res_str == "1-0": pts = 1 if is_white else 0
        elif res_str == "0-1": pts = 1 if not is_white else 0

        data.append({
            "Khai cuộc": info.get("name"),
            "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
            "Nước sai": b_move if is_broken else "-",
            "Số nước thuộc": theo_len,
            "Kết quả": pts, # 1: Thắng, 0.5: Hòa, 0: Thua
            "Link": h.get("Link", h.get("Site", "#"))
        })
    return pd.DataFrame(data)

# --- GIAO DIỆN ---
def main():
    st.sidebar.title("♟️ Chess Master Pro V4")
    platform = st.sidebar.selectbox("Platform", ["Lichess", "Chess.com"])
    user = st.sidebar.text_input(f"Username {platform}")
    mode = st.sidebar.radio("Chế độ chọn ván", ["Gần nhất", "Ngẫu nhiên"])
    count = st.sidebar.number_input("Số ván", 5, 100, 20)
    threshold = st.sidebar.slider("Ngưỡng Threshold", 1, 25, 8)
    rated = st.sidebar.toggle("Chỉ ván Rated", value=True)
    btn = st.sidebar.button("🚀 BẮT ĐẦU PHÂN TÍCH", use_container_width=True)

    db = load_db("eco.json")

    if btn and user:
        with st.spinner("Đang tính toán dữ liệu..."):
            if platform == "Lichess":
                p = {"max": count if mode=="Gần nhất" else count*3, "opening":"true", "variant":"standard"}
                if rated: p["rated"] = "true"
                res = requests.get(f"https://lichess.org/api/games/user/{user}", params=p, headers={"Accept": "application/x-chess-pgn"})
                pgn_data = res.text if res.status_code == 200 else None
            else: pgn_data = fetch_chess_com(user, count)

            if pgn_data:
                if mode == "Ngẫu nhiên":
                    gs = [g for g in pgn_data.strip().split('\n\n\n') if g]
                    pgn_data = '\n\n\n'.join(random.sample(gs, min(len(gs), count)))
                
                df = analyze(pgn_data, db, user, threshold)
                
                if not df.empty:
                    # --- 1. THỐNG KÊ TỔNG QUAN (Metrics) ---
                    st.subheader("📊 Chỉ số quan trọng")
                    m1, m2, m3, m4 = st.columns(4)
                    
                    win_rate = df["Kết quả"].mean() * 100
                    broken_pct = (len(df[df["Trạng thái"]=="💔 Vỡ bài"])/len(df))*100
                    max_theo = df["Số nước thuộc"].max()
                    min_theo = df["Số nước thuộc"].min()
                    avg_theo = df["Số nước thuộc"].mean()

                    m1.metric("Tỉ lệ Thắng", f"{win_rate:.1f}%")
                    m2.metric("Tỉ lệ Vỡ bài", f"{broken_pct:.1f}%", delta=f"{threshold} nước", delta_color="inverse")
                    m3.metric("Thuộc dài nhất", f"{max_theo} nước")
                    m4.metric("Trung bình thuộc", f"{avg_theo:.1f} nước")

                    st.divider()

                    # --- 2. CHUYỂN ĐỔI BIỂU ĐỒ ---
                    st.subheader("📈 Trực quan hóa")
                    chart_type = st.segmented_control(
                        "Chọn loại biểu đồ hiển thị:",
                        options=["Gauge (Độ phủ)", "Cột (Khai cuộc)", "Heatmap (Điểm yếu)"],
                        default="Gauge (Độ phủ)"
                    )

                    if chart_type == "Gauge (Độ phủ)":
                        fig = go.Figure(go.Indicator(
                            mode="gauge+number", value=broken_pct,
                            title={'text': "% Vỡ lý thuyết"},
                            gauge={'bar': {'color': "#EF553B"}, 'axis': {'range': [0, 100]},
                                   'steps': [{'range': [0, 20], 'color': "green"}, {'range': [20, 50], 'color': "orange"}]}
                        ))
                        st.plotly_chart(fig, use_container_width=True)
                    
                    elif chart_type == "Cột (Khai cuộc)":
                        fig = px.bar(df["Khai cuộc"].value_counts().reset_index(), 
                                     x="Khai cuộc", y="count", title="Tần suất các khai cuộc",
                                     labels={'count': 'Số ván', 'Khai cuộc': 'Tên khai cuộc'})
                        st.plotly_chart(fig, use_container_width=True)
                    
                    elif chart_type == "Heatmap (Điểm yếu)":
                        # Heatmap giả lập bằng Scatter hoặc Histogram nước sai
                        fig = px.density_heatmap(df[df["Nước sai"] != "-"], x="Nước sai", y="Khai cuộc",
                                               title="Vùng nước đi hay bị vỡ", text_auto=True)
                        st.plotly_chart(fig, use_container_width=True)

                    st.divider()

                    # --- 3. THỐNG KÊ CHI TIẾT THẮNG/THUA/HÒA ---
                    st.subheader("🏆 Thống kê hiệu quả Khai cuộc")
                    
                    # Logic gom nhóm tính thắng thua hòa
                    summary = df.groupby("Khai cuộc").agg(
                        Tổng=("Kết quả", "count"),
                        Thắng=("Kết quả", lambda x: (x == 1).sum()),
                        Hòa=("Kết quả", lambda x: (x == 0.5).sum()),
                        Thua=("Kết quả", lambda x: (x == 0).sum())
                    ).reset_index()
                    summary["% Thắng"] = (summary["Thắng"] / summary["Tổng"] * 100).round(1)
                    
                    st.data_editor(summary.sort_values("Tổng", ascending=False), use_container_width=True, hide_index=True)

                    # --- 4. DANH SÁCH VÁN ĐẤU ---
                    st.subheader("📑 Danh sách ván thực chiến")
                    st.data_editor(df, column_config={"Link": st.column_config.LinkColumn()}, use_container_width=True, hide_index=True)
                    
                    # Download
                    st.download_button("📥 Tải báo cáo CSV", df.to_csv(index=False).encode('utf-8'), "bao_cao_khai_cuoc.csv", "text/csv")

                else: st.warning("Không tìm thấy ván đấu phù hợp.")
            else: st.error("Lỗi kết nối API.")

if __name__ == "__main__": main()
