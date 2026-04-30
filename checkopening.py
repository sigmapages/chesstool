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

# --- 1. KHẮC PHỤC LỖI USER-AGENT (CHESS.COM) ---
Client.request_config['headers']['User-Agent'] = "ChessTool-CheckOpening/1.2 (Contact: thilan89757@gmail.com)"

# --- CONFIG TRANG ---
st.set_page_config(page_title="ChessTool CheckOpening", page_icon="🎯", layout="wide")

# --- 2. HÀM LOAD DB (CACHED) ---
@st.cache_data
def load_db(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            # Rút gọn FEN để tránh lệch biến thể nhỏ
            return { " ".join(k.split(' ')[:4]): v for k, v in raw.items() }
    except Exception as e:
        st.error(f"Lỗi load file ECO: {e}")
        return {}

# --- 3. FETCH DATA TỪ CHESS.COM (CÓ TIMEOUT) ---
def fetch_chess_com(user, count):
    all_pgn, found, now = "", 0, datetime.now()
    y, m = now.year, now.month
    
    # Chỉ lấy tối đa 3 tháng để tránh treo RAM
    for _ in range(3):
        try:
            # Chess.com API đôi khi chậm, tui bọc trong try-except
            res = get_player_games_by_month_pgn(user, y, m).json['pgn']['data']
            if res:
                all_pgn += res + "\n\n\n"
                found += len(res.strip().split('\n\n\n'))
            if found >= count: break
            m -= 1
            if m == 0: m, y = 12, y - 1
        except: break
    return all_pgn

# --- 4. HÀM PHÂN TÍCH (DIỆT LỖI NOT RESPONDING) ---
def analyze(pgn_text, db, user, threshold):
    if not pgn_text: return pd.DataFrame()
    
    pgn = io.StringIO(pgn_text)
    data = []
    
    # Giới hạn số ván tối đa để không cháy RAM server
    max_games = 150 
    games_processed = 0
    
    while games_processed < max_games:
        try:
            game = chess.pgn.read_game(pgn)
            if game is None: break # THOÁT AN TOÀN
            
            headers = game.headers
            white = headers.get("White", "").lower()
            black = headers.get("Black", "").lower()
            event = headers.get("Event", "").lower()
            is_white = white == user.lower()
            
            # 5. BỘ LỌC BOT (ANTI-NOISE)
            is_bot = any(x in white or x in black or x in event 
                         for x in ["bot", "ai", "stockfish", "computer", "komodo"])
            if is_bot: continue

            board, info = game.board(), {"name": "Khai cuộc lạ", "eco": "???"}
            is_broken, b_move, theo_len = False, None, 0
            moves = list(game.mainline_moves())
            
            # Duyệt nước đi để check Threshold
            for i, move in enumerate(moves):
                board.push(move)
                fen = " ".join(board.fen().split(' ')[:4])
                if fen in db:
                    info = db[fen]
                    theo_len = i + 1
                else:
                    if (i + 1) <= threshold:
                        is_broken, b_move = True, i + 1
                    break
            
            res_str, pts = headers.get("Result", "*"), 0.5
            if res_str == "1-0": pts = 1 if is_white else 0
            elif res_str == "0-1": pts = 1 if not is_white else 0

            data.append({
                "Khai cuộc": info.get("name"),
                "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
                "Nước sai": b_move if is_broken else "-",
                "Số nước thuộc": theo_len,
                "Kết quả": pts,
                "Link": headers.get("Link", headers.get("Site", "#"))
            })
            games_processed += 1
        except Exception:
            continue # Bỏ qua ván lỗi, không để app treo
            
    return pd.DataFrame(data)

# --- 6. GIAO DIỆN (UI) ---
def main():
    st.sidebar.title("♟️ Check Opening Dashboard")
    
    with st.sidebar:
        platform = st.selectbox("Nền tảng", ["Lichess", "Chess.com"])
        user = st.text_input(f"Username {platform}")
        mode = st.radio("Chế độ", ["Gần nhất", "Ngẫu nhiên"])
        count = st.slider("Số lượng ván", 5, 100, 20)
        threshold = st.slider("Threshold (Ngưỡng thuộc)", 1, 25, 8)
        rated = st.toggle("Chỉ ván Rated", value=True)
        st.divider()
        st.info("Bản V1.2")
        btn = st.button("🚀 PHÂN TÍCH NGAY", use_container_width=True)

    db = load_db("eco.json")

    if btn and user:
        with st.spinner(f"Đang phân tích ván đấu của {user}..."):
            # Fetch dữ liệu
            if platform == "Lichess":
                p = {"max": count if mode=="Gần nhất" else count*3, "opening":"true", "variant":"standard"}
                if rated: p["rated"] = "true"
                try:
                    res = requests.get(f"https://lichess.org/api/games/user/{user}", params=p, timeout=15)
                    pgn_data = res.text if res.status_code == 200 else None
                except: pgn_data = None
            else:
                pgn_data = fetch_chess_com(user, count)

            if pgn_data:
                # Logic Random
                if mode == "Ngẫu nhiên":
                    gs = [g for g in pgn_data.strip().split('\n\n\n') if g]
                    if gs: pgn_data = '\n\n\n'.join(random.sample(gs, min(len(gs), count)))
                
                df = analyze(pgn_data, db, user, threshold)
                
                if not df.empty:
                    # RENDER METRICS
                    st.subheader("📊 Thống kê tổng quan")
                    m1, m2, m3, m4 = st.columns(4)
                    
                    win_rate = df["Kết quả"].mean() * 100
                    broken_df = df[df["Trạng thái"]=="💔 Vỡ bài"]
                    broken_pct = (len(broken_df)/len(df))*100

                    m1.metric("Tỉ lệ Thắng", f"{win_rate:.1f}%")
                    m2.metric("Tỉ lệ Vỡ bài", f"{broken_pct:.1f}%")
                    m3.metric("Thuộc dài nhất", f"{df['Số nước thuộc'].max()} nước")
                    m4.metric("Trung bình thuộc", f"{df['Số nước thuộc'].mean():.1f}")

                    # RENDER CHARTS
                    st.divider()
                    tab1, tab2, tab3 = st.tabs(["🎯 Gauge", "📈 Tần suất", "🔥 Heatmap"])
                    
                    with tab1:
                        fig = go.Figure(go.Indicator(
                            mode="gauge+number", value=broken_pct,
                            title={'text': "% Vỡ lý thuyết"},
                            gauge={'bar': {'color': "#EF553B"}, 'axis': {'range': [0, 100]}}
                        ))
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with tab2:
                        st.bar_chart(df["Khai cuộc"].value_counts().head(10))
                    
                    with tab3:
                        if not broken_df.empty:
                            fig_h = px.density_heatmap(broken_df, x="Nước sai", y="Khai cuộc", text_auto=True)
                            st.plotly_chart(fig_h, use_container_width=True)
                        else: st.write("Chưa đủ dữ liệu để vẽ Heatmap.")

                    # THỐNG KÊ CHI TIẾT
                    st.subheader("🏆 Hiệu quả từng khai cuộc")
                    summary = df.groupby("Khai cuộc").agg(
                        Ván=("Kết quả", "count"),
                        Thắng=("Kết quả", lambda x: (x == 1).sum()),
                        Hòa=("Kết quả", lambda x: (x == 0.5).sum()),
                        Thua=("Kết quả", lambda x: (x == 0).sum())
                    ).reset_index()
                    st.data_editor(summary.sort_values("Ván", ascending=False), use_container_width=True, hide_index=True)

                    # BẢNG VÀ DOWNLOAD
                    st.subheader("📑 Danh sách ván đấu (Copy được)")
                    st.data_editor(df, column_config={"Link": st.column_config.LinkColumn()}, use_container_width=True, hide_index=True)
                    st.download_button("📥 Tải file CSV", df.to_csv(index=False).encode('utf-8'), "bao_cao_khai_cuoc.csv", "text/csv")
                else:
                    st.warning("Không tìm thấy ván đấu phù hợp sau khi lọc.")
            else:
                st.error("Không thể kết nối API. Vui lòng kiểm tra lại Username.")

if __name__ == "__main__":
    main()
