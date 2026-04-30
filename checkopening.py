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

# --- PHẦN 1: CÀI ĐẶT HỆ THỐNG & USER AGENT ---
MY_HEADERS = {"User-Agent": "ChessTool-CheckOpening/1.1 (thilan89757@gmail.com)"}
Client.request_config['headers']['User-Agent'] = MY_HEADERS["User-Agent"]

# --- PHẦN 2: CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="ChessTool CheckOpening",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PHẦN 3: GA4 TRACKING ---
GA_ID = "G-GK0V9TT1PV"
ga_du_kich = f"""
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){{dataLayer.push(arguments);}}
        gtag('js', new Date());
        gtag('config', '{GA_ID}');
        console.log('Targeting GA4: {GA_ID}');
    </script>
"""
components.html(ga_du_kich, height=0)

# --- PHẦN 4: HÀM LOAD CƠ SỞ DỮ LIỆU ---
@st.cache_data
def load_db(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            processed_db = {}
            for k, v in raw.items():
                parts = k.split(' ')
                short_fen = " ".join(parts[:4])
                processed_db[short_fen] = v
            return processed_db
    except Exception as e:
        st.error(f"Lỗi load eco.json: {e}")
        return {}

# --- PHẦN 5: HÀM LẤY DỮ LIỆU CHESS.COM ---
def fetch_chess_com_games(username, limit_count):
    all_pgn_data = ""
    games_found = 0
    current_date = datetime.now()
    curr_year, curr_month = current_date.year, current_date.month

    for _ in range(3):
        try:
            response = get_player_games_by_month_pgn(username, curr_year, curr_month)
            month_pgn = response.json['pgn']['data']
            if month_pgn:
                all_pgn_data += month_pgn + "\n\n\n"
                temp_games = month_pgn.strip().split('\n\n\n')
                games_found += len(temp_games)
            if games_found >= limit_count: break
            curr_month -= 1
            if curr_month == 0:
                curr_month = 12
                curr_year -= 1
        except: break
    return all_pgn_data

# --- PHẦN 6: HÀM XỬ LÝ CSV (CẢI TIẾN) ---
def convert_df_to_csv(df, target_user):
    if df.empty: return None
    
    # Tính toán thông số
    total_games = len(df)
    win_points = df["Kết quả"].sum()
    win_rate = (win_points / total_games) * 100
    avg_theory = df["Số nước thuộc"].mean()
    broken_count = len(df[df["Trạng thái"] == "💔 Vỡ bài"])
    
    # Tạo dòng Summary
    summary_rows = [
        {}, # Dòng trống
        {"Khai cuộc": "--- BÁO CÁO TỔNG KẾT ---"},
        {"Khai cuộc": f"Người chơi: {target_user}"},
        {"Khai cuộc": f"Tổng số ván: {total_games}"},
        {"Khai cuộc": f"Tỉ lệ thắng: {win_rate:.1f}%"},
        {"Khai cuộc": f"Trung bình số nước thuộc bài: {avg_theory:.1f}"},
        {"Khai cuộc": f"Số ván vỡ bài sớm: {broken_count}"},
        {"Khai cuộc": f"Ngày xuất báo cáo: {datetime.now().strftime('%d/%m/%Y %H:%M')}"},
        {"Khai cuộc": "Nguồn: ChessTool CheckOpening (by @YourTikTok)"}
    ]
    df_summary = pd.DataFrame(summary_rows)
    
    # Nối vào DF chính
    df_final = pd.concat([df, df_summary], ignore_index=True)
    
    # Xuất ra bytes với utf-8-sig
    return df_final.to_csv(index=False).encode('utf-8-sig')

# --- PHẦN 7: PHÂN TÍCH LOGIC ---
def analyze_games(pgn_content, opening_db, target_user, move_threshold):
    if not pgn_content: return pd.DataFrame()
    pgn_io = io.StringIO(pgn_content)
    analysis_results, games_count = [], 0
    
    while True:
        game = chess.pgn.read_game(pgn_io)
        if game is None or games_count >= 150: break
        
        headers = game.headers
        white_player = headers.get("White", "Unknown").lower()
        black_player = headers.get("Black", "Unknown").lower()
        
        # Lọc Bot
        bot_keywords = ["bot", "ai", "stockfish", "computer", "engine"]
        if any(k in white_player or k in black_player for k in bot_keywords): continue

        user_is_white = (white_player == target_user.lower())
        board = game.board()
        current_opening = {"name": "Khai cuộc lạ"}
        is_broken, first_wrong, theory_len = False, None, 0
        
        for index, move in enumerate(game.mainline_moves()):
            board.push(move)
            current_fen = " ".join(board.fen().split(' ')[:4])
            if current_fen in opening_db:
                current_opening = opening_db[current_fen]
                theory_len = index + 1
            else:
                if (index + 1) <= move_threshold:
                    is_broken, first_wrong = True, index + 1
                break
        
        res = headers.get("Result", "*")
        pts = 0.5
        if res == "1-0": pts = 1 if user_is_white else 0
        elif res == "0-1": pts = 0 if user_is_white else 1
            
        analysis_results.append({
            "Khai cuộc": current_opening.get("name"),
            "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
            "Nước sai": first_wrong if is_broken else "-",
            "Số nước thuộc": theory_len,
            "Kết quả": pts,
            "Link ván đấu": headers.get("Link", headers.get("Site", ""))
        })
        games_count += 1
    return pd.DataFrame(analysis_results)

# --- PHẦN 8: MAIN UI ---
def main():
    st.sidebar.markdown("# ♟️ Check Opening V1.4")
    with st.sidebar:
        platform = st.selectbox("Nền tảng:", ["Lichess", "Chess.com"])
        target_username = st.text_input(f"Username {platform}:")
        game_limit = st.slider("Số lượng ván:", 5, 100, 20)
        threshold = st.slider("Ngưỡng thuộc bài:", 1, 25, 8)
        run_button = st.button("🚀 PHÂN TÍCH", use_container_width=True)

    db_data = load_db("eco.json")
    
    if run_button and target_username:
        with st.spinner("Đang soi ván..."):
            if platform == "Lichess":
                api_url = f"https://lichess.org/api/games/user/{target_username}"
                r = requests.get(api_url, params={"max": game_limit, "opening": "true"}, headers=MY_HEADERS)
                final_pgn = r.text if r.status_code == 200 else ""
            else:
                final_pgn = fetch_chess_com_games(target_username, game_limit)

            df_result = analyze_games(final_pgn, db_data, target_username, threshold)
            
            if not df_result.empty:
                st.title(f"📊 Kết quả cho {target_username}")
                # (Phần Metrics và Biểu đồ giữ nguyên như code cũ của bro nhé...)
                
                # BẢNG CHI TIẾT
                st.subheader("📑 Chi tiết ván đấu")
                st.dataframe(df_result, use_container_width=True)
                
                # NÚT DOWNLOAD CẢI TIẾN
                csv_bytes = convert_df_to_csv(df_result, target_username)
                st.download_button(
                    label="📥 Tải báo cáo CSV (Đã kèm Summary)",
                    data=csv_bytes,
                    file_name=f"ChessReport_{target_username}.csv",
                    mime="text/csv",
                )
            else:
                st.warning("Không có dữ liệu!")

if __name__ == "__main__":
    main()
