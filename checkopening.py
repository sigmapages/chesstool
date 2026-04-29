import streamlit as st
import pandas as pd
import chess.pgn
import io
import json
import requests
import plotly.graph_objects as go
import plotly.express as px
import random

# --- CONFIG ---
LICHESS_API_URL = "https://lichess.org/api/games/user/"

st.set_page_config(page_title="Chess Pro Analyzer", page_icon="♟️", layout="wide")

# --- CORE FUNCTIONS ---

@st.cache_data
def load_eco_database(file_path):
    """Load JSON và chuẩn hóa FEN Key"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            clean_db = { " ".join(k.split(' ')[:4]): v for k, v in raw_data.items() }
            return clean_db
    except Exception as e:
        st.error(f"Lỗi load file ECO: {e}")
        return {}

def fetch_lichess_games(username, num_to_analyze, mode, color):
    """Kéo dữ liệu với 2 chế độ: Gần nhất hoặc Random"""
    # Nếu chọn Random, ta kéo về nhiều hơn một chút để bốc cho chuẩn
    fetch_count = num_to_analyze if mode == "Gần nhất" else num_to_analyze * 3
    
    params = {
        "max": fetch_count,
        "opening": "true",
        "finished": "true",
        "variant": "standard"
    }
    if color != "Both":
        params["color"] = color.lower()
    
    headers = {"Accept": "application/x-chess-pgn"}
    response = requests.get(f"{LICHESS_API_URL}{username}", params=params, headers=headers)
    
    if response.status_code != 200:
        return None

    pgn_data = response.text
    if mode == "Gần nhất":
        return pgn_data
    
    # Logic Random: Tách các ván ra list, xáo trộn rồi gộp lại
    games = pgn_data.strip().split('\n\n\n')
    if len(games) > num_to_analyze:
        random_games = random.sample(games, num_to_analyze)
        return '\n\n\n'.join(random_games)
    return pgn_data

def analyze_game(pgn_text, eco_db, username, filter_bot):
    """Phân tích ván đấu, lọc Bot và tìm Breakpoint"""
    pgn = io.StringIO(pgn_text)
    game_results = []
    
    while True:
        game = chess.pgn.read_game(pgn)
        if game is None: break
            
        headers = game.headers
        white = headers.get("White", "").lower()
        black = headers.get("Black", "").lower()
        event = headers.get("Event", "").lower()

        # --- BỘ LỌC BOT & AI ---
        if filter_bot:
            is_bot = any(x in white or x in black or x in event for x in ["bot", "ai", "stockfish", "computer"])
            if is_bot: continue

        player_is_white = white == username.lower()
        player_color = "White" if player_is_white else "Black"
        result = headers.get("Result", "*")
        
        win_val = 0.5
        if result == "1-0": win_val = 1 if player_is_white else 0
        elif result == "0-1": win_val = 1 if not player_is_white else 0

        board = game.board()
        opening_name, eco_code = "Unknown Opening", "???"
        is_broken, breakpoint_move = False, None
        
        moves = list(game.mainline_moves())
        for i, move in enumerate(moves):
            board.push(move)
            short_fen = " ".join(board.fen().split(' ')[:4])
            
            if short_fen in eco_db:
                opening_name = eco_db[short_short_fen := short_fen].get("name", "Unknown")
                eco_code = eco_db[short_short_fen].get("eco", "???")
            else:
                is_broken, breakpoint_move = True, i + 1
                break
        
        game_results.append({
            "Khai cuộc": opening_name,
            "ECO": eco_code,
            "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
            "Nước bị vỡ": breakpoint_move if is_broken else len(moves),
            "Điểm": win_val,
            "Link": headers.get("Site", "#")
        })
        
    return pd.DataFrame(game_results)

# --- UI ---

def main():
    st.sidebar.title("♟️ Chess Coach Pro")
    
    with st.sidebar:
        user = st.text_input("Username Lichess", placeholder="Ví dụ: DrNykterstein")
        mode = st.radio("Chế độ lấy ván", ["Gần nhất", "Ngẫu nhiên"])
        count = st.number_input("Số lượng ván", 5, 100, 20)
        color = st.selectbox("Cầm quân", ["Both", "White", "Black"])
        filter_bot = st.toggle("Lọc bỏ ván đánh với Bot", value=True)
        btn = st.button("🚀 PHÂN TÍCH", use_container_width=True)
    
    eco_db = load_eco_database("eco.json")

    if btn and user:
        with st.spinner("Đang 'cào' dữ liệu sạch..."):
            pgn = fetch_lichess_games(user, count, mode, color)
            if pgn:
                df = analyze_game(pgn, eco_db, user, filter_bot)
                
                if not df.empty:
                    # Metrics
                    c1, c2, c3 = st.columns(3)
                    win_rate = df["Điểm"].mean() * 100
                    broken_df = df[df["Trạng thái"] == "💔 Vỡ bài"]
                    
                    with c1:
                        st.metric("Tỉ lệ thắng", f"{win_rate:.1f}%")
                    with c2:
                        st.metric("Tỉ lệ vỡ bài", f"{(len(broken_df)/len(df))*100:.1f}%")
                    with c3:
                        st.metric("Vị trí vỡ TB", f"{broken_df['Nước bị vỡ'].mean():.1f}" if not broken_df.empty else "0")

                    # Chart
                    st.subheader("📊 Thống kê chi tiết")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        fig_gauge = go.Figure(go.Indicator(
                            mode="gauge+number", value=(len(broken_df)/len(df))*100,
                            title={'text': "% Vỡ bài"}, gauge={'bar': {'color': "#ff4b4b"}}
                        ))
                        st.plotly_chart(fig_gauge, use_container_width=True)
                    with col_b:
                        stats = df.groupby("Khai cuộc")["Điểm"].count().sort_values(ascending=False).head(10)
                        st.bar_chart(stats)

                    # Data Table (Copy thoải mái)
                    st.subheader("📑 Danh sách ván đấu")
                    st.data_editor(df, column_config={"Link": st.column_config.LinkColumn()}, 
                                   use_container_width=True, hide_index=True, disabled=True)
                else:
                    st.warning("Sau khi lọc Bot/Variant, không còn ván nào để phân tích!")

if __name__ == "__main__":
    main()
