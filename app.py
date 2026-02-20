import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# ==========================================
# 1. 資料庫連線與建立資料表 (Database Setup)
# ==========================================
conn = sqlite3.connect('business.db')
c = conn.cursor()

# 建立「交易紀錄表」
c.execute('''CREATE TABLE IF NOT EXISTS transactions
             (date TEXT, type TEXT, item TEXT, qty INTEGER, price REAL, total REAL)''')
# 建立「倉庫庫存表」
c.execute('''CREATE TABLE IF NOT EXISTS inventory
             (item TEXT PRIMARY KEY, qty INTEGER)''')
conn.commit()

# ==========================================
# 2. 前端網頁介面設計 (UI Design)
# ==========================================
st.set_page_config(page_title="中盤商記帳系統", layout="wide")
st.title("📦 專屬進銷存與記帳系統")

# 左側邊欄：操作面板
st.sidebar.header("📝 新增交易單")
trans_type = st.sidebar.selectbox("交易類別", ["進貨 (付出去的錢)", "銷貨 (收進來的錢)"])
item_name = st.sidebar.text_input("商品名稱 (例如：A級零件)")
qty = st.sidebar.number_input("數量", min_value=1, step=1)
price = st.sidebar.number_input("單價 (元)", min_value=0.0, step=1.0)

# ==========================================
# 3. 核心商業邏輯 (Business Logic)
# ==========================================
if st.sidebar.button("💾 確認送出"):
    if item_name == "":
        st.sidebar.error("請輸入商品名稱！")
    else:
        total_amount = qty * price
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 寫入交易紀錄
        c.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?)",
                  (date_str, trans_type, item_name, qty, price, total_amount))

        # 檢查庫存現況
        c.execute("SELECT qty FROM inventory WHERE item=?", (item_name,))
        current_stock = c.fetchone()

        # 進貨邏輯：庫存增加
        if "進貨" in trans_type:
            if current_stock:
                c.execute("UPDATE inventory SET qty = qty + ? WHERE item=?", (qty, item_name))
            else:
                c.execute("INSERT INTO inventory VALUES (?,?)", (item_name, qty))
            st.sidebar.success(f"✅ 成功進貨 {qty} 件 {item_name}！")
            conn.commit()
            
        # 銷貨邏輯：庫存減少 (需防呆機制：庫存不能扣到變負數)
        elif "銷貨" in trans_type:
            if current_stock and current_stock[0] >= qty:
                c.execute("UPDATE inventory SET qty = qty - ? WHERE item=?", (qty, item_name))
                st.sidebar.success(f"💰 成功銷貨！進帳 {total_amount} 元")
                conn.commit()
            else:
                st.sidebar.error("⚠️ 失敗：倉庫裡的庫存不夠賣喔！")

# ==========================================
# 4. 數據總覽儀表板 (Dashboard)
# ==========================================
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 目前倉庫庫存")
    df_inv = pd.read_sql_query("SELECT item as '商品名稱', qty as '現有數量' FROM inventory", conn)
    st.dataframe(df_inv, use_container_width=True, hide_index=True)

with col2:
    st.subheader("💸 歷史交易與帳務")
    df_trans = pd.read_sql_query("SELECT date as '時間', type as '類別', item as '商品', qty as '數量', price as '單價', total as '總金額' FROM transactions ORDER BY date DESC", conn)
    st.dataframe(df_trans, use_container_width=True, hide_index=True)