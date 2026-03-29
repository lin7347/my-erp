import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime  

# ==========================================
# 1. 建立並記住「連線工具」 (使用 cache_resource)
# ==========================================
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(st.secrets["google_credentials"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open("進銷存系統資料庫")
    
    # 把尋找分頁的動作也放進來，徹底阻絕重複連線！
    ws_trans = sheet.worksheet("transactions")
    ws_inv = sheet.worksheet("inventory")
    return ws_trans, ws_inv

# 呼叫連線工具 (程式怎麼重整，都不會重新連線)
worksheet_trans, worksheet_inv = init_connection()

# ==========================================
# 2. 抓取並記住「資料內容」 (使用 cache_data，設定 10 分鐘過期)
# ==========================================
@st.cache_data(ttl=600)
def get_erp_data():
    # 這裡才是真正去 Google 把所有資料撈下來變成表格的地方
    df_trans = pd.DataFrame(worksheet_trans.get_all_records())
    df_inv = pd.DataFrame(worksheet_inv.get_all_records())
    return df_trans, df_inv

# 呼叫資料 (10 分鐘內網頁隨便點，都不會耗費 Google 額度)
df_transactions, df_inventory = get_erp_data()

# ==========================================
# 測試顯示結果
# ==========================================
st.write("✅ 資料庫連線成功！")
st.dataframe(df_inventory)

# ==========================================
# 2. 前端網頁介面設計
# ==========================================
st.set_page_config(page_title="財務進銷存系統", layout="wide")
st.title("💰 專屬進銷存與財務系統 (全中文雲端版)")

st.sidebar.header("📝 新增交易單")
trans_type = st.sidebar.selectbox("交易類別", ["銷貨 (賣出賺錢)", "進貨 (買入囤貨)"])

client_name = st.sidebar.text_input("客戶 / 廠商名稱 (例如：王老闆)")
item_name = st.sidebar.text_input("商品名稱 (例如：A級零件)")
qty = st.sidebar.number_input("數量", min_value=1, value=1, step=1)

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
                try: current_qty = int(float(row.get('數量', 0)))
                except: current_qty = 0
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
            get_erp_data.clear()
            st.rerun()

# ==========================================
# 4. 資料清洗與財務儀表板 (新增現金結餘)
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
            
            # 👇 計算今日現金結餘 (只抓今天且現金結清的單)
            today_cash_in = df_sales[(df_sales['日期'].str.startswith(today_str)) & (df_sales['結帳狀態'] == '現金結清')]['總金額'].sum()
            today_cash_out = df_purchases[(df_purchases['日期'].str.startswith(today_str)) & (df_purchases['結帳狀態'] == '現金結清')]['總金額'].sum()
            daily_cash_balance = today_cash_in - today_cash_out
        else:
            ar_total, ap_total, daily_cash_balance = 0, 0, 0
    else:
        daily_profit, monthly_profit, ar_total, ap_total, daily_cash_balance = 0, 0, 0, 0, 0

    # 👇 改成 5 個看板並排顯示
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("💵 今日現金結餘", f"${daily_cash_balance:,.0f}")
    col2.metric("🌟 今日實賺 (毛利)", f"${daily_profit:,.0f}")
    col3.metric("📈 本月累計獲利", f"${monthly_profit:,.0f}")
    col4.metric("⚠️ 在外未收 (應收)", f"${ar_total:,.0f}")
    col5.metric("💳 待付貨款 (應付)", f"${ap_total:,.0f}")

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
        if '客戶名稱' in df_t.columns:
            client_list = df_t[df_t['客戶名稱'].str.contains('[a-zA-Z0-9\u4e00-\u9fa5]', regex=True, na=False)]['客戶名稱'].unique().tolist()
        else:
            client_list = []
            
        if '商品名稱' in df_t.columns:
            item_list = df_t[df_t['商品名稱'].str.contains('[a-zA-Z0-9\u4e00-\u9fa5]', regex=True, na=False)]['商品名稱'].unique().tolist()
        else:
            item_list = []
            
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            selected_client = st.selectbox("1️⃣ 請選擇客戶 (選填)：", ["-- 所有客戶 --"] + client_list)
        with filter_col2:
            selected_item = st.selectbox("2️⃣ 請選擇商品 (選填)：", ["-- 所有商品 --"] + item_list)
        
        today_date = datetime.now().date()
        first_day_of_month = today_date.replace(day=1)
        
        st.write("3️⃣ 請選擇結帳期間：")
        date_col1, date_col2 = st.columns(2)
        start_date = date_col1.date_input("📅 起始日期", value=first_day_of_month)
        end_date = date_col2.date_input("📅 結束日期", value=today_date)
        
        filtered_df = df_t.copy()
        
        if selected_client != "-- 所有客戶 --":
            filtered_df = filtered_df[filtered_df['客戶名稱'] == selected_client]
            
        if selected_item != "-- 所有商品 --":
            filtered_df = filtered_df[filtered_df['商品名稱'] == selected_item]
            
        # 核心篩選：套用日期區間
        mask = (filtered_df['純日期'] >= start_date) & (filtered_df['純日期'] <= end_date)
        filtered_df = filtered_df[mask]
        
        # 👇 【修改重點】解除 if 限制，讓系統一定會計算並顯示區間合計！
        # 順便幫您把「進貨總額」也算出來，這樣對帳更清楚
        c_sales = filtered_df[filtered_df['類別'] == '銷貨 (賣出賺錢)']['總金額'].sum()
        c_purchase = filtered_df[filtered_df['類別'] == '進貨 (買入囤貨)']['總金額'].sum()
        c_profit = filtered_df[filtered_df['類別'] == '銷貨 (賣出賺錢)']['毛利'].sum()
        
        # 動態產生標題
        title_str = "全部客戶與商品"
        if selected_client != "-- 所有客戶 --" or selected_item != "-- 所有商品 --":
            title_str = ""
            if selected_client != "-- 所有客戶 --": title_str += f"客戶:{selected_client}  "
            if selected_item != "-- 所有商品 --": title_str += f"商品:{selected_item}  "
        
        # 顯示統計看板
        st.info(f"📅 **查詢區間：{start_date} 至 {end_date}**")
        st.success(f"📌 [{title_str.strip()}] 累計銷貨：${c_sales:,.0f} ｜ 📦 累計進貨：${c_purchase:,.0f} ｜ 💰 總毛利：${c_profit:,.0f}")
        
        # 顯示資料表
        display_df = filtered_df.drop(columns=['純日期']) if '純日期' in filtered_df.columns else filtered_df
        st.dataframe(display_df.iloc[::-1], use_container_width=True)

        # ==========================================
        # 新增：營收與毛利趨勢長條圖
        # ==========================================
        st.markdown("#### 📊 每日營收與毛利趨勢")
        
        if not filtered_df.empty:
            # 1. 只挑出「銷貨 (賣出賺錢)」的資料來畫圖，過濾掉進貨成本
            sales_df = filtered_df[filtered_df['類別'] == '銷貨 (賣出賺錢)']
            
            if not sales_df.empty:
                # 2. 依照「純日期」分組，把每天的「總金額」跟「毛利」加總起來
                trend_data = sales_df.groupby('純日期')[['總金額', '毛利']].sum()
                
                # 3. 把欄位名稱改得更直觀一點，這會顯示在圖表的圖例上
                trend_data.rename(columns={'總金額': '每日營業額', '毛利': '每日實賺(毛利)'}, inplace=True)
                
                # 4. 直接呼叫 Streamlit 內建的長條圖函數！
                st.bar_chart(trend_data)
            else:
                st.info("💡 這段期間內尚無銷貨紀錄，暫時無法產生營收圖表。")
                
# ==========================================
# 6. 應收/應付帳款 結帳中心
# ==========================================
st.markdown("---")
st.subheader("💳 應收/應付帳款 結帳中心")

if trans_data:
    unpaid_options = []
    for row in trans_data[::-1]:
        payment_status = str(row.get('結帳狀態', ''))
        if "記帳/月結" in payment_status:
            client_info = str(row.get('客戶名稱', '未填寫')).strip()
            if not client_info or client_info == 'nan':
                client_info = '未填寫'
            
            money_type = "💰 應收" if "應收帳款" in payment_status else "💸 應付"
            option_text = f"{row.get('日期', '')} | {money_type} | 客戶:{client_info} | {row.get('商品名稱', '')} | 金額: ${row.get('總金額', 0):,.0f}"
            unpaid_options.append(option_text)
            
    if unpaid_options:
        selected_to_pay = st.selectbox("請選擇要「結清」的帳單：", unpaid_options)
        
        if st.button("✅ 確認款項已收/付 (更改為已結清)"):
            target_date = selected_to_pay.split(" | ")[0]
            try:
                cell = worksheet_trans.find(target_date)
                if cell:
                    worksheet_trans.update_cell(cell.row, 7, "✅ 已結清 (歷史沖帳)")
                    st.success(f"🎉 成功沖帳！單據狀態已更新，財務儀表板的未收/未付金額已同步扣除。請重新整理網頁！")
            except Exception as e:
                st.error("結帳過程中發生錯誤，請確認網路狀態或稍後再試。")
    else:
        st.info("🎉 太棒了！目前沒有任何在外欠款或待付帳單。")

# ==========================================
# 7. 刪除與撤銷單據
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
                    try: t_qty = int(float(target_row_data.get('數量', 0)))
                    except: t_qty = 0
                    
                    inv_records_current = worksheet_inv.get_all_records()
                    for i, inv_row in enumerate(inv_records_current):
                        if str(inv_row.get('商品名稱', '')) == t_item:
                            try: current_stock = int(float(inv_row.get('數量', 0)))
                            except: current_stock = 0
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


