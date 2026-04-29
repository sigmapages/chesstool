import streamlit as st
import pandas as pd
import chess.pgn
import io
import json
import requests
import plotly.graph_objects as go
import plotly.express as px

# --- CẤU HÌNH ---
LICHESS_API_URL = "https://lichess.org/api/games/user/"

st.set_page_config(page_title="Chess Master Coach", layout="wide")

# --- HÀM XỬ LÝ DỮ LIỆU ---

@st.cache_data
def load_eco_database(file_path):
    """Load JSON và chuẩn hóa Key FEN (chỉ lấy 4 thành phần đầu)"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            # Chuẩn hóa: "rnb... 1 1" -> "rnb... b KQkq -"
            clean_db = {}
            for fen_key, info in raw_data.items():
                short_key = " ".join(fen_key.split(' ')[:4])
                clean_db[short_key] = info
            return clean_db
    except Exception as e:
        st.error(f"Lỗi load file ECO: {e}")
        return {}

@st.cache_data
def fetch_lichess_games(username, max_games, color):
    """Kéo dữ liệu từ Lichess"""
    params = {"max": max_games, "opening": "true"}
    if color != "Both":
        params["color"] = color.lower()
    headers = {"Accept": "application/x-chess-pgn"}
    
    response = requests.get(f"{LICHESS_API_URL}{username}", params=params, headers=headers)
    if response.status_code != 200:
        return None
    return response.text

def analyze_game(pgn_text, eco_db, username):
    """Logic Core: Dò FEN để tìm Breakpoint"""
    pgn = io.StringIO(pgn_text)
    game_results = []
    
    while True:
        game = chess.pgn.read_game(pgn)
        if game is None: break
            
        headers = game.headers
        player_color = "White" if headers.get("White", "").lower() == username.lower() else "Black"
        result = headers.get("Result", "*")
        
        # Tính kết quả thắng/thua
        win_val = 0.5
        if result == "1-0": win_val = 1 if player_color == "White" else 0
        elif result == "0-1": win_val = 1 if player_color == "Black" else 0

        board = game.board()
        opening_name = "Unknown Opening"
        eco_code = "???"
        is_broken = False
        breakpoint_move = None
        
        moves = list(game.mainline_moves())
        
        for i, move in enumerate(moves):
            board.push(move)
            # Lấy FEN rút gọn (4 phần) để tra cứu
            current_short_fen = " ".join(board.fen().split(' ')[:4])
            
            if current_short_fen in eco_db:
                opening_name = eco_db[current_short_fen].get("name", "Unknown")
                eco_code = eco_db[current_short_fen].get("eco", "???")
            else:
                is_broken = True
                breakpoint_move = i + 1 # Nước thứ i+1 bị vỡ bài
                break
        
        game_results.append({
            "Opening": opening_name,
            "ECO": eco_code,
            "Status": "Vỡ bài" if is_broken else "Thuộc bài",
            "Breakpoint": breakpoint_move if is_broken else len(moves),
            "Win": win_val,
            "Link": headers.get("Site", "#")
        })
        
    return pd.DataFrame(game_results)

# --- GIAO DIỆN (UI) ---

def render_ui(df):
    if df is None or df.empty:
        st.info("Chưa có dữ liệu. Hãy nhập username và nhấn Phân tích.")
        return

    # Chỉ số hàng đầu
    total = len(df)
    broken_df = df[df["Status"] == "Vỡ bài"]
    broken_count = len(broken_df)
    avg_break = broken_df["Breakpoint"].mean() if not broken_df.empty else 0
    win_rate = df["Win"].mean() * 100

    c1, c2, c3 = st.columns(3)
    with c1:
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = (broken_count/total)*100,
            title = {'text': "% Vỡ Lý Thuyết"},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "red"}}
        ))
        fig.update_layout(height=250, margin=dict(t=30, b=0))
        st.plotly_chart(fig, use_container_width=True)
    
    c2.metric("Vị trí vỡ TB", f"Nước thứ {avg_break:.1f}")
    c3.metric("Tỉ lệ thắng", f"{win_rate:.1f}%")

    st.divider()

    # Biểu đồ Histogram
    st.subheader("📊 Phân bổ thời điểm vỡ bài")
    if not broken_df.empty:
        fig_hist = px.histogram(broken_df, x="Breakpoint", labels={'Breakpoint': 'Nước đi thứ'}, color_discrete_sequence=['#ff4b4b'])
        st.plotly_chart(fig_hist, use_container_width=True)
    else:
        st.write("Học sinh này thuộc bài quá, không có ván nào vỡ!")

    # Bảng thống kê
    st.subheader("📑 Chi tiết các loại khai cuộc")
    stats = df.groupby("Opening").agg(
        Ván=("Opening", "count"),
        Thuộc_Bài=("Status", lambda x: (x == "Thuộc bài").sum() / len(x) * 100),
        Thắng_Lợi=("Win", "mean")
    ).reset_index()
    stats["Thắng_Lợi"] = stats["Thắng_Lợi"] * 100
    st.dataframe(stats.sort_values(by="Ván", ascending=False), use_container_width=True)

    # Danh sách ván
    with st.expander("🔗 Xem link các ván đấu cụ thể"):
        st.dataframe(df[["Opening", "Status", "Breakpoint", "Link"]], use_container_width=True)

# --- MAIN ---

def main():
    st.sidebar.header("🛠 Cấu hình phân tích")
    username = st.sidebar.text_input("Lichess Username")
    num_games = st.sidebar.number_input("Số lượng ván", 10, 200, 50)
    color = st.sidebar.selectbox("Cầm quân", ["Both", "White", "Black"])
    
    # Load DB
    eco_db = load_eco_database("eco.json")

    if st.sidebar.button("Phân tích ngay"):
        if not username:
            st.warning("Nhập tên kì thủ bro ơi!")
        else:
            with st.spinner("Đang soi ván đấu..."):
                pgn_data = fetch_lichess_games(username, num_games, color)
                if pgn_data:
                    df = analyze_game(pgn_data, eco_db, username)
                    render_ui(df)
                else:
                    st.error("Không lấy được dữ liệu từ Lichess. Check lại username nhé.")

if __name__ == "__main__":
    main()
