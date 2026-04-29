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

st.set_page_config(page_title="Chess Coach Analyzer V3", page_icon="🎯", layout="wide")

# --- CORE FUNCTIONS ---

@st.cache_data
def load_eco_database(file_path):
    """Load JSON và chuẩn hóa FEN Key (4 thành phần đầu)"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            # Chuẩn hóa để so sánh FEN linh hoạt
            return { " ".join(k.split(' ')[:4]): v for k, v in raw_data.items() }
    except Exception as e:
        st.error(f"Lỗi load file ECO: {e}")
        return {}

def fetch_lichess_games(username, num_to_analyze, mode, color, rated_only):
    """Kéo dữ liệu từ Lichess với bộ lọc từ API"""
    # Nếu chọn Random, kéo dư ra để xáo trộn
    fetch_count = num_to_analyze if mode == "Gần nhất" else num_to_analyze * 3
    
    params = {
        "max": fetch_count,
        "opening": "true",
        "finished": "true",
        "variant": "standard",
    }
    if rated_only:
        params["rated"] = "true"
    if color != "Both":
        params["color"] = color.lower()
    
    headers = {"Accept": "application/x-chess-pgn"}
    try:
        response = requests.get(f"{LICHESS_API_URL}{username}", params=params, headers=headers)
        if response.status_code != 200: return None
        
        pgn_data = response.text.strip()
        if not pgn_data: return None
        
        games = pgn_data.split('\n\n\n')
        if mode == "Ngẫu nhiên" and len(games) > num_to_analyze:
            return '\n\n\n'.join(random.sample(games, num_to_analyze))
        return pgn_data
    except:
        return None

def analyze_game(pgn_text, eco_db, username, threshold):
    """Logic phân tích kèm ngưỡng Threshold nước đi"""
    pgn = io.StringIO(pgn_text)
    game_results = []
    
    while True:
        game = chess.pgn.read_game(pgn)
        if game is None: break
            
        headers = game.headers
        player_is_white = headers.get("White", "").lower() == username.lower()
        
        board = game.board()
        last_known_info = {"name": "Khai cuộc lạ / Chưa định nghĩa", "eco": "???"}
        is_broken = False
        breakpoint_move = None
        
        moves = list(game.mainline_moves())
        for i, move in enumerate(moves):
            move_number = i + 1
            board.push(move)
            short_fen = " ".join(board.fen().split(' ')[:4])
            
            if short_fen in eco_db:
                last_known_info = eco_db[short_fen]
            else:
                # Nếu đi sai lý thuyết TRƯỚC HOẶC BẰNG nước threshold -> Vỡ bài
                if move_number <= threshold:
                    is_broken = True
                    breakpoint_move = move_number
                # Nếu sai SAU nước threshold -> Coi như đã thuộc bài xong giáo án
                break
        
        # Tính kết quả ván đấu
        res = headers.get("Result", "*")
        win_val = 0.5
        if res == "1-0": win_val = 1 if player_is_white else 0
        elif res == "0-1": win_val = 1 if not player_is_white else 0

        game_results.append({
            "Khai cuộc": last_known_info.get("name"),
            "ECO": last_known_info.get("eco"),
            "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
            "Nước sai": breakpoint_move if is_broken else "-",
            "Thứ tự vỡ": breakpoint_move if is_broken else 999, # Để sort
            "Điểm": win_val,
            "Link": headers.get("Site", "#")
        })
        
    return pd.DataFrame(game_results)

# --- UI ---

def main():
    st.sidebar.title("🔍 Chess Coach V3")
    
    with st.sidebar:
        user = st.text_input("Username Lichess", placeholder="Ví dụ: DrNykterstein")
        mode = st.radio("Chế độ chọn ván", ["Gần nhất", "Ngẫu nhiên"])
        count = st.number_input("Số lượng ván", 5, 100, 20)
        
        st.divider()
        st.write("🎯 **Cấu hình giáo án**")
        threshold = st.slider("Threshold (Ngưỡng thuộc bài)", 1, 20, 5, 
                              help="Nếu sai sau nước này, học sinh vẫn được tính là thuộc bài.")
        
        st.divider()
        st.write("🛡️ **Bộ lọc nâng cao**")
        rated_only = st.checkbox("Chỉ lấy ván Rated (Tính điểm)", value=True)
        color = st.selectbox("Cầm quân", ["Both", "White", "Black"])
        
        btn = st.button("🚀 PHÂN TÍCH NGAY", use_container_width=True)

    eco_db = load_eco_database("eco.json")

    if btn and user:
        with st.spinner("Đang trích xuất dữ liệu chuẩn..."):
            pgn = fetch_lichess_games(user, count, mode, color, rated_only)
            if pgn:
                df = analyze_game(pgn, eco_db, user, threshold)
                
                if not df.empty:
                    # 1. Dashboard Metrics
                    broken_df = df[df["Trạng thái"] == "💔 Vỡ bài"]
                    win_rate = df["Điểm"].mean() * 100
                    broken_pct = (len(broken_df)/len(df))*100
                    
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Tỉ lệ Thắng", f"{win_rate:.1f}%")
                    c2.metric("Tỉ lệ Vỡ bài", f"{broken_pct:.1f}%")
                    c3.metric("Nước vỡ TB", f"{broken_df['Thứ tự vỡ'].mean():.1f}" if not broken_df.empty else "N/A")

                    # 2. Gauge Chart
                    fig = go.Figure(go.Indicator(
                        mode="gauge+number", value=broken_pct,
                        title={'text': "% Vỡ bài (Dưới nước " + str(threshold) + ")"},
                        gauge={'bar': {'color': "#EF553B"}, 'axis': {'range': [0, 100]}}
                    ))
                    st.plotly_chart(fig, use_container_width=True)

                    # 3. Data Table (Copy/Paste thoải mái)
                    st.subheader("📑 Chi tiết thực chiến")
                    st.data_editor(
                        df.drop(columns=['Thứ tự vỡ']), 
                        column_config={"Link": st.column_config.LinkColumn()},
                        use_container_width=True, hide_index=True, disabled=True
                    )
                else:
                    st.error("Không tìm thấy ván đấu nào khớp với bộ lọc!")
            else:
                st.error("Lỗi API hoặc Username không tồn tại.")

if __name__ == "__main__":
    main()
