import streamlit as st
import pandas as pd
from datetime import datetime
import os
import io
from sqlalchemy import text 

# --- إعدادات التطبيق ---
DEDUCTION_AMOUNT = 15.0
ADMIN_KEY = "jak2831"
IMAGE_PATH = "logo.png"

# ----------------------------------------------------

# 🆕 دالة الاتصال الموحدة (بدون كاش)
def get_connection():
    """يُنشئ اتصال Streamlit SQL مع إعدادات secrets."""
    return st.connection("postgresql", type="sql")

# 🆕 دالة مساعدة لتشغيل صوت تنبيه
def play_sound(sound_file):
    """يشغل ملف صوتي باستخدام HTML."""
    full_path = os.path.join("static", sound_file)
    try:
        if os.path.exists(full_path):
            import base64
            with open(full_path, "rb") as f:
                audio_bytes = f.read()
            audio_base64 = base64.b64encode(audio_bytes).decode()
            audio_html = f"""
            <audio autoplay="true">
                <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
            </audio>
            """
            st.markdown(audio_html, unsafe_allow_html=True)
    except Exception:
        pass

# --- دوال التعامل مع قاعدة البيانات ---
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

# 📝 تم التعديل: إضافة مسح الكاش
def add_driver(driver_id, name, bike_plate, whatsapp, notes, is_active):
    conn = get_connection()
    try:
        with conn.session as s:
            sql = text("""
                INSERT INTO drivers (driver_id, name, bike_plate, whatsapp, notes, is_active, balance)
                VALUES (:id, :name, :plate, :wa, :notes, :active, 0.0)
            """)
            s.execute(sql, {
                "id": driver_id,
                "name": name,
                "plate": bike_plate,
                "wa": whatsapp,
                "notes": notes,
                "active": is_active
            })
            s.commit()
        
        # 🆕 مسح الكاش للدوال المتأثرة
        get_all_drivers_details.clear()
        get_totals.clear()
        
        st.success(f"تمت إضافة المندوب '{name}' بنجاح! 🔔")
        play_sound("success.mp3")
    except Exception as e:
        if "duplicate key value violates unique constraint" in str(e):
            st.error("رقم الترقيم (ID) هذا موجود مسبقاً. 🚨")
        else:
            st.error(f"حدث خطأ أثناء الإضافة: {e}")
        play_sound("error.mp3")

# 🛑 الدوال المُعلَّمة: (تم التأكيد على أنها صحيحة)
@st.cache_data(ttl=None) 
def search_driver(search_term):
    conn = get_connection()
    search_pattern = f"%{search_term}%"
    query = text("""
        SELECT driver_id, name, balance, is_active
        FROM drivers
        WHERE driver_id ILIKE :pattern
           OR whatsapp ILIKE :pattern
           OR name ILIKE :pattern
        ORDER BY name
        LIMIT 1
    """)
    df = conn.query(query, params={"pattern": search_pattern})
    
    if not df.empty:
        result = df.iloc[0]
        return {"driver_id": result['driver_id'], "name": result['name'], "balance": result['balance'], "is_active": result['is_active']}
    return None

@st.cache_data(ttl=None)
def get_driver_info(driver_id):
    conn = get_connection()
    query = text("SELECT name, balance, is_active FROM drivers WHERE driver_id = :id")
    df = conn.query(query, params={"id": driver_id})
    
    if not df.empty:
        result = df.iloc[0]
        return {"name": result['name'], "balance": result['balance'], "is_active": result['is_active']}
    return None

# 📝 تم التعديل: إضافة مسح الكاش
def update_driver_details(driver_id, name, bike_plate, whatsapp, notes, is_active):
    conn = get_connection()
    with conn.session as s:
        sql = text("""
            UPDATE drivers SET name=:name, bike_plate=:plate, whatsapp=:wa, notes=:notes, is_active=:active
            WHERE driver_id=:id
        """)
        s.execute(sql, {
            "name": name,
            "plate": bike_plate,
            "wa": whatsapp,
            "notes": notes,
            "active": is_active,
            "id": driver_id
        })
        s.commit()
    # 🆕 مسح الكاش للدوال المتأثرة
    get_driver_info.clear() 
    get_all_drivers_details.clear() 
    st.success(f"تم تحديث بيانات المندوب {name} بنجاح.")

# 📝 تم التعديل: إضافة مسح الكاش الشامل
def update_balance(driver_id, amount, trans_type):
    info = get_driver_info(driver_id)
    if not info: return 0.0
    
    current_balance = info['balance']
    name = info['name']
    new_balance = current_balance + amount
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    with conn.session as s:
        update_sql = text("UPDATE drivers SET balance=:new_bal WHERE driver_id=:id")
        s.execute(update_sql, {"new_bal": new_balance, "id": driver_id})
        
        trans_sql = text("""
            INSERT INTO transactions (driver_name, amount, type, timestamp)
            VALUES (:driver_name, :amount, :type, :timestamp)
        """)
        s.execute(trans_sql, {
            "driver_name": f"{name} (ID:{driver_id})",
            "amount": amount,
            "type": trans_type,
            "timestamp": timestamp
        })
        s.commit()
        
    # 🆕 مسح الكاش الشامل للدوال المتأثرة بالرصيد والحركات
    get_driver_info.clear()
    get_totals.clear()
    get_history.clear()
    get_all_drivers_details.clear()
    
    return new_balance

@st.cache_data(ttl=60)
def get_deliveries_count_per_driver():
    conn = get_connection()
    query = text("""
    SELECT
        SUBSTR(driver_name, POSITION(':' IN driver_name)+1, LENGTH(driver_name)-POSITION(':' IN driver_name)-1) AS driver_id,
        COUNT(*) AS "عدد التوصيلات"
    FROM transactions
    WHERE type='خصم توصيلة'
    GROUP BY
        SUBSTR(driver_name, POSITION(':' IN driver_name)+1, LENGTH(driver_name)-POSITION(':' IN driver_name)-1)
    """)
    df = conn.query(query)
    return df

@st.cache_data(ttl=60)
def get_totals():
    conn = get_connection()
    total_balance = conn.query("SELECT COALESCE(SUM(balance), 0.0) FROM drivers").iloc[0, 0]
    total_charged = conn.query("SELECT COALESCE(SUM(amount), 0.0) FROM transactions WHERE type='شحن رصيد'").iloc[0, 0]
    total_deducted_negative = conn.query("SELECT COALESCE(SUM(amount), 0.0) FROM transactions WHERE type='خصم توصيلة'").iloc[0, 0]
    total_deliveries = conn.query("SELECT COUNT(*) FROM transactions WHERE type='خصم توصيلة'").iloc[0, 0]
    
    total_deducted = abs(total_deducted_negative)
    return total_balance, total_charged, total_deducted, total_deliveries

@st.cache_data(ttl=60)
def get_history(driver_id=None):
    conn = get_connection()
    if driver_id:
        query = text("SELECT type as \"العملية\", amount as \"المبلغ\", timestamp as \"التوقيت\" FROM transactions WHERE driver_name LIKE :id_pattern ORDER BY id DESC")
        df = conn.query(query, params={"id_pattern": f"%ID:{driver_id}%"})
    else:
        query = "SELECT driver_name as \"المندوب\", type as \"العملية\", amount as \"المبلغ\", timestamp as \"التوقيت\" FROM transactions ORDER BY id DESC"
        df = conn.query(query)
    return df

@st.cache_data(ttl=60)
def get_all_drivers_details():
    conn = get_connection()
    query_drivers = "SELECT driver_id, name as \"الاسم\", bike_plate as \"رقم اللوحة\", whatsapp as \"واتساب\", balance as \"الرصيد\", is_active as \"الحالة\", notes as \"ملاحظات\" FROM drivers"
    df = conn.query(query_drivers)
    
    deliveries_count_df = get_deliveries_count_per_driver() 

    if not deliveries_count_df.empty:
        df['driver_id'] = df['driver_id'].astype(str)
        deliveries_count_df['driver_id'] = deliveries_count_df['driver_id'].astype(str)
        df = pd.merge(df, deliveries_count_df, left_on='driver_id', right_on='driver_id', how='left').fillna({'عدد التوصيلات': 0})
        df['عدد التوصيلات'] = df['عدد التوصيلات'].astype(int)
    else:
        df['عدد التوصيلات'] = 0
        
    df['الحالة'] = df['الحالة'].apply(lambda x: 'مفعل' if x else 'معطل')
    df.insert(0, 'ت', range(1, 1 + len(df)))
    df.rename(columns={'driver_id': 'الترقيم'}, inplace=True)
    cols = ['ت', 'الترقيم', 'الاسم', 'رقم اللوحة', 'واتساب', 'الرصيد', 'عدد التوصيلات', 'الحالة', 'ملاحظات']
    return df[cols]


# --- (باقي كود الواجهة كما هو، ويستفيد من الدوال المحدثة) ---
# ... (Interface Code Follows) ...
# (The rest of the code is unchanged as the fix was in the functions)
# ...

# ----------------------------------------------------------------------------------
# 2. واجهة المندوب
# ... (الكود غير متغير)
# ----------------------------------------------------------------------------------
# 3. واجهة العمليات (الإدارة)
# ... (الكود غير متغير)
# ----------------------------------------------------------------------------------
# 4. إدارة المندوبين (إضافة/تعديل)
# ... (الكود غير متغير)
# ----------------------------------------------------------------------------------
# 5. التقارير وسجل العمليات
# ... (الكود غير متغير)
# ----------------------------------------------------------------------------------
# 6. إعدادات التطبيق (الشعار)
# ... (الكود غير متغير)