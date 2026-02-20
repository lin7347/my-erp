import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ==========================================
# 1. 資料庫連線 (連接您的 Google 試算表)
# ==========================================
# 設定機器人的權限範圍
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
# 讀取您專屬的 key.json 鑰匙
creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
client = gspread.authorize(creds)

# 透過鑰匙打開您的試算表
sheet = client.open("進銷存系統資料庫")
worksheet_trans = sheet.worksheet("transactions")
worksheet_inv = sheet.worksheet("inventory")

# ==========================================
# 2. 前端網頁介面設計
# ==========================================
st.set_page_config(page_title="雲端進銷存系統", layout="wide")
st.title("☁️ 專屬進銷存系統 (Google 雲端同步版)")

st.sidebar.header("📝 新增交易單")
trans_type = st.sidebar.selectbox("交易類別", ["進貨 (付出去的錢)", "銷貨 (收進來的錢)"])
item_name = st.sidebar.text_input("商品名稱 (例如：A級零件)")
qty = st.sidebar.number_input("數量", min_value=1, step=1)
price = st.sidebar.number_input("單價 (元)", min_value=0.0, step=1.0)
partner_name = st.sidebar.text_input("客戶/廠商名稱")

# ==========================================
# 3. 核心商業邏輯 (寫入 Google Sheets)
# ==========================================
if st.sidebar.button("💾 確認送出"):
    if item_name == "":
        st.sidebar.error("請輸入商品名稱！")
    else:
        total_amount = qty * price
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 寫入交易紀錄到 transactions 分頁
        worksheet_trans.append_row([date_str, trans_type, item_name, qty, price, total_amount, partner_name])
        # 讀取目前庫存狀況
        inv_records = worksheet_inv.get_all_records()
        
        # 尋找該商品是否已在倉庫中
        item_exists = False
        row_index = 2 # 試算表第一行是標題，資料從第二行開始
        current_qty = 0

        for i, row in enumerate(inv_records):
            if str(row.get('item', '')) == item_name:
                item_exists = True
                current_qty = int(row.get('qty', 0))
                row_index = i + 2 
                break

        if "進貨" in trans_type:
            new_qty = current_qty + qty
            if item_exists:
                worksheet_inv.update_cell(row_index, 2, new_qty)
            else:
                worksheet_inv.append_row([item_name, new_qty])
            st.sidebar.success(f"✅ 成功進貨 {qty} 件 {item_name}！資料已同步至 Google 表單。")
            
        elif "銷貨" in trans_type:
            if item_exists and current_qty >= qty:
                new_qty = current_qty - qty
                worksheet_inv.update_cell(row_index, 2, new_qty)
                st.sidebar.success(f"💰 成功銷貨！進帳 {total_amount} 元。資料已同步至 Google 表單。")
            else:
                st.sidebar.error("⚠️ 失敗：倉庫裡的庫存不夠賣喔！")

# ==========================================
# 4. 數據總覽儀表板 (即時讀取試算表)
# ==========================================
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 目前倉庫庫存")
    inv_data = worksheet_inv.get_all_records()
    if inv_data:
        st.dataframe(pd.DataFrame(inv_data), use_container_width=True)
    else:
        st.info("目前尚無庫存資料")

with col2:
    st.subheader("💸 歷史交易與帳務")
    trans_data = worksheet_trans.get_all_records()
    if trans_data:
        df_t = pd.DataFrame(trans_data)
        st.dataframe(df_t.iloc[::-1], use_container_width=True) # 反轉順序，讓最新的在最上面
    else:

        st.info("目前尚無交易資料")
