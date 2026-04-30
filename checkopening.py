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
placeholder = st.empty()
with placeholder:
    components.html(ga_du_kich, height=0)

# --- PHẦN 4: HÀM TÍNH TOÁN CSV CẢI TIẾN (KHÔNG GÂY LỖI) ---
def convert_df_to_csv_with_summary(df, target_user):
    if df.empty:
        return None
    
    # Tính toán các chỉ số
    total_games = len(df)
    win_points = df["Kết quả"].sum()
    win_rate = (win_points / total_games) * 100 if total_games > 0 else 0
    avg_theory = df["Số nước thuộc"].mean()
    broken_count = len(df[df["Trạng thái"] == "💔 Vỡ bài"])
    
    # Tạo dữ liệu Summary
    summary_data = [
        {}, # Dòng trống
        {"Khai cuộc": "--- BÁO CÁO TỔNG KẾT ---"},
        {"Khai cuộc": f"Người chơi: {target_user}"},
        {"Khai cuộc": f"Tổng số ván: {total_games}"},
        {"Khai cuộc": f"Tỉ lệ thắng: {win_rate:.1f}%"},
        {"Khai cuộc": f"Trung bình số nước thuộc: {avg_theory:.1f}"},
        {"Khai cuộc": f"Số ván vỡ bài sớm: {broken_count}"},
        {"Khai cuộc": f"Ngày xuất: {datetime.now().strftime('%d/%m/%Y')}"},
        {"Khai cuộc": "Nguồn: ChessTool CheckOpening"}
    ]
    df_summary = pd.DataFrame(summary_data)
    
    # Kết hợp
    df_final = pd.concat([df, df_summary], ignore_index=True)
    return df_final.to_csv(index=False).encode('utf-8-sig')

# --- PHẦN 5: CÁC HÀM PHỤ TRỢ (DATABASE, FETCH, ANALYZE) ---
@st.cache_data
def load_db(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            processed_db = { " ".join(k.split(' ')[:4]): v for k, v in raw.items() }
            return processed_db
    except: return {}

def fetch_chess_com_games(username, limit_count):
    all_pgn = ""
    found = 0
    now = datetime.now()
    y, m = now.year, now.month
    for _ in range(3):
        try:
            r = get_player_games_by_month_pgn(username, y, m)
            data = r.json['pgn']['data']
            if data:
                all_pgn += data + "\n\n\n"
                found += len(data.strip().split('\n\n\n'))
            if found >= limit_count: break
            m -= 1
            if m == 0: m = 12; y -= 1
        except: break
    return all_pgn

def analyze_games(pgn_content, opening_db, target_user, threshold):
    if not pgn_content: return pd.DataFrame()
    pgn_io = io.StringIO(pgn_content)
    results = []
    count = 0
    while count < 150:
        game = chess.pgn.read_game(pgn_io)
        if not game: break
        h = game.headers
        w, b = h.get("White", "").lower(), h.get("Black", "").lower()
        if any(k in w or k in b for k in ["bot", "ai", "stockfish", "engine"]): continue
        
        user_is_white = (w == target_user.lower())
        board = game.board()
        opening_name = "Khai cuộc lạ"
        is_broken, wrong_move, theory_len = False, None, 0
        
        for i, move in enumerate(game.mainline_moves()):
            board.push(move)
            fen = " ".join(board.fen().split(' ')[:4])
            if fen in opening_db:
                opening_name = opening_db[fen].get("name")
                theory_len = i + 1
            else:
                if (i + 1) <= threshold:
                    is_broken, wrong_move = True, i + 1
                break
        
        res = h.get("Result", "*")
        pts = 0.5
        if res == "1-0": pts = 1 if user_is_white else 0
        elif res == "0-1": pts = 0 if user_is_white else 1
            
        results.append({
            "Khai cuộc": opening_name,
            "Trạng thái": "💔 Vỡ bài" if is_broken else "✅ Thuộc bài",
            "Nước sai": wrong_move if is_broken else "-",
            "Số nước thuộc": theory_len,
            "Kết quả": pts,
            "Link ván đấu": h.get("Link", h.get("Site", ""))
        })
        count += 1
    return pd.DataFrame(results)

# --- PHẦN 6: GIAO DIỆN CHÍNH ---
def main():
    st.sidebar.markdown("# ♟️ Check Opening V1.4")
    with st.sidebar:
        platform = st.selectbox("Chọn nền tảng:", ["Lichess", "Chess.com"])
        target_username = st.text_input(f"Nhập Username {platform}:")
        analysis_mode = st.radio("Chế độ lấy ván:", ["Gần nhất", "Ngẫu nhiên"])
        game_limit = st.slider("Số lượng ván:", 5, 100, 20)
        threshold = st.slider("Ngưỡng thuộc bài (Threshold):", 1, 25, 8)
        only_rated = st.toggle("Chỉ tính ván Rated", value=True)
        run_button = st.button("🚀 BẮT ĐẦU PHÂN TÍCH", use_container_width=True)

    db_data = load_db("eco.json")
    
    if run_button and target_username:
        with st.spinner(f"Đang phân tích ván đấu của {target_username}..."):
            # Fetch PGN
            if platform == "Lichess":
                params = {"max": game_limit if analysis_mode == "Gần nhất" else game_limit*2, "opening": "true"}
                if only_rated: params["rated"] = "true"
                r = requests.get(f"https://lichess.org/api/games/user/{target_username}", params=params, headers=MY_HEADERS)
                final_pgn = r.text if r.status_code == 200 else ""
            else:
                final_pgn = fetch_chess_com_games(target_username, game_limit)

            # Randomize if needed
            if analysis_mode == "Ngẫu nhiên" and final_pgn:
                g_list = [g for g in final_pgn.strip().split('\n\n\n') if g]
                final_pgn = "\n\n\n".join(random.sample(g_list, min(len(g_list), game_limit)))

            df_result = analyze_games(final_pgn, db_data, target_username, threshold)

            if not df_result.empty:
                st.title(f"📊 Kết quả cho {target_username}")
                
                # 1. METRICS
                m1, m2, m3, m4 = st.columns(4)
                win_rate = df_result["Kết quả"].mean() * 100
                broken_rate = (len(df_result[df_result["Trạng thái"] == "💔 Vỡ bài"]) / len(df_result)) * 100
                m1.metric("Tỉ lệ Thắng", f"{win_rate:.1f}%")
                m2.metric("Tỉ lệ Vỡ bài", f"{broken_rate:.1f}%")
                m3.metric("Thuộc sâu nhất", f"{df_result['Số nước thuộc'].max()} nước")
                m4.metric("Avg thuộc", f"{df_result['Số nước thuộc'].mean():.1f}")

                # 2. TABS (BIỂU ĐỒ)
                t1, t2, t3 = st.tabs(["🎯 Gauge", "📈 Tần suất", "🔥 Heatmap"])
                with t1:
                    fig = go.Figure(go.Indicator(mode="gauge+number", value=broken_rate, title={'text': "Tỉ lệ Vỡ bài (%)"}))
                    st.plotly_chart(fig, use_container_width=True)
                with t2:
                    st.bar_chart(df_result["Khai cuộc"].value_counts().head(10))
                with t3:
                    broken_df = df_result[df_result["Trạng thái"] == "💔 Vỡ bài"]
                    if not broken_df.empty:
                        fig_h = px.density_heatmap(broken_df, x="Nước sai", y="Khai cuộc", text_auto=True)
                        st.plotly_chart(fig_h, use_container_width=True)

                # 3. TABLES
                st.subheader("🏆 Hiệu quả Khai cuộc")
                summary = df_result.groupby("Khai cuộc").agg(Số_ván=("Kết quả", "count"), Thắng=("Kết quả", lambda x: (x==1).sum())).reset_index()
                st.dataframe(summary.sort_values(by="Số_ván", ascending=False), use_container_width=True, hide_index=True)

                st.subheader("📑 Chi tiết ván đấu")
                st.data_editor(df_result, column_config={"Link ván đấu": st.column_config.LinkColumn("Xem")}, use_container_width=True, hide_index=True)

                # 4. DOWNLOAD (TÍNH NĂNG THÊM VÀO ĐÂY)
                csv_data = convert_df_to_csv_with_summary(df_result, target_username)
                st.download_button(
                    label="📥 Tải báo cáo CSV (Full Summary)",
                    data=csv_data,
                    file_name=f"ChessReport_{target_username}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.warning("Không tìm thấy dữ liệu!")

if __name__ == "__main__":
    main()
