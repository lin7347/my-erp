import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ==========================================
# 1. 資料庫連線
# ==========================================
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("key.json", scope)
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
        
        # 寫入交易紀錄 (對應 中文標題)
        worksheet_trans.append_row([date_str, trans_type, item_name, qty, price, total_amount, payment, cost, profit])

        # 庫存更新邏輯 (對應 中文標題)
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
            if item_exists and current_qty >= qty:
                new_qty = current_qty - qty
                worksheet_inv.update_cell(row_index, 2, new_qty)
                st.sidebar.success(f"💰 成功銷貨！本單毛利：${profit:,.0f} ({payment})")
            else:
                st.sidebar.error("⚠️ 失敗：倉庫裡的庫存不夠賣喔！")

# ==========================================
# 4. 財務儀表板 (即時算帳)
# ==========================================
st.markdown("---")
trans_data = worksheet_trans.get_all_records()

if trans_data:
    df_t = pd.DataFrame(trans_data)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    month_str = datetime.now().strftime("%Y-%m")
    
    # 根據中文標題計算指標
    if '類別' in df_t.columns:
        df_sales = df_t[df_t['類別'] == '銷貨 (賣出賺錢)']
        df_purchases = df_t[df_t['類別'] == '進貨 (買入囤貨)']
        
        if '毛利' in df_t.columns:
            # 轉換型別以防資料讀取為字串
            df_sales['毛利'] = pd.to_numeric(df_sales['毛利'], errors='coerce').fillna(0)
            daily_profit = df_sales[df_sales['日期'].astype(str).str.startswith(today_str)]['毛利'].sum()
            monthly_profit = df_sales[df_sales['日期'].astype(str).str.startswith(month_str)]['毛利'].sum()
        else:
            daily_profit, monthly_profit = 0, 0
            
        if '結帳狀態' in df_t.columns and '總金額' in df_t.columns:
            df_sales['總金額'] = pd.to_numeric(df_sales['總金額'], errors='coerce').fillna(0)
            df_purchases['總金額'] = pd.to_numeric(df_purchases['總金額'], errors='coerce').fillna(0)
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
# 5. 數據總覽明細
# ==========================================
st.markdown("---")
col_a, col_b = st.columns([1, 2])

with col_a:
    st.subheader("📦 目前庫存")
    inv_data = worksheet_inv.get_all_records()
    if inv_data:
        st.dataframe(pd.DataFrame(inv_data), use_container_width=True)

with col_b:
    st.subheader("🧾 交易與財務明細")
    if trans_data:
        st.dataframe(df_t.iloc[::-1], use_container_width=True)

# ==========================================
# 6. 刪除與撤銷單據 (一鍵校正庫存)
# ==========================================
st.markdown("---")
st.subheader("🗑️ 刪除與撤銷單據")

if trans_data:
    # 整理出下拉選單的選項 (顯示格式：日期 | 類別 | 商品 | 數量)
    delete_options = []
    for row in trans_data[::-1]: # 從最新的單據開始顯示
        option_text = f"{row['日期']} | {row['類別']} | {row['商品名稱']} | {row['數量']}件"
        delete_options.append(option_text)
        
    selected_to_delete = st.selectbox("⚠️ 請選擇要撤銷的單據：", delete_options)
    
    if st.button("🚨 確認刪除並自動校正庫存"):
        # 1. 抓出這筆單據的「日期時間」作為尋找目標
        target_date = selected_to_delete.split(" | ")[0]
        
        # 找出這筆單據的原始資料
        target_row_data = next((item for item in trans_data if str(item['日期']) == target_date), None)
        
        if target_row_data:
            try:
                # 2. 去交易紀錄表找出那一列並刪除
                cell = worksheet_trans.find(target_date)
                if cell:
                    worksheet_trans.delete_rows(cell.row)
                    
                    # 3. 去庫存表把數量加減回來
                    t_type = target_row_data['類別']
                    t_item = target_row_data['商品名稱']
                    t_qty = int(target_row_data['數量'])
                    
                    inv_records_current = worksheet_inv.get_all_records()
                    for i, inv_row in enumerate(inv_records_current):
                        if str(inv_row.get('商品名稱', '')) == t_item:
                            current_stock = int(inv_row.get('數量', 0))
                            row_index = i + 2
                            
                            # 商業邏輯：銷貨被刪除 -> 補回庫存；進貨被刪除 -> 扣除庫存
                            if "銷貨" in t_type:
                                new_stock = current_stock + t_qty
                            elif "進貨" in t_type:
                                new_stock = current_stock - t_qty
                                
                            worksheet_inv.update_cell(row_index, 2, new_stock)
                            break
                            
                    st.success(f"✅ 成功刪除！單據已銷毀，庫存也已自動校正。請重新整理網頁查看最新數據。")
            except Exception as e:
                st.error("刪除過程中發生錯誤，請確認該單據是否已在試算表被手動刪除了。")
