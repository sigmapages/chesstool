import streamlit as st
import pandas as pd
import chess.pgn
import io
import json
import requests
import plotly.graph_objects as go
import plotly.express as px
import random

# --- CẤU HÌNH HỆ THỐNG ---
LICHESS_API_URL = "https://lichess.org/api/games/user/"

st.set_page_config(
    page_title="Chess Opening Pro Analyzer",
    page_icon="🎯",
    layout="wide"
)

# --- 1. HÀM LOAD & CHUẨN HÓA DỮ LIỆU ---
@st.cache_data
def load_eco_database(file_path):
    """Load JSON và chuẩn hóa FEN Key để khớp với logic hoán vị nước đi"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
            # Rút gọn FEN: chỉ lấy 4 thành phần đầu (vị trí, lượt đi, nhập thành, en passant)
            clean_db = { " ".join(k.split(' ')[:4]): v for k, v in raw_data.items() }
            return clean_db
    except Exception as e:
        st.error(f"Lỗi load file ECO: {e}")
        return {}

# --- 2. HÀM CÀO DATA TỪ LICHESS ---
def fetch_lichess_games(username, num_to_analyze, mode, color, rated_only):
    """Kéo dữ liệu từ API Lichess kèm bộ lọc và chế độ Random"""
    # Nếu chọn Ngẫu nhiên, kéo x3 số lượng ván để bốc quẻ
    fetch_count = num_to_analyze if mode == "Gần nhất" else num_to_analyze * 3
    
    params = {
        "max": fetch_count,
        "opening": "true",
        "finished": "true",
        "variant": "standard", # Luôn lấy ván tiêu chuẩn
    }
    if rated_only:
        params["rated"] = "true"
    if color != "Both":
        params["color"] = color.lower()
    
    headers = {"Accept": "application/x-chess-pgn"}
    
    try:
        response = requests.get(f"{LICHESS_API_URL}{username}", params=params, headers=headers)
        if response.status_code != 200:
            return None
            
        pgn_data = response.text.strip()
        if not pgn_data:
            return None
            
        # Xử lý Logic Random
        games = pgn_data.split('\n\n\n')
        if mode == "Ngẫu nhiên" and len(games) > num_to_analyze:
            selected_games = random.sample(games, num_to_analyze)
            return '\n\n\n'.join(selected_games)
            
        return pgn_data
    except Exception as e:
        st.error(f"Lỗi API: {e}")
        return None

# --- 3. HÀM PHÂN TÍCH CORE LOGIC ---
def analyze_games(pgn_text, eco_db, username, threshold):
    """Phân tích ván đấu, xác định điểm vỡ bài dựa trên Threshold"""
    pgn = io.StringIO(pgn_text)
    results = []
    
    while True:
        game = chess.pgn.read_game(pgn)
        if game is None:
            break
            
        headers = game.headers
        white_player = headers.get("White", "").lower()
        black_player = headers.get("Black", "").lower()
        player_is_white = white_player == username.lower()
        
        # Bỏ qua ván nếu có dấu hiệu Bot tự chế (check thêm tên user)
        if any(x in white_player or x in black_player for x in ["bot", "stockfish", "computer", "ai"]):
            continue

        board = game.board()
        opening_info = {"name": "Khai cuộc lạ", "eco": "???"}
        is_broken = False
        breakpoint_move = None
        
        moves = list(game.mainline_moves())
        for i, move in enumerate(moves):
            move_idx = i + 1
            board.push(move)
            
            # Lấy FEN rút gọn để tra cứu
            current_fen = " ".join(board.fen().split(' ')[:4])
            
            if current_fen in eco_db:
                opening_info = eco_db[current_fen]
            else:
                # Nếu đi sai lý thuyết TRƯỚC HOẶC BẰNG nước threshold -> Vỡ bài
                if move_idx <= threshold:
                    is_broken = True
                    breakpoint_move = move_idx
                # Nếu đã qua threshold thì coi như "đã hoàn thành giáo án"
                break
        
        # Tính kết quả
        res = headers.get("Result", "*")
        points = 0.5
        if res == "1-0": points = 1 if player_is_white else 0
        elif res == "0-1": points = 1 if not player_is_white else 0

        results.append({
            "Khai cuộc": opening_info.get("name"),
            "ECO": opening_info.get("eco"),
            "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
            "Nước bị vỡ": breakpoint_move if is_broken else "-",
            "Thứ tự vỡ": breakpoint_move if is_broken else 999,
            "Kết quả": points,
            "Link ván": headers.get("Site", "#")
        })
        
    return pd.DataFrame(results)

# --- 4. GIAO DIỆN CHÍNH (UI) ---
def main():
    # Sidebar config
    st.sidebar.title("♟️ HLV Cờ Vua Dashboard")
    st.sidebar.info("Phân tích độ thuộc bài của học sinh dựa trên lý thuyết ECO.")
    
    with st.sidebar:
        user = st.text_input("Username Lichess", placeholder="Ví dụ: lequangliem")
        mode = st.radio("Chế độ chọn ván", ["Gần nhất", "Ngẫu nhiên"])
        count = st.number_input("Số lượng ván", 5, 100, 20)
        
        st.divider()
        st.write("⚙️ **Cấu hình giáo án**")
        threshold = st.slider("Ngưỡng thuộc (Threshold)", 1, 20, 5, 
                              help="Nếu học sinh đi đúng x nước đầu, sau đó mới sai thì vẫn tính là Thuộc bài.")
        
        st.divider()
        st.write("🛡️ **Bộ lọc**")
        rated_only = st.toggle("Chỉ lấy ván Rated (Diệt Bot/Casual)", value=True)
        color = st.selectbox("Cầm quân", ["Both", "White", "Black"])
        
        analyze_btn = st.button("🚀 BẮT ĐẦU PHÂN TÍCH", use_container_width=True)

    # Main Page
    st.title("🎯 Báo cáo thuộc bài Khai cuộc")
    
    db = load_eco_database("eco.json")

    if analyze_btn and user:
        with st.spinner(f"Đang xử lý dữ liệu cho {user}..."):
            pgn_data = fetch_lichess_games(user, count, mode, color, rated_only)
            
            if pgn_data:
                df = analyze_games(pgn_data, db, user, threshold)
                
                if not df.empty:
                    # Metrics hàng đầu
                    broken_df = df[df["Trạng thái"] == "💔 Vỡ bài"]
                    win_rate = df["Kết quả"].mean() * 100
                    broken_pct = (len(broken_df) / len(df)) * 100
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Tỉ lệ Thắng", f"{win_rate:.1f}%")
                    m2.metric("Tỉ lệ Vỡ bài", f"{broken_pct:.1f}%")
                    m3.metric("Nước vỡ TB", f"{broken_df['Thứ tự vỡ'].mean():.1f}" if not broken_df.empty else "N/A")

                    # Dashboard biểu đồ
                    col_left, col_right = st.columns([1, 1])
                    
                    with col_left:
                        # Biểu đồ Gauge
                        fig_gauge = go.Figure(go.Indicator(
                            mode="gauge+number",
                            value=broken_pct,
                            title={'text': "% Vỡ Lý Thuyết (Dưới nước " + str(threshold) + ")"},
                            gauge={
                                'axis': {'range': [0, 100]},
                                'bar': {'color': "#EF553B"},
                                'steps': [
                                    {'range': [0, 20], 'color': "#d4edda"},
                                    {'range': [20, 50], 'color': "#fff3cd"},
                                    {'range': [50, 100], 'color': "#f8d7da"}
                                ]
                            }
                        ))
                        fig_gauge.update_layout(height=350)
                        st.plotly_chart(fig_gauge, use_container_width=True)

                    with col_right:
                        # Biểu đồ cột khai cuộc hay vỡ
                        st.subheader("Top Khai cuộc hay bị vỡ")
                        if not broken_df.empty:
                            vỡ_stats = broken_df["Khai cuộc"].value_counts().head(5)
                            st.bar_chart(vỡ_stats)
                        else:
                            st.success("Tuyệt vời! Không có ván nào vỡ bài.")

                    # BẢNG DỮ LIỆU - CHO PHÉP COPY 100%
                    st.divider()
                    st.subheader("📑 Chi tiết các ván đấu (Có thể bôi đen copy)")
                    st.info("💡 Mẹo: Bro có thể click vào Link để mở ván, hoặc bôi đen ô rồi nhấn Ctrl+C để lấy dữ liệu.")
                    
                    # Dùng data_editor để mở khóa tính năng copy và tương tác
                    st.data_editor(
                        df.drop(columns=['Thứ tự vỡ']), 
                        column_config={
                            "Link ván": st.column_config.LinkColumn("Link ván đấu"),
                            "Kết quả": st.column_config.NumberColumn("Điểm", format="%.1f")
                        },
                        use_container_width=True,
                        hide_index=True,
                        disabled=False # QUAN TRỌNG: Để False để bro bôi đen copy được
                    )
                    
                    # Nút tải báo cáo
                    st.download_button(
                        "📥 Tải báo cáo CSV",
                        df.to_csv(index=False).encode('utf-8'),
                        "bao_cao_khai_cuoc.csv",
                        "text/csv"
                    )
                else:
                    st.warning("Sau khi lọc dữ liệu, không có ván nào phù hợp để phân tích.")
            else:
                st.error("Không lấy được dữ liệu. Kiểm tra lại Username hoặc Lichess API đang bận.")

if __name__ == "__main__":
    main()
