import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json

# ==========================================
# 1. 資料庫連線 (隱形保險箱安全版)
# ==========================================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(st.secrets["google_credentials"])
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

sheet = client.open("進銷存系統資料庫")
worksheet_trans = sheet.worksheet("transactions")
worksheet_inv = sheet.worksheet("inventory")

# ==========================================
# 2. 前端網頁介面設計
# ==========================================
st.set_page_config(page_title="財務進銷存系統", layout="wide")
st.title("💰 專屬進銷存與財務系統 (全中文雲端版)")

st.sidebar.header("📝 新增交易單")
trans_type = st.sidebar.selectbox("交易類別", ["銷貨 (賣出賺錢)", "進貨 (買入囤貨)"])

client_name = st.sidebar.text_input("客戶 / 廠商名稱 (例如：王老闆)")
item_name = st.sidebar.text_input("商品名稱 (例如：A級零件)")
qty = st.sidebar.number_input("數量", min_value=1, step=1)

if trans_type == "銷貨 (賣出賺錢)":
    price = st.sidebar.number_input("售出單價 (元)", min_value=0.0, step=1.0)
    cost = st.sidebar.number_input("當初進貨成本 (元) - 算利潤用", min_value=0.0, step=1.0)
    payment = st.sidebar.selectbox("結帳狀態", ["現金結清", "記帳/月結 (應收帳款)"])
else:
    price = st.sidebar.number_input("進貨單價 (元)", min_value=0.0, step=1.0)
    cost = price 
    payment = st.sidebar.selectbox("結帳狀態", ["現金結清", "記帳/月結 (應付帳款)"])

# ==========================================
# 3. 核心邏輯 (寫入 Google Sheets)
# ==========================================
if st.sidebar.button("💾 確認送出"):
    if item_name == "":
        st.sidebar.error("請輸入商品名稱！")
    else:
        total_amount = qty * price
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        profit = (price - cost) * qty if trans_type == "銷貨 (賣出賺錢)" else 0
        
        worksheet_trans.append_row([date_str, trans_type, item_name, qty, price, total_amount, payment, cost, profit, client_name])

        inv_records = worksheet_inv.get_all_records()
        item_exists = False
        row_index = 2 
        current_qty = 0

        for i, row in enumerate(inv_records):
            if str(row.get('商品名稱', '')) == item_name:
                item_exists = True
                current_qty = int(row.get('數量', 0))
                row_index = i + 2 
                break

        if "進貨" in trans_type:
            new_qty = current_qty + qty
            if item_exists:
                worksheet_inv.update_cell(row_index, 2, new_qty)
            else:
                worksheet_inv.append_row([item_name, new_qty])
            st.sidebar.success(f"✅ 成功進貨！金額 ${total_amount:,.0f} ({payment})")
            
        elif "銷貨" in trans_type:
            new_qty = current_qty - qty 
            if item_exists:
                worksheet_inv.update_cell(row_index, 2, new_qty)
            else:
                worksheet_inv.append_row([item_name, new_qty])
            st.sidebar.success(f"💰 成功接單！本單毛利：${profit:,.0f} ({payment})。🚨 提醒：目前庫存為 {new_qty} 件。")

# ==========================================
# 4. 資料清洗與財務儀表板
# ==========================================
st.markdown("---")
trans_data = worksheet_trans.get_all_records()

if trans_data:
    df_t = pd.DataFrame(trans_data)
    
    for col in ['數量', '單價', '總金額', '成本', '毛利']:
        if col in df_t.columns:
            df_t[col] = pd.to_numeric(df_t[col], errors='coerce').fillna(0)
            
    for col in ['類別', '商品名稱', '客戶名稱', '結帳狀態', '日期']:
        if col in df_t.columns:
            df_t[col] = df_t[col].astype(str).str.strip()
    
    df_t['純日期'] = pd.to_datetime(df_t['日期'], errors='coerce').dt.date
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    month_str = datetime.now().strftime("%Y-%m")
    
    if '類別' in df_t.columns:
        df_sales = df_t[df_t['類別'] == '銷貨 (賣出賺錢)']
        df_purchases = df_t[df_t['類別'] == '進貨 (買入囤貨)']
        
        if '毛利' in df_t.columns:
            daily_profit = df_sales[df_sales['日期'].str.startswith(today_str)]['毛利'].sum()
            monthly_profit = df_sales[df_sales['日期'].str.startswith(month_str)]['毛利'].sum()
        else:
            daily_profit, monthly_profit = 0, 0
            
        if '結帳狀態' in df_t.columns and '總金額' in df_t.columns:
            ar_total = df_sales[df_sales['結帳狀態'] == '記帳/月結 (應收帳款)']['總金額'].sum()
            ap_total = df_purchases[df_purchases['結帳狀態'] == '記帳/月結 (應付帳款)']['總金額'].sum()
        else:
            ar_total, ap_total = 0, 0
    else:
        daily_profit, monthly_profit, ar_total, ap_total = 0, 0, 0, 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🌟 今日實賺 (毛利)", f"${daily_profit:,.0f}")
    col2.metric("📈 本月累計獲利", f"${monthly_profit:,.0f}")
    col3.metric("⚠️ 在外未收 (應收帳款)", f"${ar_total:,.0f}")
    col4.metric("💳 待付貨款 (應付帳款)", f"${ap_total:,.0f}")

# ==========================================
# 5. 數據總覽與【三重交叉】查詢引擎
# ==========================================
st.markdown("---")
col_a, col_b = st.columns([1, 2])

with col_a:
    st.subheader("📦 目前庫存")
    inv_data = worksheet_inv.get_all_records()
    if inv_data:
        st.dataframe(pd.DataFrame(inv_data), use_container_width=True)

with col_b:
    st.subheader("🔍 歷史交易查詢 (三重交叉篩選)")
    if trans_data:
        # 抓取不重複的客戶與商品名單
        if '客戶名稱' in df_t.columns:
            client_list = df_t[df_t['客戶名稱'].str.contains('[a-zA-Z0-9\u4e00-\u9fa5]', regex=True, na=False)]['客戶名稱'].unique().tolist()
        else:
            client_list = []
            
        if '商品名稱' in df_t.columns:
            item_list = df_t[df_t['商品名稱'].str.contains('[a-zA-Z0-9\u4e00-\u9fa5]', regex=True, na=False)]['商品名稱'].unique().tolist()
        else:
            item_list = []
            
        # 第一排：客戶與商品並排
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            selected_client = st.selectbox("1️⃣ 請選擇客戶 (選填)：", ["-- 所有客戶 --"] + client_list)
        with filter_col2:
            selected_item = st.selectbox("2️⃣ 請選擇商品 (選填)：", ["-- 所有商品 --"] + item_list)
        
        # 第二排：日期區間
        today_date = datetime.now().date()
        first_day_of_month = today_date.replace(day=1)
        
        st.write("3️⃣ 請選擇結帳期間：")
        date_col1, date_col2 = st.columns(2)
        start_date = date_col1.date_input("📅 起始日期", value=first_day_of_month)
        end_date = date_col2.date_input("📅 結束日期", value=today_date)
        
        # 開始進行三重篩選
        filtered_df = df_t.copy()
        
        if selected_client != "-- 所有客戶 --":
            filtered_df = filtered_df[filtered_df['客戶名稱'] == selected_client]
            
        if selected_item != "-- 所有商品 --":
            filtered_df = filtered_df[filtered_df['商品名稱'] == selected_item]
            
        mask = (filtered_df['純日期'] >= start_date) & (filtered_df['純日期'] <= end_date)
        filtered_df = filtered_df[mask]
        
        # 顯示結算結果與提示字
        if selected_client != "-- 所有客戶 --" or selected_item != "-- 所有商品 --":
            c_sales = filtered_df[filtered_df['類別'] == '銷貨 (賣出賺錢)']['總金額'].sum()
            c_profit = filtered_df[filtered_df['類別'] == '銷貨 (賣出賺錢)']['毛利'].sum()
            
            # 動態組合標題
            title_str = ""
            if selected_client != "-- 所有客戶 --": title_str += f"客戶: {selected_client}  "
            if selected_item != "-- 所有商品 --": title_str += f"商品: {selected_item}  "
            
            st.success(f"📌 **[{title_str.strip()}]** 於所選期間 累計銷貨：${c_sales:,.0f} ｜ 💰 期間總毛利：${c_profit:,.0f}")
            
        display_df = filtered_df.drop(columns=['純日期']) if '純日期' in filtered_df.columns else filtered_df
        st.dataframe(display_df.iloc[::-1], use_container_width=True)

# ==========================================
# 6. 刪除與撤銷單據
# ==========================================
st.markdown("---")
st.subheader("🗑️ 刪除與撤銷單據")

if trans_data:
    delete_options = []
    for row in trans_data[::-1]:
        client_info = str(row.get('客戶名稱', '未填寫')).strip()
        if not client_info or client_info == 'nan':
            client_info = '未填寫'
        option_text = f"{row.get('日期', '')} | 客戶:{client_info} | {row.get('類別', '')} | {row.get('商品名稱', '')} | {row.get('數量', 0)}件"
        delete_options.append(option_text)
        
    selected_to_delete = st.selectbox("⚠️ 請選擇要撤銷的單據：", delete_options)
    
    if st.button("🚨 確認刪除並自動校正庫存"):
        target_date = selected_to_delete.split(" | ")[0]
        target_row_data = next((item for item in trans_data if str(item.get('日期', '')) == target_date), None)
        
        if target_row_data:
            try:
                cell = worksheet_trans.find(target_date)
                if cell:
                    worksheet_trans.delete_rows(cell.row)
                    
                    t_type = target_row_data.get('類別', '')
                    t_item = target_row_data.get('商品名稱', '')
                    t_qty = int(target_row_data.get('數量', 0))
                    
                    inv_records_current = worksheet_inv.get_all_records()
                    for i, inv_row in enumerate(inv_records_current):
                        if str(inv_row.get('商品名稱', '')) == t_item:
                            current_stock = int(inv_row.get('數量', 0))
                            row_index = i + 2
                            
                            if "銷貨" in t_type:
                                new_stock = current_stock + t_qty
                            elif "進貨" in t_type:
                                new_stock = current_stock - t_qty
                                
                            worksheet_inv.update_cell(row_index, 2, new_stock)
                            break
                            
                    st.success(f"✅ 成功刪除！單據已銷毀，庫存也已自動校正。請重新整理網頁查看最新數據。")
            except Exception as e:
                st.error("刪除過程中發生錯誤，請確認該單據是否已在試算表被手動刪除了。")
