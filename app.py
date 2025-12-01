import streamlit as st
import pandas as pd
from datetime import datetime
import os
import base64
from sqlalchemy import text

# --- إعدادات التطبيق ---

DEDUCTION_AMOUNT = 15.0
ADMIN_KEY = "jak2831"
IMAGE_PATH = "logo.png"

# --- دالة الاتصال ---

def get_connection():
return st.connection("postgresql", type="sql")

# --- تشغيل الصوت ---

def play_sound(sound_file):
full_path = os.path.join("static", sound_file)
if os.path.exists(full_path):
try:
with open(full_path, "rb") as f:
audio_bytes = f.read()
audio_base64 = base64.b64encode(audio_bytes).decode()
audio_html = f""" <audio autoplay="true"> <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3"> </audio>
"""
st.markdown(audio_html, unsafe_allow_html=True)
except Exception:
pass

# --- تهيئة قاعدة البيانات ---

def init_db():
conn = get_connection()
with conn.session as s:
s.execute(text("""
CREATE TABLE IF NOT EXISTS drivers (
id SERIAL PRIMARY KEY,
driver_id TEXT UNIQUE,
name TEXT,
bike_plate TEXT,
whatsapp TEXT,
notes TEXT,
is_active BOOLEAN,
balance REAL
);
"""))
s.execute(text("""
CREATE TABLE IF NOT EXISTS transactions (
id SERIAL PRIMARY KEY,
driver_name TEXT,
amount REAL,
type TEXT,
timestamp TEXT
);
"""))
s.commit()

# --- إدارة المندوبين ---

def add_driver(driver_id, name, bike_plate, whatsapp, notes, is_active):
conn = get_connection()
try:
with conn.session as s:
s.execute(text("""
INSERT INTO drivers (driver_id, name, bike_plate, whatsapp, notes, is_active, balance)
VALUES (:id, :name, :plate, :wa, :notes, :active, 0.0)
"""), {
"id": driver_id,
"name": name,
"plate": bike_plate,
"wa": whatsapp,
"notes": notes,
"active": is_active
})
s.commit()
for fn in (get_driver_info, search_driver, get_all_drivers_details, get_totals):
try: fn.clear()
except Exception: pass
st.success(f"تمت إضافة المندوب '{name}' بنجاح! 🔔")
play_sound("success.mp3")
except Exception as e:
if "duplicate key value" in str(e).lower() or "unique" in str(e).lower():
st.error("رقم الترقيم (ID) هذا موجود مسبقاً. 🚨")
else:
st.error(f"حدث خطأ أثناء الإضافة: {e}")
play_sound("error.mp3")

def update_driver_details(driver_id, name, bike_plate, whatsapp, notes, is_active):
conn = get_connection()
with conn.session as s:
s.execute(text("""
UPDATE drivers SET name=:name, bike_plate=:plate, whatsapp=:wa, notes=:notes, is_active=:active
WHERE driver_id=:id
"""), {
"name": name,
"plate": bike_plate,
"wa": whatsapp,
"notes": notes,
"active": is_active,
"id": driver_id
})
s.commit()
for fn in (get_driver_info, get_all_drivers_details, get_totals, search_driver):
try: fn.clear()
except Exception: pass
st.success(f"تم تحديث بيانات المندوب {name} بنجاح.")

def update_balance(driver_id, amount, trans_type):
info = get_driver_info(driver_id)
if not info: return 0.0
current_balance = info['balance']
name = info['name']
new_balance = current_balance + amount
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

```
conn = get_connection()
with conn.session as s:
    s.execute(text("UPDATE drivers SET balance=:new_bal WHERE driver_id=:id"), {"new_bal": new_balance, "id": driver_id})
    s.execute(text("""
        INSERT INTO transactions (driver_name, amount, type, timestamp)
        VALUES (:driver_name, :amount, :type, :timestamp)
    """), {
        "driver_name": f"{name} (ID:{driver_id})",
        "amount": amount,
        "type": trans_type,
        "timestamp": timestamp
    })
    s.commit()
for fn in (get_driver_info, search_driver, get_all_drivers_details, get_totals, get_history, get_deliveries_count_per_driver):
    try: fn.clear()
    except Exception: pass
return new_balance
```

# --- دوال جلب البيانات ---

@st.cache_data(ttl=60)
def search_driver(search_term):
conn = get_connection()
pattern = f"%{search_term}%"
sql = "SELECT driver_id, name, balance, is_active FROM drivers WHERE driver_id ILIKE :p OR whatsapp ILIKE :p OR name ILIKE :p ORDER BY name LIMIT 1"
df = conn.query(sql, params={"p": pattern})
if not df.empty:
r = df.iloc[0]
return {"driver_id": r['driver_id'], "name": r['name'], "balance": float(r['balance']) if pd.notna(r['balance']) else 0.0, "is_active": bool(r['is_active'])}
return None

@st.cache_data(ttl=60)
def get_driver_info(driver_id):
conn = get_connection()
sql = "SELECT name, COALESCE(balance,0) as balance, is_active FROM drivers WHERE driver_id=:id"
df = conn.query(sql, params={"id": driver_id})
if not df.empty:
r = df.iloc[0]
return {"name": r['name'], "balance": float(r['balance']), "is_active": bool(r['is_active'])}
return None

@st.cache_data(ttl=60)
def get_deliveries_count_per_driver():
conn = get_connection()
sql = """
SELECT
SUBSTR(driver_name, POSITION(':' IN driver_name)+1, LENGTH(driver_name)-POSITION(':' IN driver_name)-1) AS driver_id,
COUNT(*) AS deliveries_count
FROM transactions
WHERE type='خصم توصيلة'
GROUP BY 1
"""
df = conn.query(sql)
if df.empty: return []
return [{"driver_id": str(row['driver_id']), "عدد التوصيلات": int(row['deliveries_count'])} for _, row in df.iterrows()]

def get_all_drivers_details():
conn = get_connection()
query_drivers = "SELECT driver_id, name as "الاسم", bike_plate as "رقم اللوحة", whatsapp as "واتساب", COALESCE(balance,0) as "الرصيد", is_active as "الحالة", notes as "ملاحظات" FROM drivers"
df = conn.query(query_drivers)
if df.empty:
return pd.DataFrame(columns=['ت','الترقيم','الاسم','رقم اللوحة','واتساب','الرصيد','عدد التوصيلات','الحالة','ملاحظات'])

```
deliveries_list = get_deliveries_count_per_driver()
deliveries_df = pd.DataFrame(deliveries_list) if deliveries_list else pd.DataFrame(columns=['driver_id','عدد التوصيلات'])
df['driver_id'] = df['driver_id'].astype(str)
if not deliveries_df.empty:
    deliveries_df['driver_id'] = deliveries_df['driver_id'].astype(str)
    merged = pd.merge(df, deliveries_df, left_on='driver_id', right_on='driver_id', how='left')
    merged['عدد التوصيلات'] = merged['عدد التوصيلات'].fillna(0).astype(int)
else:
    df['عدد التوصيلات'] = 0
    merged = df
merged['الحالة'] = merged['الحالة'].apply(lambda x: 'مفعل' if x else 'معطل')
merged.insert(0, 'ت', range(1, 1 + len(merged)))
merged.rename(columns={'driver_id': 'الترقيم'}, inplace=True)
cols = ['ت', 'الترقيم', 'الاسم', 'رقم اللوحة', 'واتساب', 'الرصيد', 'عدد التوصيلات', 'الحالة', 'ملاحظات']
for c in cols:
    if c not in merged.columns: merged[c] = ""
return merged[cols]
```

@st.cache_data(ttl=60)
def get_totals():
conn = get_connection()
total_balance = float(conn.query("SELECT COALESCE(SUM(balance),0) FROM drivers").iloc[0,0])
total_charged = float(conn.query("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='شحن رصيد'").iloc[0,0])
total_deducted = abs(float(conn.query("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='خصم توصيلة'").iloc[0,0]))
total_deliveries = int(conn.query("SELECT COUNT(*) FROM transactions WHERE type='خصم توصيلة'").iloc[0,0])
return total_balance, total_charged, total_deducted, total_deliveries

def get_history(driver_id=None):
conn = get_connection()
if driver_id:
sql = "SELECT type as "العملية", amount as "المبلغ", timestamp as "التوقيت" FROM transactions WHERE driver_name LIKE :id_pattern ORDER BY id DESC"
df = conn.query(sql, params={"id_pattern": f"%ID:{driver_id}%"})
else:
sql = "SELECT driver_name as "المندوب", type as "العملية", amount as "المبلغ", timestamp as "التوقيت" FROM transactions ORDER BY id DESC"
df = conn.query(sql)
return df

# --- واجهة المستخدم ---

st.set_page_config(page_title="نظام إدارة التوصيل", layout="wide", page_icon="🚚")
st.title("🚚 نظام رصيد المندوبين")

init_db()

if 'logged_in_driver_id' not in st.session_state: st.session_state['logged_in_driver_id'] = None
if 'admin_mode' not in st.session_state: st.session_state['admin_mode'] = False
if 'search_result_id' not in st.session_state: st.session_state['search_result_id'] = None

if os.path.exists(IMAGE_PATH):
st.sidebar.image(IMAGE_PATH, use_column_width=True)
st.sidebar.header("لوحة التحكم")

if st.session_state['admin_mode']:
st.sidebar.markdown("**وضع المسؤول (ADMIN)**")
menu_options = ["واجهة العمليات (الإدارة)", "إدارة المندوبين (إضافة/تعديل)", "التقارير وسجل العمليات", "إعدادات التطبيق (الشعار)", "الخروج من وضع المسؤول"]
current_menu = st.sidebar.radio("القائمة", menu_options)
if current_menu == "الخروج من وضع المسؤول":
st.session_state['admin_mode'] = False
st.session_state['search_result_id'] = None
st.rerun()
elif st.session_state['logged_in_driver_id']:
driver_id = st.session_state['logged_in_driver_id']
driver_info = get_driver_info(driver_id)
if driver_info:
st.sidebar.markdown(f"**مرحباً، {driver_info['name']}**")
st.sidebar.button("خروج (Logout)", on_click=lambda: st.session_state.update(logged_in_driver_id=None, admin_mode=False, search_result_id=None))
current_menu = "واجهة المندوب"
else:
st.session_state.logged_in_driver_id = None
current_menu = "واجهة المندوب"
else:
current_menu = "واجهة المندوب"
st.sidebar.divider()
with st.sidebar.expander("مدخل المسؤول الإداري"):
admin_key_input = st.text_input("أدخل المفتاح السري", type="password")
if st.button("دخول المسؤول"):
if admin_key_input == ADMIN_KEY:
st.session_state['admin_mode'] = True
st.rerun()
else:
st.error("المفتاح السري غير صحيح.")
