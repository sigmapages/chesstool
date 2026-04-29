import streamlit as st
import pandas as pd
import chess.pgn
import io
import json
import requests
import plotly.graph_objects as go
import plotly.express as px

# --- CONFIG & CONSTANTS ---
LICHESS_API_URL = "https://lichess.org/api/games/user/"

st.set_page_config(page_title="Chess Opening Analyzer", layout="wide")

# --- CORE FUNCTIONS ---

@st.cache_data
def load_eco_database(file_path):
    """Load file JSON chứa lý thuyết khai cuộc"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Lỗi load file ECO: {e}")
        return {}

@st.cache_data
def fetch_lichess_games(username, max_games, color):
    """Lấy dữ liệu ván đấu từ Lichess API"""
    params = {
        "max": max_games,
        "perfType": "ultraBullet,bullet,blitz,rapid,classical",
        "opening": "true"
    }
    if color != "Both":
        params["color"] = color.lower()
        
    headers = {"Accept": "application/x-chess-pgn"}
    response = requests.get(f"{LICHESS_API_URL}{username}", params=params, headers=headers)
    
    if response.status_code == 404:
        st.error("Không tìm thấy người chơi này!")
        return None
    elif response.status_code == 429:
        st.error("Bị Lichess limit rồi, đợi xíu nha bro!")
        return None
    
    return response.text

def analyze_game(pgn_text, eco_db, username):
    """Logic xử lý chính để tìm điểm vỡ bài (Breakpoint)"""
    pgn = io.StringIO(pgn_text)
    game_results = []
    
    while True:
        game = chess.pgn.read_game(pgn)
        if game is None:
            break
            
        headers = game.headers
        player_color = "White" if headers.get("White").lower() == username.lower() else "Black"
        result = headers.get("Result")
        
        # Mapping kết quả thắng/thua cho người chơi
        win_status = 0 # 1: Thắng, 0.5: Hòa, 0: Thua
        if result == "1/2-1/2": win_status = 0.5
        elif (result == "1-0" and player_color == "White") or (result == "0-1" and player_color == "Black"):
            win_status = 1

        board = game.board()
        san_moves = []
        breakpoint_move = None
        opening_name = "Unknown"
        eco_code = "???"
        is_broken = False
        
        moves = list(game.mainline_moves())
        
        for i, move in enumerate(moves):
            san_moves.append(board.san(move))
            board.push(move)
            
            current_path = " ".join(san_moves)
            
            if current_path in eco_db:
                opening_name = eco_db[current_path]["name"]
                eco_code = eco_db[current_path]["eco"]
            else:
                # Nếu nước này không có trong ECO nhưng nước trước đó có -> Breakpoint
                is_broken = True
                breakpoint_move = i + 1
                break
        
        game_results.append({
            "Opening": opening_name,
            "ECO": eco_code,
            "Status": "Broken" if is_broken else "In Theory",
            "Breakpoint": breakpoint_move if is_broken else len(moves),
            "Win": win_status,
            "Link": headers.get("Site", "")
        })
        
    return pd.DataFrame(game_results)

# --- UI RENDERING ---

def render_dashboard(df):
    if df.empty:
        st.warning("Không có dữ liệu để hiển thị.")
        return

    # 1. Metric Columns
    total_games = len(df)
    broken_games = len(df[df["Status"] == "Broken"])
    avg_breakpoint = df[df["Status"] == "Broken"]["Breakpoint"].mean()
    win_rate = df["Win"].mean() * 100

    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Gauge Chart cho % Vỡ bài
        broken_pct = (broken_games / total_games) * 100
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = broken_pct,
            title = {'text': "% Vỡ Lý Thuyết"},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#EF553B"}}
        ))
        fig_gauge.update_layout(height=250, margin=dict(t=50, b=0, l=10, r=10))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col2:
        st.metric("Vị trí vỡ trung bình", f"Nước thứ {avg_breakpoint:.1f}")
        st.info("Học sinh thường đi sai lý thuyết ở giai đoạn này.")

    with col3:
        st.metric("Tỉ lệ thắng tổng quát", f"{win_rate:.1f}%")

    # 2. Histogram
    st.subheader("📊 Phân bổ nước đi bị vỡ")
    fig_hist = px.histogram(df[df["Status"] == "Broken"], x="Breakpoint", 
                           nbins=20, labels={'Breakpoint': 'Nước thứ mấy'},
                           color_discrete_sequence=['#636EFA'])
    st.plotly_chart(fig_hist, use_container_width=True)

    # 3. Thống kê chi tiết từng khai cuộc
    st.subheader("📑 Chi tiết theo Khai cuộc")
    stats = df.groupby("Opening").agg(
        So_Van=("Opening", "count"),
        Ti_Le_Thuoc=("Status", lambda x: (x == "In Theory").sum() / len(x) * 100),
        Ti_Le_Thang=("Win", "mean")
    ).reset_index()
    
    stats["Ti_Le_Thang"] = stats["Ti_Le_Thang"] * 100
    st.dataframe(stats.sort_values(by="So_Van", ascending=False), use_container_width=True)

    # 4. Danh sách ván đấu
    with st.expander("🔍 Xem chi tiết danh sách ván đấu"):
        st.table(df[["Opening", "ECO", "Status", "Breakpoint", "Link"]])

# --- MAIN APP ---

def main():
    st.sidebar.title("⚙️ Cấu hình")
    username = st.sidebar.text_input("Username Lichess", placeholder="Ví dụ: DrNykterstein")
    num_games = st.sidebar.slider("Số lượng ván", 10, 100, 50)
    color = st.sidebar.selectbox("Phân tích ván cầm quân", ["Both", "White", "Black"])
    
    eco_db = load_eco_database("eco.json")

    if st.sidebar.button("Phân tích ngay"):
        if not username:
            st.error("Nhập username cái đã bro ơi!")
            return
            
        with st.spinner("Đang kéo data từ Lichess..."):
            pgn_data = fetch_lichess_games(username, num_games, color)
            
            if pgn_data:
                df_results = analyze_game(pgn_data, eco_db, username)
                render_dashboard(df_results)

if __name__ == "__main__":
    main()
