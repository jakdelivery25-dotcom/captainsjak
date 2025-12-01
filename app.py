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
        with open(full_path, "rb") as f:
            audio_bytes = f.read()
        audio_base64 = base64.b64encode(audio_bytes).decode()
        audio_html = f"""
        <audio autoplay="true">
            <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
        </audio>
        """
        st.markdown(audio_html, unsafe_allow_html=True)

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

# --- دوال إدارة المندوبين ---
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
        get_driver_info.clear()
        get_all_drivers_details.clear()
        get_totals.clear()
        st.success(f"تمت إضافة المندوب '{name}' بنجاح! 🔔")
        play_sound("success.mp3")
    except Exception as e:
        if "duplicate key value" in str(e):
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
    get_driver_info.clear()
    get_all_drivers_details.clear()
    get_totals.clear()
    st.success(f"تم تحديث بيانات المندوب {name} بنجاح.")

def update_balance(driver_id, amount, trans_type):
    info = get_driver_info(driver_id)
    if not info: return 0.0
    current_balance = info['balance']
    name = info['name']
    new_balance = current_balance + amount
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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

    get_driver_info.clear()
    get_all_drivers_details.clear()
    get_totals.clear()
    get_history.clear()
    return new_balance

# --- دوال جلب البيانات (آمنة للكاش) ---
@st.cache_data(ttl=60)
def get_driver_info(driver_id):
    conn = get_connection()
    df = conn.query(text("SELECT name, balance, is_active FROM drivers WHERE driver_id=:id"), params={"id": driver_id})
    if not df.empty:
        result = df.iloc[0]
        return {"name": result['name'], "balance": result['balance'], "is_active": result['is_active']}
    return None

@st.cache_data(ttl=60)
def get_all_drivers_details():
    conn = get_connection()
    df = conn.query("SELECT driver_id, name, bike_plate, whatsapp, balance, is_active, notes FROM drivers")
    if df.empty:
        return pd.DataFrame()
    df['الحالة'] = df['is_active'].apply(lambda x: 'مفعل' if x else 'معطل')
    df['ت'] = range(1, len(df)+1)
    df.rename(columns={'driver_id': 'الترقيم', 'name':'الاسم','bike_plate':'رقم اللوحة','whatsapp':'واتساب','balance':'الرصيد','notes':'ملاحظات'}, inplace=True)
    cols = ['ت','الترقيم','الاسم','رقم اللوحة','واتساب','الرصيد','الحالة','ملاحظات']
    return df[cols]

@st.cache_data(ttl=60)
def get_totals():
    conn = get_connection()
    total_balance = conn.query("SELECT COALESCE(SUM(balance),0) FROM drivers").iloc[0,0]
    total_charged = conn.query("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='شحن رصيد'").iloc[0,0]
    total_deducted = abs(conn.query("SELECT COALESCE(SUM(amount),0) FROM transactions WHERE type='خصم توصيلة'").iloc[0,0])
    total_deliveries = conn.query("SELECT COUNT(*) FROM transactions WHERE type='خصم توصيلة'").iloc[0,0]
    return total_balance, total_charged, total_deducted, total_deliveries

@st.cache_data(ttl=60)
def get_history(driver_id=None):
    conn = get_connection()
    if driver_id:
        df = conn.query(text("SELECT type as 'العملية', amount as 'المبلغ', timestamp as 'التوقيت' FROM transactions WHERE driver_name LIKE :id_pattern ORDER BY id DESC"), params={"id_pattern": f"%ID:{driver_id}%"})
    else:
        df = conn.query("SELECT driver_name as 'المندوب', type as 'العملية', amount as 'المبلغ', timestamp as 'التوقيت' FROM transactions ORDER BY id DESC")
    return df

# --- البحث عن مندوب ---
@st.cache_data(ttl=60)
def search_driver(search_term):
    conn = get_connection()
    pattern = f"%{search_term}%"
    df = conn.query(text("SELECT driver_id, name, balance, is_active FROM drivers WHERE driver_id ILIKE :p OR whatsapp ILIKE :p OR name ILIKE :p ORDER BY name LIMIT 1"), params={"p": pattern})
    if not df.empty:
        r = df.iloc[0]
        return {"driver_id": r['driver_id'], "name": r['name'], "balance": r['balance'], "is_active": r['is_active']}
    return None

# --- التهيئة ---
st.set_page_config(page_title="نظام إدارة التوصيل", layout="wide", page_icon="🚚")
st.title("🚚 نظام رصيد المندوبين")
init_db()

# --- حالة الجلسة ---
if 'logged_in_driver_id' not in st.session_state:
    st.session_state['logged_in_driver_id'] = None
if 'admin_mode' not in st.session_state:
    st.session_state['admin_mode'] = False
if 'search_result_id' not in st.session_state:
    st.session_state['search_result_id'] = None
