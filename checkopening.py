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
# Đây là chìa khóa để fix lỗi "Lỗi kết nối API" trong ảnh của bro
MY_HEADERS = {"User-Agent": "ChessTool-CheckOpening/1.1 (thilan89757@gmail.com)"}
Client.request_config['headers']['User-Agent'] = MY_HEADERS["User-Agent"]

# --- PHẦN 2: CẤU HÌNH TRANG ---
st.set_page_config(
    page_title="ChessTool CheckOpening",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PHẦN 3: CÁCH "DU KÍCH" - CHỈ 1 DÒNG DUY NHẤT ---
import streamlit.components.v1 as components

GA_ID = "G-GK0V9TT1PV"

# Chèn thẳng script tag vào body, không bọc <html> hay <head> gì hết
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

# Dùng st.empty để đảm bảo nó được render ra ngay
placeholder = st.empty()
with placeholder:
    components.html(ga_du_kich, height=0)

# --- PHẦN 4: HÀM LOAD CƠ SỞ DỮ LIỆU (DATABASE) ---
@st.cache_data
def load_db(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            # Giữ nguyên logic xử lý key của bro
            processed_db = {}
            for k, v in raw.items():
                parts = k.split(' ')
                short_fen = " ".join(parts[:4])
                processed_db[short_fen] = v
            return processed_db
    except Exception as e:
        st.error(f"Không tìm thấy file dữ liệu khai cuộc (eco.json): {e}")
        return {}

# --- PHẦN 5: HÀM LẤY DỮ LIỆU TỪ CHESS.COM ---
def fetch_chess_com_games(username, limit_count):
    all_pgn_data = ""
    games_found = 0
    current_date = datetime.now()
    curr_year = current_date.year
    curr_month = current_date.month

    # Quét lùi 3 tháng để gom đủ số ván bro cần
    for _ in range(3):
        try:
            response = get_player_games_by_month_pgn(username, curr_year, curr_month)
            month_pgn = response.json['pgn']['data']
            if month_pgn:
                all_pgn_data += month_pgn + "\n\n\n"
                # Đếm sơ bộ số ván
                temp_games = month_pgn.strip().split('\n\n\n')
                games_found += len(temp_games)
            
            if games_found >= limit_count:
                break
                
            curr_month -= 1
            if curr_month == 0:
                curr_month = 12
                curr_year -= 1
        except Exception:
            break
    return all_pgn_data

# --- PHẦN 6: HÀM PHÂN TÍCH LOGIC KHAI CUỘC ---
def analyze_games(pgn_content, opening_db, target_user, move_threshold):
    if not pgn_content:
        return pd.DataFrame()

    pgn_io = io.StringIO(pgn_content)
    analysis_results = []
    games_count = 0
    
    while True:
        try:
            game = chess.pgn.read_game(pgn_io)
            if game is None or games_count >= 150:
                break
            
            headers = game.headers
            white_player = headers.get("White", "Unknown").lower()
            black_player = headers.get("Black", "Unknown").lower()
            event_name = headers.get("Event", "Unknown").lower()
            
            # Lọc Bot/AI cực mạnh như bro muốn
            bot_keywords = ["bot", "ai", "stockfish", "computer", "komodo", "alpha", "engine"]
            if any(key in white_player or key in black_player or key in event_name for key in bot_keywords):
                continue

            user_is_white = (white_player == target_user.lower())
            board = game.board()
            current_opening = {"name": "Khai cuộc lạ (Không có trong DB)"}
            is_theory_broken = False
            first_wrong_move = None
            theory_length = 0
            
            game_moves = list(game.mainline_moves())
            
            for index, move in enumerate(game_moves):
                board.push(move)
                # Lấy FEN rút gọn để đối chiếu
                current_fen = " ".join(board.fen().split(' ')[:4])
                
                if current_fen in opening_db:
                    current_opening = opening_db[current_fen]
                    theory_length = index + 1
                else:
                    # Nếu nước sai nằm trong ngưỡng bro cài đặt
                    if (index + 1) <= move_threshold:
                        is_theory_broken = True
                        first_wrong_move = index + 1
                    break
            
            # Tính điểm số
            game_result = headers.get("Result", "*")
            points = 0.5
            if game_result == "1-0":
                points = 1 if user_is_white else 0
            elif game_result == "0-1":
                points = 0 if user_is_white else 1
                
            analysis_results.append({
                "Khai cuộc": current_opening.get("name"),
                "Trạng thái": "💔 Vỡ bài" if is_theory_broken else "✅ Thuộc bài",
                "Nước sai": first_wrong_move if is_theory_broken else "-",
                "Số nước thuộc": theory_length,
                "Kết quả": points,
                "Link ván đấu": headers.get("Link", headers.get("Site", "https://lichess.org"))
            })
            games_count += 1
        except Exception:
            continue
            
    return pd.DataFrame(analysis_results)

# --- PHẦN 7: GIAO DIỆN CHÍNH (MAIN UI) ---
def main():
    # Sidebar
    st.sidebar.markdown("# ♟️ Check Opening V1.3")
    
    with st.sidebar:
        st.write("---")
        platform = st.selectbox("Chọn nền tảng:", ["Lichess", "Chess.com"])
        target_username = st.text_input(f"Nhập Username {platform}:", placeholder="Ví dụ: chessnhan")
        
        analysis_mode = st.radio("Chế độ lấy ván:", ["Gần nhất", "Ngẫu nhiên"])
        
        game_limit = st.slider("Số lượng ván phân tích:", 5, 100, 20)
        threshold = st.slider("Ngưỡng thuộc bài (Threshold):", 1, 25, 8)
        
        only_rated = st.toggle("Chỉ tính ván Rated", value=True)
        
        st.write("---")
        run_button = st.button("🚀 BẮT ĐẦU PHÂN TÍCH", use_container_width=True)
        
    # Main Content Area
    db_data = load_db("eco.json")
    
    if run_button:
        if not target_username:
            st.error("Bro quên nhập Username kìa!")
            return

        with st.spinner(f"Đang 'soi' ván đấu của {target_username}... Chờ xíu nhé!"):
            final_pgn = ""
            
            if platform == "Lichess":
                # Thêm headers trực tiếp vào đây để fix lỗi kết nối
                api_url = f"https://lichess.org/api/games/user/{target_username}"
                params = {
                    "max": game_limit if analysis_mode == "Gần nhất" else game_limit * 3,
                    "opening": "true",
                    "variant": "standard"
                }
                if only_rated:
                    params["rated"] = "true"
                
                try:
                    r = requests.get(api_url, params=params, headers=MY_HEADERS, timeout=20)
                    if r.status_code == 200:
                        final_pgn = r.text
                    else:
                        st.error(f"Lỗi từ Lichess (Mã {r.status_code}). Có thể sai Username?")
                except Exception as e:
                    st.error(f"Lỗi kết nối không xác định: {e}")
            else:
                final_pgn = fetch_chess_com_games(target_username, game_limit)

            if final_pgn:
                # Xử lý chế độ ngẫu nhiên
                if analysis_mode == "Ngẫu nhiên":
                    game_list = [g for g in final_pgn.strip().split('\n\n\n') if g]
                    if game_list:
                        selected_games = random.sample(game_list, min(len(game_list), game_limit))
                        final_pgn = "\n\n\n".join(selected_games)
                
                # Chạy phân tích
                df_result = analyze_games(final_pgn, db_data, target_username, threshold)
                
                if not df_result.empty:
                    # HIỂN THỊ THỐNG KÊ
                    st.title(f"📊 Kết quả cho {target_username}")
                    
                    metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
                    
                    win_rate = df_result["Kết quả"].mean() * 100
                    broken_games = df_result[df_result["Trạng thái"] == "💔 Vỡ bài"]
                    broken_rate = (len(broken_games) / len(df_result)) * 100
                    
                    metric_col1.metric("Tỉ lệ Thắng", f"{win_rate:.1f}%")
                    metric_col2.metric("Tỉ lệ Vỡ bài", f"{broken_rate:.1f}%")
                    metric_col3.metric("Thuộc sâu nhất", f"{df_result['Số nước thuộc'].max()} nước")
                    metric_col4.metric("Avg thuộc", f"{df_result['Số nước thuộc'].mean():.1f}")
                    
                    st.divider()
                    
                    # BIỂU ĐỒ
                    tab_gauge, tab_freq, tab_heat = st.tabs(["🎯 Gauge", "📈 Tần suất", "🔥 Heatmap"])
                    
                    with tab_gauge:
                        fig_gauge = go.Figure(go.Indicator(
                            mode = "gauge+number",
                            value = broken_rate,
                            title = {'text': "Tỉ lệ Vỡ bài (%)"},
                            gauge = {
                                'axis': {'range': [None, 100]},
                                'bar': {'color': "#EF553B"},
                                'steps': [
                                    {'range': [0, 30], 'color': "#E2F0CB"},
                                    {'range': [30, 70], 'color': "#FFD97D"},
                                    {'range': [70, 100], 'color': "#FF9B85"}
                                ]
                            }
                        ))
                        st.plotly_chart(fig_gauge, use_container_width=True)
                        
                    with tab_freq:
                        opening_counts = df_result["Khai cuộc"].value_counts().head(10)
                        st.bar_chart(opening_counts)
                        
                    with tab_heat:
                        if not broken_games.empty:
                            fig_heat = px.density_heatmap(
                                broken_games, 
                                x="Nước sai", 
                                y="Khai cuộc", 
                                title="Khai cuộc nào hay vỡ ở nước mấy?",
                                text_auto=True,
                                color_continuous_scale="Reds"
                            )
                            st.plotly_chart(fig_heat, use_container_width=True)
                        else:
                            st.info("Học sinh này quá giỏi, không vỡ bài ván nào nên không có heatmap!")

                    # BẢNG TỔNG HỢP KHAI CUỘC
                    st.subheader("🏆 Hiệu quả từng loại Khai cuộc")
                    summary = df_result.groupby("Khai cuộc").agg(
                        Số_ván=("Kết quả", "count"),
                        Thắng=("Kết quả", lambda x: (x == 1).sum()),
                        Hòa=("Kết quả", lambda x: (x == 0.5).sum()),
                        Thua=("Kết quả", lambda x: (x == 0).sum())
                    ).reset_index()
                    summary = summary.sort_values(by="Số_ván", ascending=False)
                    st.dataframe(summary, use_container_width=True, hide_index=True)

                    # BẢNG CHI TIẾT
                    st.subheader("📑 Danh sách ván đấu chi tiết")
                    st.data_editor(
                        df_result,
                        column_config={
                            "Link ván đấu": st.column_config.LinkColumn("Xem ván đấu")
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # NÚT DOWNLOAD
                    csv = df_result.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="📥 Tải báo cáo CSV",
                        data=csv,
                        file_name=f"Chess_Report_{target_username}.csv",
                        mime="text/csv",
                    )
                else:
                    st.warning("Không tìm thấy dữ liệu ván đấu nào để phân tích.")
            else:
                st.error("Không thể lấy dữ liệu PGN. Vui lòng kiểm tra lại Username hoặc kết nối mạng.")

if __name__ == "__main__":
    main()
