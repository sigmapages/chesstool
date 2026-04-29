import streamlit as st
import pandas as pd
import chess.pgn
import io
import json
import requests
import plotly.graph_objects as go
import plotly.express as px

# --- CONFIG ---
LICHESS_API_URL = "https://lichess.org/api/games/user/"

st.set_page_config(
    page_title="Chess Opening Pro Analyzer",
    page_icon="♟️",
    layout="wide"
)

# --- STYLE ---
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- CORE FUNCTIONS ---

@st.cache_data
def load_eco_database(file_path):
    """Load JSON và chuẩn hóa FEN Key (chỉ lấy 4 thành phần đầu)"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            clean_db = {}
            for fen_key, info in raw_data.items():
                # Rút gọn FEN để tăng tỉ lệ khớp (bỏ nửa nước và số nước)
                short_key = " ".join(fen_key.split(' ')[:4])
                clean_db[short_key] = info
            return clean_db
    except Exception as e:
        st.error(f"Lỗi load file ECO: {e}")
        return {}

@st.cache_data
def fetch_lichess_games(username, max_games, color):
    """Kéo PGN từ Lichess API"""
    params = {
        "max": max_games,
        "opening": "true",
        "finished": "true"
    }
    if color != "Both":
        params["color"] = color.lower()
    
    headers = {"Accept": "application/x-chess-pgn"}
    
    try:
        response = requests.get(f"{LICHESS_API_URL}{username}", params=params, headers=headers)
        if response.status_code == 200:
            return response.text
        elif response.status_code == 404:
            st.error("Không tìm thấy user này trên Lichess!")
        elif response.status_code == 429:
            st.error("Lichess đang chặn (Rate Limit). Đợi vài phút nha bro.")
        return None
    except Exception as e:
        st.error(f"Lỗi kết nối API: {e}")
        return None

def analyze_game(pgn_text, eco_db, username):
    """Xử lý từng ván đấu và tìm điểm vỡ bài"""
    pgn = io.StringIO(pgn_text)
    game_results = []
    
    while True:
        game = chess.pgn.read_game(pgn)
        if game is None: break
            
        # 1. BỘ LỌC: Bỏ qua ván biến thể (Chess960, ván tự set thế cờ...)
        variant = game.headers.get("Variant", "Standard")
        if variant != "Standard":
            continue

        headers = game.headers
        player_is_white = headers.get("White", "").lower() == username.lower()
        player_color = "White" if player_is_white else "Black"
        result = headers.get("Result", "*")
        
        # Logic tính thắng/thua/hòa
        win_val = 0.5
        if result == "1-0": win_val = 1 if player_is_white else 0
        elif result == "0-1": win_val = 1 if not player_is_white else 0

        board = game.board()
        opening_name = "Unknown Opening"
        eco_code = "???"
        is_broken = False
        breakpoint_move = None
        
        moves = list(game.mainline_moves())
        
        for i, move in enumerate(moves):
            board.push(move)
            # Rút gọn FEN bàn cờ hiện tại
            current_short_fen = " ".join(board.fen().split(' ')[:4])
            
            if current_short_fen in eco_db:
                opening_name = eco_db[current_short_fen].get("name", "Unknown")
                eco_code = eco_db[current_short_fen].get("eco", "???")
            else:
                # Nếu không khớp FEN -> Vỡ bài từ nước này
                is_broken = True
                breakpoint_move = i + 1 
                break
        
        game_results.append({
            "Opening": opening_name,
            "ECO": eco_code,
            "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
            "Nước bị vỡ": breakpoint_move if is_broken else len(moves),
            "Kết quả": win_val,
            "Link ván đấu": headers.get("Site", "#")
        })
        
    return pd.DataFrame(game_results)

# --- UI RENDERING ---

def render_dashboard(df):
    if df is None or df.empty:
        st.warning("Không có dữ liệu hợp lệ để phân tích.")
        return

    # Row 1: Metrics
    total = len(df)
    broken_df = df[df["Trạng thái"] == "💔 Vỡ bài"]
    broken_pct = (len(broken_df) / total) * 100
    avg_break = broken_df["Nước bị vỡ"].mean() if not broken_df.empty else 0
    win_rate = df["Kết quả"].mean() * 100

    c1, c2, c3 = st.columns(3)
    with c1:
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = broken_pct,
            number = {'suffix': "%"},
            title = {'text': "Tỉ lệ Vỡ bài"},
            gauge = {'axis': {'range': [0, 100]}, 'bar': {'color': "#EF553B"}}
        ))
        fig.update_layout(height=280, margin=dict(t=50, b=0, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
    
    with c2:
        st.write("") # Padding
        st.metric("Vị trí vỡ TB", f"Nước thứ {avg_break:.1f}")
        st.caption("Điểm mà học sinh thường bắt đầu đi sai lý thuyết.")
        
    with c3:
        st.write("") # Padding
        st.metric("Tỉ lệ thắng", f"{win_rate:.1f}%")
        st.caption(f"Dựa trên {total} ván Standard gần nhất.")

    st.divider()

    # Row 2: Charts
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.subheader("📊 Phân bổ nước đi bị vỡ")
        if not broken_df.empty:
            fig_hist = px.histogram(broken_df, x="Nước bị vỡ", nbins=15, color_discrete_sequence=['#636EFA'])
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.success("Học sinh này 'thuộc bài' 100% trong số ván đã chọn!")

    with col_right:
        st.subheader("🏆 Top Khai cuộc hay đánh")
        top_openings = df["Opening"].value_counts().head(5)
        fig_pie = px.pie(values=top_openings.values, names=top_openings.index, hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

    # Row 3: Data Editor (Cho phép Copy)
    st.subheader("📑 Chi tiết từng ván đấu")
    st.info("💡 Mẹo: Bro có thể click vào ô Link để mở hoặc chọn nhiều ô rồi nhấn Ctrl+C để copy dữ liệu.")
    
    st.data_editor(
        df,
        column_config={
            "Link ván đấu": st.column_config.LinkColumn("Link ván đấu"),
            "Kết quả": st.column_config.NumberColumn("Điểm (1=Thắng)", format="%.1f")
        },
        hide_index=True,
        use_container_width=True,
        disabled=True
    )

# --- APP EXECUTION ---

def main():
    st.sidebar.title("♟️ HLV Cờ Vua Dashboard")
    st.sidebar.markdown("Phân tích độ thuộc bài từ Lichess")
    
    with st.sidebar:
        username = st.text_input("Username Lichess", placeholder="Ví dụ: DrNykterstein")
        num_games = st.slider("Số lượng ván phân tích", 10, 100, 50)
        color = st.selectbox("Cầm quân", ["Both", "White", "Black"])
        st.divider()
        if st.button("🚀 BẮT ĐẦU PHÂN TÍCH", use_container_width=True):
            if not username:
                st.error("Nhập username cái đã bro!")
            else:
                # Trigger flow
                st.session_state.start_analysis = True
        
    eco_db = load_eco_database("eco.json")

    if st.session_state.get('start_analysis'):
        with st.spinner(f"Đang tải {num_games} ván đấu của {username}..."):
            pgn_data = fetch_lichess_games(username, num_games, color)
            if pgn_data:
                df = analyze_game(pgn_data, eco_db, username)
                render_dashboard(df)
            else:
                st.info("Không tìm thấy dữ liệu. Hãy check lại username.")

if __name__ == "__main__":
    main()
