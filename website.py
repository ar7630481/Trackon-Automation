import streamlit as st
import pandas as pd
import numpy as np
import warnings
import io
import os
import pickle
import urllib.request
import urllib.parse
import time
import shutil
from datetime import datetime
from playwright.sync_api import sync_playwright
import pdfplumber
from streamlit_autorefresh import st_autorefresh

warnings.filterwarnings('ignore')

os.system("playwright install chromium")

# ==========================================
# PAGE SETUP & UI
# ==========================================
st.set_page_config(page_title="Trackon Dashboard", layout="wide", page_icon="🚛")

# ==========================================
# LOGIN SYSTEM
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_role'] = ''

if not st.session_state['logged_in']:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Trackon Login")
        st.markdown("---")
        user_id = st.text_input("User ID")
        pwd = st.text_input("Password", type="password")
        
        if st.button("Login", type="primary", use_container_width=True):
            if user_id == "admin" and pwd == "9211213215":
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = "Admin"
                st.rerun()
            elif user_id == "user" and pwd == "52729211":
                st.session_state['logged_in'] = True
                st.session_state['user_role'] = "User"
                st.rerun()
            else:
                st.error("Invalid ID or Password.")
    st.stop()

# ==========================================
# LOGOUT BUTTON & APP HEADER
# ==========================================
st.sidebar.success(f"🟢 Logged in as: {st.session_state['user_role']}")
if st.sidebar.button("Logout", type="secondary"):
    st.session_state['logged_in'] = False
    st.rerun()

st.title("🚛 Trackon Dashboard")
st.markdown("---")

# ==========================================
# BACKGROUND AUTO-REFRESH (Every 5 Minutes)
# ==========================================
st_autorefresh(interval=300000, key="fleet_auto_refresh")

# ==========================================
# HELPER FUNCTIONS (ANALYTICS & OPERATIONS)
# ==========================================
def format_pct_cnt(count, total):
    if total == 0 or pd.isna(total): return "0.0% (0)"
    pct = (count / total) * 100
    return f"{pct:.1f}% ({int(count)})"

def format_hrs_safe(hrs):
    if pd.isna(hrs): return ""
    sign = "-" if hrs < 0 else ""
    hrs = abs(hrs)
    h = int(hrs)
    m = int(round((hrs - h) * 60))
    if m == 60: 
        h += 1
        m = 0
    return f"{sign}{h}:{m:02d}"

def format_hhmm(t):
    if pd.isna(t): return ""
    t_str = str(t).strip()
    if t_str.lower() in ['', 'nan', 'nat']: return ""
    if hasattr(t, 'hour'): return f"{t.hour:02d}:{t.minute:02d}"
    if ':' in t_str: 
        parts = t_str.split(':')
        try: return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        except: return t_str
    return t_str

def extract_orig_dest(route_str):
    s = str(route_str).upper()
    parts = s.replace(' TO ', '-').split('-')
    if len(parts) >= 2: return parts[0].strip(), parts[-1].strip()
    return s, s

def get_route_pair(route_str):
    o, d = extract_orig_dest(route_str)
    return f"{min(o, d)}-{max(o, d)}"

def time_to_hrs(t):
    if pd.isna(t): return np.nan
    t_str = str(t).strip()
    if t_str.lower() in ['', 'nan', 'nat']: return np.nan
    if hasattr(t, 'hour'): return t.hour + t.minute / 60.0
    if ':' in t_str:
        parts = t_str.split(':')
        if len(parts) >= 2:
            try: return float(parts[0]) + float(parts[1])/60.0
            except: return np.nan
    try: return float(t_str)
    except: return np.nan

def get_day_offset(day_val):
    try:
        if pd.isna(day_val): return np.nan
        return float(day_val) * 24
    except: return np.nan

# ==========================================
# HELPER FUNCTIONS (LIVE FLEET GPS)
# ==========================================
FLEET_ACCOUNTS = [
    {"email": "anand.joshi@trackon.in", "password": "Trackon@123"},
    {"email": "lh.fleetops@trackon.in", "password": "i7F0TYVh@"},
    {"email": "amar.vandanamotors@gmail.com", "password": "Amar@123"},
    {"email": "9712339060", "password": "Boss@9918"}
]

def clear_pre_modal_popups(page):
    try:
        close_btn = page.locator('span.ant-tour-close-icon')
        if close_btn.is_visible(timeout=1000): close_btn.click()
    except: pass
    try:
        next_btn = page.locator("span", has_text="Next")
        if next_btn.is_visible(timeout=1000): next_btn.click()
    except: pass
    try:
        svg_close = page.locator('svg[data-icon="close"]')
        if svg_close.is_visible(timeout=1000): svg_close.click()
    except: pass

@st.cache_data(ttl=300, show_spinner=False)
def fetch_fleet_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    all_raw_data = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage']
            ) 
            
            for acc in FLEET_ACCOUNTS:
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                
                safe_email = acc['email'].replace('@', '_').replace('.', '_')
                pdf_path = os.path.join(script_dir, f"temp_{safe_email}.pdf")
                
                try:
                    page.goto("https://app.fleetx.io/users/login", timeout=90000, wait_until="domcontentloaded")
                    page.fill('input[data-testid="email"]', acc['email'])
                    page.fill('input[data-testid="password"]', acc['password'])
                    page.click('button[type="submit"]')

                    page.wait_for_selector('img[title="Realtime Vehicle Report"]', timeout=90000)
                    page.wait_for_timeout(2000)
                    clear_pre_modal_popups(page)
                    page.evaluate("document.querySelector('img[title=\"Realtime Vehicle Report\"]').click()")
                    page.wait_for_timeout(2000) 
                    page.evaluate("Array.from(document.querySelectorAll('span')).find(el => el.textContent.trim() === 'Download PDF')?.click()")
                    page.wait_for_timeout(2000) 

                    if os.path.exists(pdf_path): 
                        try: os.remove(pdf_path)
                        except: pass

                    # AWS Logic
                    if "anand.joshi" in acc['email'] or "lh.fleetops" in acc['email']:
                        captured_urls = []
                        def handle_new_page(new_page):
                            new_page.wait_for_timeout(3000)
                            captured_urls.append(new_page.url)

                        context.on("page", handle_new_page)
                        page.evaluate("Array.from(document.querySelectorAll('span')).find(el => el.textContent.trim() === 'Download')?.click()")
                        
                        pdf_url = ""
                        for _ in range(40):
                            for url in captured_urls:
                                if "amazonaws.com" in url or ".pdf" in url.lower():
                                    pdf_url = url
                                    break
                            if not pdf_url:
                                for p_tab in context.pages:
                                    if "amazonaws.com" in p_tab.url or ".pdf" in p_tab.url.lower():
                                        pdf_url = p_tab.url
                                        break
                            if pdf_url: break
                            page.wait_for_timeout(1000)
                            
                        if pdf_url:
                            urllib.request.urlretrieve(pdf_url, pdf_path)

                    # CDP Logic
                    else:
                        dl_folder = os.path.join(script_dir, f"dl_{safe_email}")
                        os.makedirs(dl_folder, exist_ok=True)
                        
                        for f in os.listdir(dl_folder):
                            try: os.remove(os.path.join(dl_folder, f))
                            except: pass

                        client = context.new_cdp_session(page)
                        client.send("Page.setDownloadBehavior", {
                            "behavior": "allow",
                            "downloadPath": dl_folder
                        })

                        page.evaluate("Array.from(document.querySelectorAll('span')).find(el => el.textContent.trim() === 'Download')?.click()")
                        
                        for _ in range(60): 
                            files = os.listdir(dl_folder)
                            if not files:
                                time.sleep(1)
                                continue
                            if any(f.lower().endswith(('.tmp', '.crdownload')) for f in files):
                                time.sleep(1)
                                continue
                                
                            pdf_files = [f for f in files if f.lower().endswith('.pdf')]
                            if pdf_files:
                                downloaded_file = os.path.join(dl_folder, pdf_files[0])
                                shutil.move(downloaded_file, pdf_path)
                                break
                            time.sleep(1)
                        try: shutil.rmtree(dl_folder)
                        except: pass

                    if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                        with pdfplumber.open(pdf_path) as pdf:
                            for page_obj in pdf.pages:
                                table = page_obj.extract_table()
                                if table:
                                    for row in table:
                                        if any(cell and str(cell).strip() for cell in row):
                                            all_raw_data.append(row)
                        try: os.remove(pdf_path)
                        except: pass
                except Exception as e:
                    pass
                finally:
                    context.close()
            browser.close()
            
        if all_raw_data:
            max_cols = max(len(row) for row in all_raw_data)
            normalized_data = [row + [""] * (max_cols - len(row)) for row in all_raw_data]
            df = pd.DataFrame(normalized_data[1:], columns=normalized_data[0])
            df.columns = [str(c).replace('\n', ' ').strip() if c else f"Col_{i}" for i, c in enumerate(df.columns)]
            
            # Robust Column Matching
            veh_col = next((c for c in df.columns if 'veh' in str(c).lower() or 'name' in str(c).lower()), None)
            status_col = next((c for c in df.columns if 'stat' in str(c).lower() and 'job' not in str(c).lower()), None)
            speed_col = next((c for c in df.columns if 'spee' in str(c).lower()), None)
            nearest_col = next((c for c in df.columns if 'near' in str(c).lower() or 'rem' in str(c).lower()), None)
            loc_col = next((c for c in df.columns if 'loc' in str(c).lower()), None)
            time_col = next((c for c in df.columns if 'last' in str(c).lower() or 'date' in str(c).lower() or 'time' in str(c).lower()), None)

            if veh_col:
                raw_str = df[veh_col].astype(str).str.replace(r'\n', ' ', regex=True)
                df['Vehicle_Code'] = raw_str.str.extract(r'(\d{4})', expand=False).fillna("-")
                df['Full_Number'] = raw_str.str.extract(r'(?i)No:\s*([A-Z0-9]+)', expand=False).combine_first(raw_str.str.extract(r'([A-Z]{2}\d{1,2}[A-Z]{1,2}\d{4})', expand=False)).fillna("-")
            else:
                df['Vehicle_Code'] = "-"
                df['Full_Number'] = "-"
                
            df['Status'] = df[status_col].astype(str).str.replace(r'\n', ' ', regex=True).str.strip() if status_col else "-"
            df['Speed'] = df[speed_col].astype(str).str.replace(r'\n', ' ', regex=True).str.strip() if speed_col else "-"
            df['Remaining_KMS'] = df[nearest_col].astype(str).str.replace(r'\n', ' ', regex=True).str.strip() if nearest_col else "-"
            df['Location'] = df[loc_col].astype(str).str.replace(r'\n', ' ', regex=True).str.strip() if loc_col else "-"
            df['Last_Updated'] = df[time_col].astype(str).str.replace(r'\n', ' ', regex=True).str.strip() if time_col else "-"

            final_cols = ['Vehicle_Code', 'Full_Number', 'Status', 'Speed', 'Remaining_KMS', 'Location', 'Last_Updated']
            for col in final_cols:
                if col not in df.columns:
                    df[col] = "-"
                    
            df_clean = df[final_cols]
            df_clean = df_clean.drop_duplicates(subset=['Full_Number'], keep='first')
            
            st.session_state['cached_gps_df'] = df_clean
            st.session_state['last_sync_time'] = datetime.now().strftime("%I:%M %p, %d %b %Y")
            return df_clean
        else:
            return pd.DataFrame()
    except Exception as e:
        return st.session_state.get('cached_gps_df', pd.DataFrame())

# ==========================================
# ROLE-BASED DASHBOARD LOGIC (FILES)
# ==========================================
data_ready = False

if st.session_state['user_role'] == 'Admin':
    st.sidebar.header("📂 Upload Data Files")
    payment_file = st.sidebar.file_uploader("1. Payment Tracking Data", type=['xlsx'])
    legwise_file = st.sidebar.file_uploader("2. Ondemand Legwise Report", type=['xlsx'])
    route_file = st.sidebar.file_uploader("3. Scheduled Route Master", type=['xlsx'])
    branch_file = st.sidebar.file_uploader("4. RO & Branch List", type=['xlsx'])
    mcd_file = st.sidebar.file_uploader("5. Monthly MCD Vendor Data", type=['xlsx'])

    if st.sidebar.button("Process Files", type="primary"):
        if not all([payment_file, legwise_file, route_file, branch_file, mcd_file]):
            st.sidebar.error("All 5 files are required.")
        else:
            with st.spinner("Processing files..."):
                
                # --- MODULE 1: VENDOR PAYMENT TRACKING ---
                df_pay = pd.read_excel(payment_file)
                df_pay.columns = df_pay.columns.astype(str).str.strip().str.upper().str.replace(" ", "").str.replace("_", "")
                
                rename_dict = {}
                for col in df_pay.columns:
                    if 'ROSELECTION' in col: rename_dict[col] = 'RO Name'
                    elif 'CATEGORY' in col: rename_dict[col] = 'Category'
                    elif 'VENDORNAME' in col: rename_dict[col] = 'Vendor Name'
                    elif 'INVOICEID' in col: rename_dict[col] = 'Invoice Id'
                    elif 'INVOICEDATE' in col: rename_dict[col] = 'Invoice Date'
                    elif 'AMOUNT' == col: rename_dict[col] = 'Amount'
                    elif 'STATUS' == col: rename_dict[col] = 'Status'
                    elif 'PENDINGWITH' in col: rename_dict[col] = 'Pending With'
                    elif 'LASTAPPROVEDAT' in col: rename_dict[col] = 'Last Approved At'
                    elif 'FINANCEREVERTREMARKS1' in col: rename_dict[col] = 'Finance Revert Remarks 1'
                    elif 'APPROVERREVERTREMARKS' in col: rename_dict[col] = 'Approver Revert Remarks'
                    elif 'HOLD.KEY' in col or 'HOLDKEY' in col: rename_dict[col] = 'Hold Key'
                    elif 'NAME' == col or 'UPLOADERNAME' in col or 'BILLUPLOADER' in col: rename_dict[col] = 'Bill Uploader'

                df_pay.rename(columns=rename_dict, inplace=True)
                
                required_cols = ['RO Name', 'Category', 'Vendor Name', 'Invoice Id', 'Invoice Date', 'Amount', 'Status', 'Pending With', 'Last Approved At', 'Finance Revert Remarks 1', 'Approver Revert Remarks', 'Hold Key', 'Bill Uploader']
                for req in required_cols:
                    if req not in df_pay.columns: df_pay[req] = ""
                        
                df_pay['Vendor Name'] = df_pay['Vendor Name'].fillna('').astype(str).str.upper().str.strip()
                df_pay['Category'] = df_pay['Category'].fillna('').astype(str).str.strip()
                df_pay['Status'] = df_pay['Status'].fillna('').astype(str).str.upper()
                df_pay['Pending With'] = df_pay['Pending With'].fillna('').astype(str).str.upper()
                
                valid_cats = ["Contract - Feeder Connection vehicle charges", "Market - Feeder Connection vehicle charges", 
                              "Market Vehicle Hired -Linehaul", "Contract Network Vehicle Hired - Regional", 
                              "Contract Network Vehicle Hired - Zonal", "Contract Network Vehicle Hired - National"]
                df_pay = df_pay[df_pay['Category'].isin(valid_cats)]
                
                vip_vends = ["SHRI GANPATI", "MOHD ASLAM", "MEHTAROAD", "E WHEELS", "TEJAS", "T T TRANSPORT", 
                             "APL EXPRESS", "GOTRUCKS", "RADHA RANI", "FASTLANE", "MMM LOGISTICS", "ATA ROADWAYS", "ZAST", "FLEETX"]
                df_pay = df_pay[~df_pay['Vendor Name'].str.contains('|'.join(vip_vends), na=False, regex=True)].copy()
                df_pay = df_pay[~df_pay['Status'].str.contains('PAID|PROCESSED|CANCELLED|DECLINED', na=False)]
                
                df_pay['Finance Revert Remarks 1'] = df_pay.get('Finance Revert Remarks 1', pd.Series(['']*len(df_pay))).fillna('')
                df_pay['Approver Revert Remarks'] = df_pay.get('Approver Revert Remarks', pd.Series(['']*len(df_pay))).fillna('')
                df_pay['Revert Remarks'] = np.where(df_pay['Finance Revert Remarks 1'] != '', df_pay['Finance Revert Remarks 1'], df_pay['Approver Revert Remarks'])
                
                conds = [
                    (df_pay['Status'].str.contains('PAYMENT') | df_pay['Pending With'].str.contains('PAYMENT')),
                    (df_pay['Status'].str.contains('FINANCE') | df_pay['Pending With'].str.contains('FINANCE|LEVEL 3') | df_pay['Status'].str.contains('HOLD')),
                    (df_pay['Revert Remarks'] != '') | (df_pay['Status'].str.contains('DRAFT')) | (df_pay['Pending With'].str.contains('AJAY')),
                    (df_pay['Status'].str.contains('PENDING') | df_pay['Pending With'].str.contains('COST CONTROL|OPSACCTS|ACC'))
                ]
                df_pay['Department Bucket'] = np.select(conds, ["4. PAYMENT PENDING", "3. FINANCE PENDING", "1. USER / DRAFT PENDING", "2. COST CONTROL PENDING"], "5. OTHER PENDING")
                
                today = pd.to_datetime('today').normalize()
                df_pay['Last Approved At'] = pd.to_datetime(df_pay['Last Approved At'], dayfirst=True, errors='coerce').dt.normalize()
                df_pay['Invoice Date'] = pd.to_datetime(df_pay['Invoice Date'], dayfirst=True, errors='coerce').dt.normalize()
                df_pay['Base Date'] = df_pay['Last Approved At'].combine_first(df_pay['Invoice Date']).fillna(today)
                df_pay['Days Pending'] = (today - df_pay['Base Date']).dt.days
                df_pay['Aging Bucket'] = np.where(df_pay['Days Pending'] <= 5, "1. 0-5 Days", "2. >5 Days")
                df_pay['Base Date'] = df_pay['Base Date'].dt.strftime('%d-%b-%Y').fillna("")
                df_pay['Invoice Month'] = df_pay['Invoice Date'].dt.strftime('%b-%Y').fillna("UNKNOWN")
                
                df_master = df_pay[["RO Name", "Category", "Vendor Name", "Bill Uploader", "Invoice Id", "Hold Key", "Aging Bucket", "Invoice Month", "Days Pending", "Status", "Pending With", "Revert Remarks", "Department Bucket", "Amount", "Base Date"]]
                df_cc = df_pay[df_pay['Department Bucket'] == "2. COST CONTROL PENDING"]
                df_fin = df_pay[df_pay['Department Bucket'] == "3. FINANCE PENDING"]
                df_pay_team = df_pay[df_pay['Department Bucket'] == "4. PAYMENT PENDING"]
                
                pvt_master = pd.pivot_table(df_master, values='Invoice Id', index='RO Name', columns='Department Bucket', aggfunc='count', fill_value=0, margins=True, margins_name='Grand Total')
                pvt_cc = pd.pivot_table(df_cc, values='Invoice Id', index='RO Name', columns='Aging Bucket', aggfunc='count', fill_value=0, margins=True, margins_name='Grand Total')
                pvt_fin = pd.pivot_table(df_fin, values='Invoice Id', index='RO Name', columns='Aging Bucket', aggfunc='count', fill_value=0, margins=True, margins_name='Grand Total')
                pvt_pay = pd.pivot_table(df_pay_team, values='Invoice Id', index='RO Name', columns='Aging Bucket', aggfunc='count', fill_value=0, margins=True, margins_name='Grand Total')

                # --- MODULE 2: OPERATIONS COMMAND CENTER ---
                df_leg = pd.read_excel(legwise_file, sheet_name="Sheet1")
                df_rte = pd.read_excel(route_file, sheet_name="RoutePathReportModel")
                df_brn = pd.read_excel(branch_file, sheet_name="Sheet1")
                
                df_rte_tat = df_rte.copy()
                df_rte_tat['Dep_Hrs'] = df_rte_tat['Schedule Departure Time'].apply(time_to_hrs)
                df_rte_tat['Arr_Hrs'] = df_rte_tat['Schedule Arrival Time'].apply(time_to_hrs)
                df_rte_tat['Day_Offset'] = df_rte_tat['Route Day'].apply(get_day_offset)
                df_rte_tat['Abs_Dep'] = df_rte_tat['Day_Offset'] + df_rte_tat['Dep_Hrs']
                df_rte_tat['Abs_Arr'] = df_rte_tat['Day_Offset'] + df_rte_tat['Arr_Hrs']
                
                route_tat_master = df_rte_tat.groupby('Route Code').agg(Min_Dep=('Abs_Dep', 'min'), Max_Arr=('Abs_Arr', 'max')).reset_index()
                route_tat_master['Master_Sch_E2E_Hrs'] = route_tat_master['Max_Arr'] - route_tat_master['Min_Dep']
                route_tat_master['Scheduled TAT Till Destination'] = route_tat_master['Master_Sch_E2E_Hrs'].apply(format_hrs_safe)

                df_leg.columns = df_leg.columns.str.strip()
                df_leg = df_leg[(df_leg['MCD_Created_By'] == 'SCHEDULED') & (df_leg['LH_Type'].isin(['National LH', 'Zonal LH']))]
                df_leg['MCD_StartDate_DT'] = pd.to_datetime(df_leg['MCD_StartDate'], dayfirst=True, errors='coerce')
                df_leg['Leg_Num'] = df_leg['Legwise'].astype(str).str.extract(r'(\d+)').astype(float).fillna(1)
                df_leg = df_leg.sort_values(by=['RouteCode', 'MCD_StartDate_DT', 'Min_CD_StartDatetime'])
                
                dedup = df_leg.groupby(['RouteCode', 'MCD_StartDate_DT'])['MasterCDNo'].first().reset_index()
                df_leg = df_leg.merge(dedup, on=['RouteCode', 'MCD_StartDate_DT', 'MasterCDNo'])
                df_leg['Legs'] = df_leg['CD_FromBranch'].astype(str) + " to " + df_leg['CD_ToBranch'].astype(str)
                df_leg.rename(columns={'Min_CD_StartDatetime': 'Actual Departure Time', 'Max_CD_EndDatetime': 'Actual Arrival Time', 'Route': 'Route Path'}, inplace=True)
                
                df_brn = df_brn[['RPTBranchcode', 'RPTRO', 'Zone']].drop_duplicates()
                df_leg = df_leg.merge(df_brn, left_on='CD_FromBranch', right_on='RPTBranchcode', how='left')
                df_leg.rename(columns={'RPTRO': 'Origin RO', 'Zone': 'Region'}, inplace=True)
                df_leg['Region'] = df_leg['Region'].fillna('Missing RO')
                
                trip_origins = df_leg.sort_values('Leg_Num').groupby('MasterCDNo').first()[['Region', 'Origin RO']].reset_index()
                trip_origins.rename(columns={'Region': 'Trip_Region', 'Origin RO': 'Trip_Origin_RO'}, inplace=True)
                df_leg = df_leg.merge(trip_origins, on='MasterCDNo', how='left')
                df_leg['Region'] = df_leg['Trip_Region']
                df_leg['Origin RO'] = df_leg['Trip_Origin_RO']
                df_leg[['Origin', 'Destination']] = df_leg['Route Path'].apply(lambda x: pd.Series(extract_orig_dest(x)))
                df_leg['E2E_Pair'] = df_leg['Route Path'].apply(get_route_pair)
                df_leg.rename(columns={'LH_Type': 'LH Type'}, inplace=True)
                
                df_leg = df_leg.merge(route_tat_master[['Route Code', 'Scheduled TAT Till Destination']], left_on='RouteCode', right_on='Route Code', how='left')
                df_rte_sub = df_rte[['Route Code', 'Route Branch Code', 'Route Day', 'Schedule Departure Time', 'Schedule Arrival Time']]
                
                df_leg = df_leg.merge(df_rte_sub, left_on=['RouteCode', 'CD_FromBranch'], right_on=['Route Code', 'Route Branch Code'], how='left')
                df_leg.rename(columns={'Route Day': 'Dep_Route_Day', 'Schedule Departure Time': 'Sch_Dep_Time_Raw'}, inplace=True)
                df_leg.drop(columns=['Schedule Arrival Time'], inplace=True, errors='ignore')
                
                df_leg = df_leg.merge(df_rte_sub[['Route Code', 'Route Branch Code', 'Route Day', 'Schedule Arrival Time']], 
                                      left_on=['RouteCode', 'CD_ToBranch'], right_on=['Route Code', 'Route Branch Code'], how='left')
                df_leg.rename(columns={'Route Day': 'Arr_Route_Day', 'Schedule Arrival Time': 'Sch_Arr_Time_Raw'}, inplace=True)

                def get_sch_time(r, day_c, time_c):
                    try:
                        if pd.isna(r['MCD_StartDate_DT']) or pd.isna(r[day_c]): return pd.NaT
                        day_offset = float(r[day_c])
                        d = r['MCD_StartDate_DT'] + pd.to_timedelta(day_offset, unit='D')
                        t_str = str(r[time_c]).strip()
                        if t_str == 'nan' or not t_str: return pd.NaT
                        return pd.to_datetime(d.strftime('%Y-%m-%d') + ' ' + str(pd.to_datetime(t_str).time()))
                    except: return pd.NaT
                    
                df_leg['Scheduled Departure Time'] = df_leg.apply(lambda r: get_sch_time(r, 'Dep_Route_Day', 'Sch_Dep_Time_Raw'), axis=1)
                df_leg['Scheduled Arrival Time'] = df_leg.apply(lambda r: get_sch_time(r, 'Arr_Route_Day', 'Sch_Arr_Time_Raw'), axis=1)
                df_leg['Actual Departure Time'] = pd.to_datetime(df_leg['Actual Departure Time'], dayfirst=True, errors='coerce')
                df_leg['Actual Arrival Time'] = pd.to_datetime(df_leg['Actual Arrival Time'], dayfirst=True, errors='coerce')
                
                def apply_abs(day_val, time_val):
                    d = get_day_offset(day_val)
                    t = time_to_hrs(time_val)
                    return d + t if pd.notna(d) and pd.notna(t) else np.nan

                df_leg['Abs_Dep_Hrs'] = df_leg.apply(lambda r: apply_abs(r['Dep_Route_Day'], r['Sch_Dep_Time_Raw']), axis=1)
                df_leg['Abs_Arr_Hrs'] = df_leg.apply(lambda r: apply_abs(r['Arr_Route_Day'], r['Sch_Arr_Time_Raw']), axis=1)
                
                route_master_df = df_leg.drop_duplicates(subset=['Route Path', 'Leg_Num']).copy()
                route_master_df = route_master_df.sort_values(by=['LH Type', 'E2E_Pair', 'Origin', 'Route Path', 'Leg_Num'])
                route_master_df['Prev_Abs_Arr_Hrs'] = route_master_df.groupby('Route Path')['Abs_Arr_Hrs'].shift(1)
                
                def calc_master_sch_halt(abs_dep, prev_abs_arr, leg_num, branch):
                    if leg_num == 1: return "Origin"
                    if pd.isna(abs_dep) or pd.isna(prev_abs_arr): return f"0:00 at {branch}"
                    return f"{format_hrs_safe(abs_dep - prev_abs_arr)} at {branch}"

                route_master_df['Scheduled Halting'] = route_master_df.apply(lambda r: calc_master_sch_halt(r['Abs_Dep_Hrs'], r['Prev_Abs_Arr_Hrs'], r['Leg_Num'], r['CD_FromBranch']), axis=1)
                route_master_df['Given Driving Hours'] = (route_master_df['Abs_Arr_Hrs'] - route_master_df['Abs_Dep_Hrs']).apply(format_hrs_safe)
                route_master_df['Scheduled Departure Time'] = pd.to_datetime(route_master_df['Scheduled Departure Time']).dt.strftime('%d-%m-%Y %H:%M').fillna('N/A')
                route_master_df['Scheduled Arrival Time'] = pd.to_datetime(route_master_df['Scheduled Arrival Time']).dt.strftime('%d-%m-%Y %H:%M').fillna('N/A')
                
                rm_cols = ['Region', 'Route Path', 'Legwise', 'Legs', 'Scheduled Departure Time', 'Scheduled Arrival Time', 'Given Driving Hours', 'Scheduled Halting', 'Scheduled TAT Till Destination']
                route_master_df = route_master_df[rm_cols]

                df_leg = df_leg.merge(route_master_df[['Route Path', 'Legwise', 'Scheduled Halting', 'Given Driving Hours']], on=['Route Path', 'Legwise'], how='left')
                df_leg = df_leg.sort_values(by=['LH Type', 'E2E_Pair', 'Origin', 'Route Path', 'MasterCDNo', 'Leg_Num'])
                df_leg['Prev_Act_Arr'] = df_leg.groupby('MasterCDNo')['Actual Arrival Time'].shift(1)

                def calc_act_halt(act_dep, prev_act_arr, leg_num, branch):
                    if leg_num == 1: return "Origin"
                    if pd.isna(act_dep) or pd.isna(prev_act_arr): return f"0:00 at {branch}"
                    dur = (act_dep - prev_act_arr).total_seconds() / 3600
                    if dur < 0: return "Data Error"
                    return f"{format_hrs_safe(dur)} at {branch}"

                df_leg['Actual Halting'] = df_leg.apply(lambda r: calc_act_halt(r['Actual Departure Time'], r['Prev_Act_Arr'], r['Leg_Num'], r['CD_FromBranch']), axis=1)
                
                def calc_status(act, sch, mode):
                    if pd.isna(act): return f"No {mode}" if mode == 'Dep' else "In-Transit"
                    if pd.isna(sch): return "Missing Sch"
                    if (act - sch).total_seconds() / 60 <= 15: return f"Ontime {mode}"
                    return f"Late {mode}"
                    
                df_leg['Dep_Status'] = df_leg.apply(lambda r: calc_status(r['Actual Departure Time'], r['Scheduled Departure Time'], 'Dep'), axis=1)
                df_leg['Arr_Status'] = df_leg.apply(lambda r: calc_status(r['Actual Arrival Time'], r['Scheduled Arrival Time'], 'Arr'), axis=1)
                df_leg['Remark'] = df_leg['Dep_Status'] + ", " + df_leg['Arr_Status']

                trip_bounds = df_leg.groupby('MasterCDNo').agg(
                    Trip_Sch_Dep=('Scheduled Departure Time', 'min'), Trip_Act_Dep=('Actual Departure Time', 'min'),
                    Trip_Sch_Arr=('Scheduled Arrival Time', 'max'), Trip_Act_Arr=('Actual Arrival Time', 'max')
                ).reset_index()

                df_leg = df_leg.merge(trip_bounds, on='MasterCDNo', how='left')
                df_leg['Act_E2E_Hrs'] = (df_leg['Trip_Act_Arr'] - df_leg['Trip_Act_Dep']).dt.total_seconds() / 3600
                df_leg['Actual TAT Till Destination'] = df_leg['Act_E2E_Hrs'].apply(format_hrs_safe)
                df_leg['Overall Remark'] = df_leg.apply(lambda r: calc_status(r['Trip_Act_Dep'], r['Trip_Sch_Dep'], 'Dep') + ", " + calc_status(r['Trip_Act_Arr'], r['Trip_Sch_Arr'], 'Arr'), axis=1)

                # --- MODULE 3: ROUTE SUMMARIES ---
                def generate_summary(df_group, group_cols, summary_type):
                    df_valid = df_group.copy()
                    target_col = 'Overall Remark' if summary_type == 'Overall' else 'Remark'
                    trip_col = 'Total_Trips'
                    
                    df_valid['OO_Cnt'] = df_valid[target_col].apply(lambda x: 1 if 'Ontime Dep, Ontime Arr' in str(x) else 0)
                    df_valid['LO_Cnt'] = df_valid[target_col].apply(lambda x: 1 if 'Late Dep, Ontime Arr' in str(x) else 0)
                    df_valid['OL_Cnt'] = df_valid[target_col].apply(lambda x: 1 if 'Ontime Dep, Late Arr' in str(x) else 0)
                    df_valid['LL_Cnt'] = df_valid[target_col].apply(lambda x: 1 if 'Late Dep, Late Arr' in str(x) else 0)
                    df_valid['Ontime_Dep_IT_Cnt'] = df_valid[target_col].apply(lambda x: 1 if 'Ontime Dep, In-Transit' in str(x) else 0)
                    df_valid['Late_Dep_IT_Cnt'] = df_valid[target_col].apply(lambda x: 1 if 'Late Dep, In-Transit' in str(x) else 0)

                    agg_dict = {'MasterCDNo': 'count', 'OO_Cnt': 'sum', 'LO_Cnt': 'sum', 'OL_Cnt': 'sum', 'LL_Cnt': 'sum', 'Ontime_Dep_IT_Cnt': 'sum', 'Late_Dep_IT_Cnt': 'sum'}
                    if summary_type == 'Overall': agg_dict['Scheduled TAT Till Destination'] = 'first'
                    else:
                        agg_dict['Sch_Dep_Time_Raw'] = 'first'
                        agg_dict['Sch_Arr_Time_Raw'] = 'first'
                        agg_dict['Given Driving Hours'] = 'first'
                    
                    summary = df_valid.groupby(group_cols).agg(agg_dict).reset_index()
                    summary.rename(columns={'MasterCDNo': trip_col}, inplace=True)
                    
                    summary['Ontime Dep, Ontime Arr %'] = summary.apply(lambda r: format_pct_cnt(r['OO_Cnt'], r[trip_col]), axis=1)
                    summary['Late Dep, Late Arr %'] = summary.apply(lambda r: format_pct_cnt(r['LL_Cnt'], r[trip_col]), axis=1)
                    summary['Late Dep, Ontime Arr %'] = summary.apply(lambda r: format_pct_cnt(r['LO_Cnt'], r[trip_col]), axis=1)
                    summary['Ontime Dep, Late Arr %'] = summary.apply(lambda r: format_pct_cnt(r['OL_Cnt'], r[trip_col]), axis=1)
                    summary['Ontime Dep, In-Transit'] = summary.apply(lambda r: format_pct_cnt(r['Ontime_Dep_IT_Cnt'], r[trip_col]), axis=1)
                    summary['Late Dep, In-Transit'] = summary.apply(lambda r: format_pct_cnt(r['Late_Dep_IT_Cnt'], r[trip_col]), axis=1)
                    
                    def get_insight(row):
                        total = row[trip_col]
                        if total == 0: return "No Data"
                        oo_pct = row['OO_Cnt']/total
                        ll_pct = row['LL_Cnt']/total
                        ol_pct = row['OL_Cnt']/total
                        lo_pct = row['LO_Cnt']/total
                        arr_total = row['OO_Cnt'] + row['LO_Cnt'] + row['OL_Cnt'] + row['LL_Cnt']
                        
                        if arr_total == 0: return "Currently Running / In-Transit"
                        if oo_pct >= 0.80: return "Smooth Operations - Excellent TAT"
                        elif ll_pct >= 0.40: return "Critical Lag - Fails at Route & Origin"
                        elif ol_pct >= 0.30: return "Transit Delay - Route Lag"
                        elif lo_pct >= 0.30: return "Origin Delay - Covered in Transit"
                        elif (ol_pct + ll_pct) >= 0.50: return "High Arrival Failures"
                        else: return "Mixed Performance - Monitor"
                        
                    summary['Operations Insight'] = summary.apply(get_insight, axis=1)
                    
                    if summary_type == 'Overall':
                        final_cols = ['Region', 'Origin RO', 'Route Path', 'Scheduled TAT Till Destination', trip_col, 'Ontime Dep, Ontime Arr %', 'Late Dep, Late Arr %', 'Late Dep, Ontime Arr %', 'Ontime Dep, Late Arr %', 'Operations Insight', 'Ontime Dep, In-Transit', 'Late Dep, In-Transit', 'LH Type', 'Origin', 'Destination']
                    else:
                        summary['Scheduled Dep (HH:MM)'] = summary['Sch_Dep_Time_Raw'].apply(format_hhmm)
                        summary['Scheduled Arr (HH:MM)'] = summary['Sch_Arr_Time_Raw'].apply(format_hhmm)
                        final_cols = ['Region', 'Origin RO', 'Route Path', 'Legwise', 'Legs', trip_col, 'Ontime Dep, Ontime Arr %', 'Late Dep, Late Arr %', 'Late Dep, Ontime Arr %', 'Ontime Dep, Late Arr %', 'Operations Insight', 'Ontime Dep, In-Transit', 'Late Dep, In-Transit', 'LH Type', 'Origin', 'Destination', 'Scheduled Dep (HH:MM)', 'Given Driving Hours', 'Scheduled Arr (HH:MM)']
                        
                    sort_cols = ['LH Type', 'E2E_Pair', 'Origin', 'Route Path'] if summary_type == 'Overall' else ['LH Type', 'E2E_Pair', 'Origin', 'Route Path', 'Leg_Num']
                    return summary.sort_values(by=sort_cols)[final_cols]

                df_trip_unique = df_leg.drop_duplicates(subset=['MasterCDNo']).copy()
                overall_sum = generate_summary(df_trip_unique, ['Region', 'LH Type', 'E2E_Pair', 'Origin RO', 'Route Path', 'Origin', 'Destination'], 'Overall')
                leg_sum = generate_summary(df_leg, ['Region', 'LH Type', 'E2E_Pair', 'Origin RO', 'Route Path', 'Origin', 'Destination', 'Leg_Num', 'Legwise', 'Legs'], 'Legwise')

                dt_cols = ['Scheduled Departure Time', 'Actual Departure Time', 'Scheduled Arrival Time', 'Actual Arrival Time']
                for c in dt_cols: df_leg[c] = df_leg[c].dt.strftime('%d-%m-%Y %H:%M').fillna('')
                df_leg['MCD_StartDate'] = pd.to_datetime(df_leg['MCD_StartDate_DT']).dt.strftime('%d-%m-%Y')
                df_leg['MCD_EndDate'] = pd.to_datetime(df_leg['MCD_EndDate'], dayfirst=True, errors='coerce').dt.strftime('%d-%m-%Y').fillna('')

                final_pq_cols = ['Region', 'Origin RO', 'Route Path', 'MCD_StartDate', 'Leg_Num', 'Legwise', 'Legs', 
                                 'Scheduled Departure Time', 'Actual Departure Time', 'Scheduled Arrival Time', 'Remark', 
                                 'Actual Arrival Time', 'Scheduled Halting', 'Actual Halting', 'Scheduled TAT Till Destination', 
                                 'Actual TAT Till Destination', 'Overall Remark', 'MasterCDNo', 'VendorName', 
                                 'RouteCode', 'VehicleNo', 'MCD_EndDate', 'LH Type', 'Origin', 'Destination', 'E2E_Pair']

                df_leg_final = df_leg[final_pq_cols].sort_values(by=['LH Type', 'E2E_Pair', 'Origin', 'Route Path', 'MCD_StartDate', 'Leg_Num'])
                df_leg_final.drop(columns=['Leg_Num', 'E2E_Pair'], inplace=True) 

                df_leg['Late Dep'] = df_leg['Remark'].str.contains('Late Dep', case=False, na=False).astype(int)
                df_leg['Late Arr'] = df_leg['Remark'].str.contains('Late Arr', case=False, na=False).astype(int)
                df_leg['Missing'] = df_leg['Remark'].str.contains('No Dep|Missing', case=False, na=False, regex=True).astype(int)

                exec_sum = df_leg.groupby(['Region', 'LH Type', 'E2E_Pair', 'Origin RO', 'Route Path', 'Leg_Num', 'Legwise', 'Legs']).agg(
                    Trips=('MasterCDNo', 'count'), LDep=('Late Dep', 'sum'), LArr=('Late Arr', 'sum'), Miss=('Missing', 'sum')
                ).reset_index()

                def set_stat(r):
                    if r['LDep'] > 0 and r['LArr'] > 0: return "Critical: Late Dep & Arr"
                    elif r['LDep'] > 0: return "Critical: Late Departure"
                    elif r['LArr'] > 0: return "Warning: Late Arrival"
                    elif r['Miss'] > 0: return "Alert: Missing Data / No Dep"
                    return "OK"
                    
                exec_sum['Status'] = exec_sum.apply(set_stat, axis=1)
                exec_notes = exec_sum[exec_sum['Status'] != "OK"].copy()

                def mk_note(r):
                    msg = f"Total {r['Trips']} trips. "
                    if r['LDep']>0: msg += f"{r['LDep']} Late Dep. "
                    if r['LArr']>0: msg += f"{r['LArr']} Late Arr. "
                    if r['Miss']>0: msg += f"{r['Miss']} Missing/No Dep."
                    return msg.strip()
                    
                exec_notes['Actionable Note'] = exec_notes.apply(mk_note, axis=1)
                exec_notes['Action'] = "[ Review Details ]"
                exec_notes.sort_values(by=['LH Type', 'E2E_Pair', 'Route Path', 'Leg_Num'], inplace=True)
                exec_notes = exec_notes[['Region', 'Origin RO', 'Route Path', 'Legwise', 'Legs', 'Status', 'Actionable Note', 'Action']]

                # --- MODULE 4: MONTHLY MCD VENDOR MONITORING ---
                df_mcd = pd.read_excel(mcd_file)
                df_mcd.columns = df_mcd.columns.astype(str).str.strip().str.upper().str.replace(" ", "").str.replace("_", "")
                
                def find_col(possible_names):
                    for col in df_mcd.columns:
                        if any(p in col for p in possible_names):
                            val = df_mcd[col]
                            if isinstance(val, pd.DataFrame): val = val.iloc[:, 0]
                            return val.fillna('').astype(str).str.strip().str.upper()
                    return pd.Series([''] * len(df_mcd))

                clean_df = pd.DataFrame()
                clean_df['RO'] = find_col(["MCDFROMRO", "FROMRO"])
                clean_df['Route'] = find_col(["ROUTE"])
                clean_df['Vehicle No'] = find_col(["VEHICLENO"])
                clean_df['Vehicle Type'] = find_col(["VEHICLETYPE", "VEHTYPE"])
                clean_df['Vendor Name'] = find_col(["VENDORNAME"])
                clean_df['LH Type'] = find_col(["LHTYPE"])
                clean_df['Replace Vehicle No'] = find_col(["REPLACEVEHICLENO", "REPLACEVEHICLE"])

                df_rep = clean_df[clean_df['Vehicle Type'] == 'REPLACEMENT']
                df_rep = df_rep[df_rep['Replace Vehicle No'] != '']
                if not df_rep.empty:
                    rep_summary = df_rep.groupby(['RO', 'Route', 'Vehicle No', 'Replace Vehicle No']).size().reset_index(name='Replacement Count')
                    rep_summary = rep_summary.sort_values(by='Replacement Count', ascending=False)
                else:
                    rep_summary = pd.DataFrame(columns=['RO', 'Route', 'Vehicle No', 'Replace Vehicle No', 'Replacement Count'])
                    
                ven_grp = clean_df.groupby(['RO', 'LH Type', 'Vehicle No']).agg(
                    Total_MCD_Count=('Vehicle No', 'count'),
                    Unique_Vendor_Count=('Vendor Name', 'nunique'),
                    Vendors=('Vendor Name', lambda x: list(set([v for v in x if v and v != 'NAN' and v != ''])))
                ).reset_index()
                ven_grp = ven_grp.sort_values(by=['Unique_Vendor_Count', 'Total_MCD_Count'], ascending=[False, False])
                
                if not ven_grp.empty:
                    max_v = ven_grp['Vendors'].apply(len).max()
                    if max_v > 0:
                        ops_expanded = pd.DataFrame(ven_grp['Vendors'].to_list(), index=ven_grp.index)
                        ops_expanded = ops_expanded.iloc[:, :max_v] 
                        ops_expanded.columns = [f"Vendor {i+1}" for i in range(ops_expanded.shape[1])]
                        ven_final = pd.concat([ven_grp.drop(columns=['Vendors']), ops_expanded], axis=1)
                    else:
                        ven_final = ven_grp.drop(columns=['Vendors'])
                else:
                    ven_final = ven_grp.drop(columns=['Vendors'])

                # --- SAVE DATA TO STREAMLIT SERVER MEMORY ---
                dashboard_data = {
                    'pvt_master': pvt_master, 'pvt_cc': pvt_cc, 'pvt_fin': pvt_fin, 'pvt_pay': pvt_pay,
                    'df_master': df_master, 'route_master_df': route_master_df, 'df_leg_final': df_leg_final,
                    'overall_sum': overall_sum, 'leg_sum': leg_sum, 'exec_notes': exec_notes,
                    'rep_summary': rep_summary, 'ven_final': ven_final
                }
                
                with open('server_dashboard_data.pkl', 'wb') as f:
                    pickle.dump(dashboard_data, f)
                    
                data_ready = True
                st.sidebar.success("✅ Files processed successfully.")

elif st.session_state['user_role'] == 'User':
    st.sidebar.info("👀 Viewing Mode.")
    
    if os.path.exists('server_dashboard_data.pkl'):
        with open('server_dashboard_data.pkl', 'rb') as f:
            dashboard_data = pickle.load(f)
            
        pvt_master = dashboard_data['pvt_master']
        pvt_cc = dashboard_data['pvt_cc']
        pvt_fin = dashboard_data['pvt_fin']
        pvt_pay = dashboard_data['pvt_pay']
        df_master = dashboard_data['df_master']
        route_master_df = dashboard_data['route_master_df']
        df_leg_final = dashboard_data['df_leg_final']
        overall_sum = dashboard_data['overall_sum']
        leg_sum = dashboard_data['leg_sum']
        exec_notes = dashboard_data['exec_notes']
        rep_summary = dashboard_data['rep_summary']
        ven_final = dashboard_data['ven_final']
        
        data_ready = True
    else:
        st.sidebar.warning("⚠️ Data has not been uploaded by the Admin yet.")

# ==========================================
# STREAMLIT UI RENDERER (TABS)
# ==========================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Payments", "Route Details", "Route Summary", "Actionable Notes", "Vendor Details", "Live GPS Tracking"])

# TABS 1 TO 5: FILE DATA
if data_ready:
    with tab1:
        st.subheader("Regional Financial Pending Analysis")
        st.dataframe(pvt_master, use_container_width=True)
        col1, col2, col3 = st.columns(3)
        col1.write("**Cost Control Hold**"); col1.dataframe(pvt_cc, use_container_width=True)
        col2.write("**Finance Team Hold**"); col2.dataframe(pvt_fin, use_container_width=True)
        col3.write("**Payment Gateway Hold**"); col3.dataframe(pvt_pay, use_container_width=True)
        st.write("**Complete Transaction Registry**")
        st.dataframe(df_master, use_container_width=True)

    with tab2:
        st.subheader("Route Configuration Master")
        st.dataframe(route_master_df, use_container_width=True)
        st.subheader("Daily Processed Dispatches")
        st.dataframe(df_leg_final, use_container_width=True)

    with tab3:
        st.subheader("Macro Level Route Health")
        st.dataframe(overall_sum.style.applymap(lambda x: "background-color: #D4EFDF; color: #196F3D" if "Smooth" in str(x) else ("background-color: #FADBD8; color: #943126" if "Critical" in str(x) else "")), use_container_width=True)
        st.subheader("Micro Level Operations Summary")
        st.dataframe(leg_sum, use_container_width=True)

    with tab4:
        st.subheader("Actionable Delay Notifications")
        st.dataframe(exec_notes.style.applymap(lambda x: "background-color: #FADBD8; color: #943126" if "Critical" in str(x) else ("background-color: #FCF3CF; color: #9A7D0A" if "Warning" in str(x) else "")), use_container_width=True)

    with tab5:
        st.subheader("Active Vehicle Replacements")
        st.dataframe(rep_summary, use_container_width=True)
        st.subheader("Vendor Deployment Analysis")
        st.dataframe(ven_final, use_container_width=True)

    # Export Logic
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_master.to_excel(writer, sheet_name='Master_Database', index=False)
        route_master_df.to_excel(writer, sheet_name='Route_Master', index=False)
        df_leg_final.to_excel(writer, sheet_name='Legwise_Processed', index=False)
        overall_sum.to_excel(writer, sheet_name='Overall_Summary', index=False)
        leg_sum.to_excel(writer, sheet_name='Legwise_Summary', index=False)
        exec_notes.to_excel(writer, sheet_name='Actionable_Notes', index=False)
        rep_summary.to_excel(writer, sheet_name='Replacement_Report', index=False)
        ven_final.to_excel(writer, sheet_name='Vendor_Analysis', index=False)
    
    st.sidebar.download_button(label="📥 Export Report Data", data=output.getvalue(), file_name="Dashboard_Data.xlsx", mime="application/vnd.ms-excel")
else:
    for t in [tab1, tab2, tab3, tab4, tab5]:
        with t:
            st.info("System is waiting for master data file upload.")

# TAB 6: GPS TRACKING
with tab6:
    st.subheader("Live GPS Tracking")
    
    old_df = st.session_state.get('cached_gps_df', pd.DataFrame())
    last_time = st.session_state.get('last_sync_time', 'Never synced')
    
    if st.button("Fetch Live GPS Data", use_container_width=True):
        fetch_fleet_data.clear()
        st.rerun()

    with st.spinner("⏳ Live tracking data fetch ho raha hai... Isme 1-2 minute lag sakte hain, please wait..."):
        df_gps = fetch_fleet_data()
    
    if df_gps.empty and not old_df.empty:
        df_gps = old_df
        st.warning(f"⚠️ Naya data fetch nahi ho paaya. Showing last known coordinates from {last_time}.")
    
    if not df_gps.empty:
        col1, col2 = st.columns([3, 1])
        sync_time = st.session_state.get('last_sync_time', 'Recently')
        col1.success(f"GPS Data Active. Last Updated: {sync_time}")

        st.info(f"📊 **Total Vehicles:** {len(df_gps)}")
        
        st.markdown("### 🔍 Search Location")
        search_query = st.text_input("Search by 4-digit ID or full number:", placeholder="e.g. 3389")
        
        if search_query:
            sq = str(search_query).strip().lower()
            mask = (df_gps['Vehicle_Code'].astype(str).str.lower().str.contains(sq, na=False) | 
                    df_gps['Full_Number'].astype(str).str.lower().str.contains(sq, na=False))
            result = df_gps[mask]
            
            if not result.empty:
                st.success(f"✅ {len(result)} vehicle(s) found.")
                for index, vehicle in result.iterrows():
                    full_no = vehicle.get('Full_Number', '-')
                    with st.container(border=True):
                        st.markdown(f"### 🚛 Vehicle: {full_no}")
                        c1, c2, c3 = st.columns(3)
                        c1.metric(label="🚦 Status", value=str(vehicle.get('Status', '-')).upper())
                        c2.metric(label="⚡ Speed", value=str(vehicle.get('Speed', '-')))
                        c3.metric(label="🕒 Last Updated", value=str(vehicle.get('Last_Updated', '-')))
                        st.divider()
                        loc = str(vehicle.get('Location', '-'))
                        st.info(f"**🌍 Location:**\n\n{loc}")
                        st.warning(f"**🛣️ Distance remaining:**\n\n{str(vehicle.get('Remaining_KMS', '-'))}")
                        
                        if loc != "-":
                            loc_parts = [p.strip() for p in loc.split(',')]
                            optimized_loc = ", ".join(loc_parts[-3:]) if len(loc_parts) >= 3 else loc
                            safe_location = urllib.parse.quote(optimized_loc)
                            gmaps_url = f"https://www.google.com/maps/dir/?api=1&destination={safe_location}"
                            st.link_button(f"📍 View Route Map for {full_no}", gmaps_url, type="primary", use_container_width=True)
            else:
                st.info(f"ℹ️ Gaadi '{sq}' live list mein nahi hai.")
                
        st.markdown("---")
        st.markdown("### 📋 Active Fleet Log")
        st.dataframe(df_gps, hide_index=True)

    else:
        st.error("⚠️ Background engine fail ho gaya. Kripya retry karein.")
