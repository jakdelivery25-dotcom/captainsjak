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

# 🆕 دالة الاتصال الموحدة
def get_connection():
    """يُنشئ اتصال Streamlit SQL مع إعدادات secrets."""
    return st.connection("postgresql", type="sql")

# 🆕 دالة مساعدة لتشغيل صوت تنبيه
def play_sound(sound_file):
    """يشغل ملف صوتي باستخدام HTML."""
    # هذا الجزء يعتمد على وجود ملفات الصوت في مسار معين (مثل static/success.mp3)
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

# --- دوال التعامل مع قاعدة البيانات (تم تحديثها) ---
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

# 🆕 تم تحديثها لاستخدام المعاملات المسماة (:param_name)
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
        st.success(f"تمت إضافة المندوب '{name}' بنجاح! 🔔")
        play_sound("success.mp3") 
    except Exception as e:
        if "duplicate key value violates unique constraint" in str(e):
             st.error("رقم الترقيم (ID) هذا موجود مسبقاً. 🚨")
        else:
             st.error(f"حدث خطأ أثناء الإضافة: {e}")
        play_sound("error.mp3") 

# 🛑 تم تعديل هذه الدالة: 
# 1. إضافة @st.cache_data(ttl=None) لحل مشكلة UnhashableParamError.
# 2. تحسين البحث ليشمل الاسم والبحث الجزئي (ILIKE).
@st.cache_data(ttl=None) 
def search_driver(search_term):
    """البحث عن مندوب بواسطة driver_id أو whatsapp أو الاسم باستخدام البحث الجزئي"""
    conn = get_connection()
    
    # تحضير مصطلح البحث للبحث الجزئي باستخدام ILIKE
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
     
    # إزالة ttl="0" والاعتماد على @st.cache_data(ttl=None)
    df = conn.query(query, params={"pattern": search_pattern})
    
    if not df.empty:
        result = df.iloc[0]
        return {"driver_id": result['driver_id'], "name": result['name'], "balance": result['balance'], "is_active": result['is_active']}
    return None

# 🛑 تم تعديل هذه الدالة:
# 1. إضافة @st.cache_data(ttl=None) لحل مشكلة UnhashableParamError.
@st.cache_data(ttl=None) 
def get_driver_info(driver_id):
    conn = get_connection()
    query = text("SELECT name, balance, is_active FROM drivers WHERE driver_id = :id")
    # إزالة ttl="0" والاعتماد على @st.cache_data(ttl=None)
    df = conn.query(query, params={"id": driver_id}) 
    
    if not df.empty:
        result = df.iloc[0]
        return {"name": result['name'], "balance": result['balance'], "is_active": result['is_active']} 
    return None

# 🆕 تم تحديثها لاستخدام conn.session
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
    st.success(f"تم تحديث بيانات المندوب {name} بنجاح.")

# 🆕 تم تحديثها لاستخدام conn.session وتنفيذ عمليتي كتابة متتاليتين
def update_balance(driver_id, amount, trans_type):
    conn = get_connection()
    # يجب إزالة أي caching هنا لضمان الحصول على أحدث رصيد
    # يتم تجاوز الكاش هنا عن طريق استدعاء get_driver_info بدون وسيط الترقيم
    info = get_driver_info(driver_id)
    if not info: return 0.0
    
    current_balance = info['balance']
    name = info['name']
    new_balance = current_balance + amount
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with conn.session as s:
        # 1. تحديث الرصيد
        update_sql = text("UPDATE drivers SET balance=:new_bal WHERE driver_id=:id")
        s.execute(update_sql, {"new_bal": new_balance, "id": driver_id})
        
        # 2. تسجيل المعاملة
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
    return new_balance

def get_deliveries_count_per_driver():
    conn = get_connection()
    query = """
    SELECT 
        SUBSTR(driver_name, POSITION(':' IN driver_name)+1, LENGTH(driver_name)-POSITION(':' IN driver_name)-1) AS driver_id, 
        COUNT(*) AS "عدد التوصيلات"
    FROM transactions
    WHERE type='خصم توصيلة'
    GROUP BY driver_id
    """
    df = conn.query(query, ttl="0")
    return df

def get_totals():
    conn = get_connection()
    
    # استخدام conn.query مع ttl=0 للحصول على أحدث نتيجة كـ DataFrame ثم استخراج القيمة
    total_balance = conn.query("SELECT COALESCE(SUM(balance), 0.0) FROM drivers", ttl="0").iloc[0, 0]
    total_charged = conn.query("SELECT COALESCE(SUM(amount), 0.0) FROM transactions WHERE type='شحن رصيد'", ttl="0").iloc[0, 0]
    total_deducted_negative = conn.query("SELECT COALESCE(SUM(amount), 0.0) FROM transactions WHERE type='خصم توصيلة'", ttl="0").iloc[0, 0]
    total_deliveries = conn.query("SELECT COUNT(*) FROM transactions WHERE type='خصم توصيلة'", ttl="0").iloc[0, 0]
    
    total_deducted = abs(total_deducted_negative)
    return total_balance, total_charged, total_deducted, total_deliveries

def get_history(driver_id=None):
    conn = get_connection()
    if driver_id:
        # استخدام المعاملات المسماة للاستعلامات المعقدة
        query = text(f"SELECT type as \"العملية\", amount as \"المبلغ\", timestamp as \"التوقيت\" FROM transactions WHERE driver_name LIKE '%ID:{driver_id}%' ORDER BY id DESC")
        # يجب إزالة ttl="0" والاعتماد على @st.cache_data(ttl=None) لو أضفنا الـ Decorator على هذه الدالة
        df = conn.query(query, ttl="0")
    else:
        query = "SELECT driver_name as \"المندوب\", type as \"العملية\", amount as \"المبلغ\", timestamp as \"التوقيت\" FROM transactions ORDER BY id DESC"
        df = conn.query(query, ttl="0")
    return df

def get_all_drivers_details():
    conn = get_connection()
    # الاستعلام الأساسي لجلب كل السائقين
    query_drivers = "SELECT driver_id, name as \"الاسم\", bike_plate as \"رقم اللوحة\", whatsapp as \"واتساب\", balance as \"الرصيد\", is_active as \"الحالة\", notes as \"ملاحظات\" FROM drivers"
    df = conn.query(query_drivers, ttl="0")
    
    deliveries_count_df = get_deliveries_count_per_driver()
    
    if not deliveries_count_df.empty:
        df['driver_id'] = df['driver_id'].astype(str)
        deliveries_count_df['driver_id'] = deliveries_count_df['driver_id'].astype(str)
        df = pd.merge(df, deliveries_count_df, left_on='driver_id', right_on='driver_id', how='left').fillna({'عدد التوصيلات': 0})
        df['عدد التوصيلات'] = df['عدد التوصيلات'].astype(int)
    else:
        df['عدد التوصيلات'] = 0
        
    df['الحالة'] = df['الحالة'].apply(lambda x: 'مفعل' if x else 'معطل') # تم التعديل إلى if x ليتناسب مع True/False
    df.insert(0, 'ت', range(1, 1 + len(df)))
    df.rename(columns={'driver_id': 'الترقيم'}, inplace=True)
    cols = ['ت', 'الترقيم', 'الاسم', 'رقم اللوحة', 'واتساب', 'الرصيد', 'عدد التوصيلات', 'الحالة', 'ملاحظات']
    return df[cols]

# --- واجهة التطبيق ---
st.set_page_config(page_title="نظام إدارة التوصيل", layout="wide", page_icon="🚚")
st.title("🚚 نظام رصيد المندوبين")

# التأكد من وجود قاعدة البيانات (إنشاء الجداول في PostgreSQL)
init_db()

# تهيئة حالة الجلسة
if 'logged_in_driver_id' not in st.session_state:
    st.session_state['logged_in_driver_id'] = None
if 'admin_mode' not in st.session_state:
    st.session_state['admin_mode'] = False
if 'search_result_id' not in st.session_state:
    st.session_state['search_result_id'] = None

# ----------------------------------------------------------------------------------
# 1. منطق القائمة الجانبية (لم يتغير)
# ----------------------------------------------------------------------------------

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
    # استدعاء get_driver_info يعمل بشكل صحيح الآن
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

# ----------------------------------------------------------------------------------
# 2. واجهة المندوب (لم تتغير)
# ----------------------------------------------------------------------------------
if current_menu == "واجهة المندوب":
    if st.session_state['logged_in_driver_id']:
        driver_id = st.session_state['logged_in_driver_id']
        driver_data = get_driver_info(driver_id)
        
        if driver_data:
            st.header(f"أهلاً بك يا {driver_data['name']}!")
            
            is_active = driver_data['is_active']
            status_text = "🟢 مفعل" if is_active else "🔴 معطل"
            status_color = "green" if is_active else "red"
            st.markdown(f"**حالة حسابك:** <span style='color:{status_color}; font-size: 1.5em;'>{status_text}</span>", unsafe_allow_html=True)
            
            if is_active:
                st.markdown("### رصيدك الحالي")
                st.metric(label="الرصيد المتوفر", value=f"{driver_data['balance']:.2f} أوقية", delta_color="off")
                st.divider()
                st.markdown("### سجل حركاتك الأخيرة")
                history_df = get_history(driver_id)
                if not history_df.empty:
                    st.dataframe(history_df, use_container_width=True)
                else:
                    st.info("لا توجد حركات مسجلة لك بعد.")
            else:
                st.error("عفواً، حسابك معطل. لا يمكنك إجراء أي عمليات. يرجى مراجعة الإدارة.")
                
        else:
            st.error("حدث خطأ في جلب البيانات.")
            st.session_state['logged_in_driver_id'] = None
            st.rerun()
    
    else:
        st.header("تسجيل الدخول للمندوبين")
        driver_id_input = st.text_input("أدخل ترقيمك (Driver ID)")
        
        def attempt_login():
            if not driver_id_input:
                st.error("الرجاء إدخال ترقيمك.")
                return
            
            info = get_driver_info(driver_id_input)
            if info:
                st.session_state['logged_in_driver_id'] = driver_id_input
                st.success(f"تم تسجيل الدخول بنجاح! مرحباً بك يا {info['name']}.")
                st.rerun()
            else:
                st.error("ترقيم المندوب غير صحيح.")

        st.button("تسجيل الدخول", on_click=attempt_login, type="primary")

# ----------------------------------------------------------------------------------
# 3. واجهة العمليات (الإدارة) (لم تتغير)
# ----------------------------------------------------------------------------------
elif current_menu == "واجهة العمليات (الإدارة)":
    st.header("تسجيل العمليات (شحن/خصم)")
    
    st.subheader("1. تحديد المندوب")
    
    col_search, col_button = st.columns([3, 1])
    with col_search:
        search_term_op = st.text_input("ابحث بالترقيم (ID) أو رقم الواتساب أو الاسم", key="search_op_input")
    with col_button:
        if st.button("بحث وتحديد", key="search_op_btn", type="primary"):
            # search_driver يعمل الآن بالبحث الشامل
            driver_data = search_driver(search_term_op)
            if driver_data:
                st.session_state['search_result_id'] = driver_data['driver_id']
                st.success(f"تم تحديد المندوب: {driver_data['name']}")
            else:
                st.error("لم يتم العثور على المندوب بالترقيم أو رقم الواتساب أو الاسم المدخل.")
                st.session_state['search_result_id'] = None
    
    selected_id = st.session_state['search_result_id']
    
    if selected_id:
        info = get_driver_info(selected_id)
        # قد يكون info فارغاً إذا تم حذفه
        if info:
            st.subheader(f"2. تفاصيل ورصيد المندوب: {info['name']}")
            balance = info['balance']
            is_active = info['is_active']
            
            status_text = "🟢 مفعل" if is_active else "🔴 معطل"
            status_color = "green" if is_active else "red"
            
            st.markdown(f"**الرصيد الحالي:** **<span style='color:green; font-size: 1.5em;'>{balance:.2f} أوقية</span>** | **الحالة:** <span style='color:{status_color}; font-size: 1.2em;'>{status_text}</span>", unsafe_allow_html=True)
            st.divider()
            
            if not is_active:
                 st.warning("تنبيه: هذا المندوب **معطل** ولا يمكنه إجراء عمليات توصيل حتى يتم تفعيله من قائمة الإدارة.")
  
            tab1, tab2 = st.tabs(["✅ إتمام توصيلة", "💰 شحن رصيد"])
            
            with tab1:
                st.markdown(f"سيتم خصم **{DEDUCTION_AMOUNT} أوقية** من الرصيد.")
                if st.button("تسجيل توصيلة ناجحة", key="deduct_button", type="primary", disabled=not is_active):
                    if balance >= DEDUCTION_AMOUNT:
                        new_bal = update_balance(selected_id, -DEDUCTION_AMOUNT, "خصم توصيلة")
                        st.success(f"تم تسجيل التوصيلة! الرصيد المتبقي: {new_bal:.2f} أوقية 🔔")
                        play_sound("success.mp3") 
                        st.session_state['search_result_id'] = None 
                        st.rerun()
                    else:
                        st.error("عفواً، الرصيد غير كافي لإجراء التوصيلة. يرجى الشحن أولاً. 🚨")
                        play_sound("error.mp3") 
            
            with tab2:
                amount_to_add = st.number_input("المبلغ المراد شحنه (أوقية)", min_value=-99999.0, step=10.0, key="charge_amount")
                if st.button("تأكيد الشحن", key="charge_button"):
                    new_bal = update_balance(selected_id, amount_to_add, "شحن رصيد")
                    st.success(f"تم الشحن بنجاح! الرصيد الجديد: {new_bal:.2f} أوقية 🔔")
                    play_sound("success.mp3") 
                    st.session_state['search_result_id'] = None 
                    st.rerun()
        else:
            st.error("لم يتم العثور على بيانات المندوب المحدد.")
    else:
        st.info("يرجى البحث عن المندوب باستخدام ترقيمه أو رقم الواتساب أو الاسم لتسجيل عملية.")

# ----------------------------------------------------------------------------------
# 4. إدارة المندوبين (إضافة/تعديل) 
# ----------------------------------------------------------------------------------
elif current_menu == "إدارة المندوبين (إضافة/تعديل)":
    st.header("إدارة بيانات المندوبين")
    tab_add, tab_edit, tab_view = st.tabs(["إضافة مندوب", "تعديل بيانات", "عرض الكل"])
    
    with tab_add:
        st.subheader("تسجيل مندوب جديد")
        with st.form("new_driver_form"):
            col1_add, col2_add = st.columns(2)
            with col1_add:
                new_driver_id = st.text_input("ترقيم المندوب (ID)", help="يجب أن يكون رقماً فريداً أو كوداً مميزاً")
                new_name = st.text_input("اسم المندوب الكامل")
                new_bike_plate = st.text_input("رقم لوحة الدراجة")
            with col2_add:
                new_whatsapp = st.text_input("رقم الواتساب (للتواصل)")
                new_notes = st.text_area("ملاحظات إضافية")
                new_is_active = st.checkbox("حساب مفعل؟", value=True, help="عطّل هذا الخيار لمنع المندوب من إجراء عمليات توصيل أو شحن.")
            
            submitted = st.form_submit_button("إضافة المندوب", type="primary")
            if submitted:
                if new_driver_id and new_name:
                    add_driver(new_driver_id, new_name, new_bike_plate, new_whatsapp, new_notes, new_is_active) 
                    st.rerun()
                else:
                    st.error("يرجى إدخال ترقيم المندوب والاسم على الأقل.")

    with tab_edit:
        st.subheader("تعديل بيانات مندوب حالي")
        
        col_search_edit, col_button_edit = st.columns([3, 1])
        with col_search_edit:
            search_term_edit = st.text_input("ابحث بالترقيم (ID) أو رقم الواتساب أو الاسم للتعديل", key="search_edit_input")
        with col_button_edit:
            if st.button("بحث وتحديد", key="search_edit_btn", type="primary"):
                # search_driver يعمل الآن بشكل صحيح مع Caching والبحث الشامل
                driver_data = search_driver(search_term_edit) 
                if driver_data:
                    st.session_state['search_result_id'] = driver_data['driver_id']
                    st.success(f"تم تحديد المندوب: {driver_data['name']}. يمكنك الآن التعديل.")
                else:
                    st.error("لم يتم العثور على المندوب.")
                    st.session_state['search_result_id'] = None
        
        selected_id = st.session_state['search_result_id']
        
        if selected_id:
            conn = get_connection()
            # استخدام query لجلب البيانات (مع تعديل get_driver_info لتجنب الخطأ)
            query = text("SELECT name, bike_plate, whatsapp, notes, is_active FROM drivers WHERE driver_id=:id")
            # استخدام query مباشرة هنا لا يسبب خطأ Unhashable لأن params هو قاموس بسيط
            info_df = conn.query(query, params={"id": selected_id}, ttl="0") 
            
            if not info_df.empty:
                info_db = info_df.iloc[0].tolist()
                current_name = info_db[0]
                st.markdown(f"**بيانات المندوب الحالي: {current_name}**")
                
                with st.form("edit_driver_form"):
                    col1_edit, col2_edit = st.columns(2)
                    with col1_edit:
                        edit_name = st.text_input("الاسم", value=current_name if current_name is not None else "")
                        edit_bike_plate = st.text_input("رقم لوحة الدراجة", value=info_db[1] if info_db[1] else "")
                        edit_whatsapp = st.text_input("رقم الواتساب", value=info_db[2] if info_db[2] else "")
                    with col2_edit:
                        edit_notes = st.text_area("ملاحظات إضافية", value=info_db[3] if info_db[3] else "")
                        edit_is_active = st.checkbox("حساب مفعل؟", value=info_db[4] if info_db[4] is not None else False, help="عطّل لمنع إجراء أي عمليات.")
                    
                    submitted_edit = st.form_submit_button("حفظ التعديلات", type="primary")
                    if submitted_edit:
                        update_driver_details(selected_id, edit_name, edit_bike_plate, edit_whatsapp, edit_notes, edit_is_active)
                        # clear cache for driver info to fetch updated data immediately
                        get_driver_info.clear() 
                        st.session_state['search_result_id'] = None 
                        st.rerun()
            else:
                st.error("حدث خطأ في جلب بيانات المندوب للتعديل.")
        else:
            st.info("يرجى استخدام شريط البحث أعلاه لتحديد المندوب المراد تعديله.")

    with tab_view:
        st.subheader("عرض بيانات جميع المندوبين")
        all_details = get_all_drivers_details()
        if not all_details.empty:
            st.dataframe(all_details, use_container_width=True)
        else:
            st.info("لا توجد بيانات لعرضها.")

# ----------------------------------------------------------------------------------
# 5. التقارير وسجل العمليات (لم يتغير)
# ----------------------------------------------------------------------------------
elif current_menu == "التقارير وسجل العمليات":
    st.header("سجل الحركات المالية والتقارير")
    
    report_type = st.radio("نوع التقرير", ["التقارير الإجمالية", "سجل جميع العمليات", "سجل مندوب معين"], horizontal=True)
    
    if report_type == "التقارير الإجمالية":
        st.subheader("ملخص إجمالي للنظام")
        total_balance, total_charged, total_deducted, total_deliveries = get_totals()
        
        col_total_bal, col_total_charged, col_total_deducted, col_total_deliveries = st.columns(4)
        
        with col_total_bal:
            st.metric(label="مجموع الأرصدة الحالية للمندوبين", value=f"{total_balance:.2f} أوقية", delta_color="off")
            st.caption("مجموع الرصيد الحالي الموجود في حسابات جميع المندوبين.")
        
        with col_total_charged:
            st.metric(label="إجمالي المبالغ المشحونة", value=f"{total_charged:.2f} أوقية", delta_color="off")
            st.caption("مجموع كل عمليات الشحن التي تمت منذ بدء النظام.")
        
        with col_total_deducted:
            st.metric(label="إجمالي المبالغ المخصومة", value=f"{total_deducted:.2f} أوقية", delta_color="off")
            st.caption("مجموع الخصومات التي تمت لتسجيل التوصيلات.")

        with col_total_deliveries:
            st.metric(label="عدد التوصيلات الإجمالي", value=f"{total_deliveries}", delta_color="off")
            st.caption("مجموع عدد التوصيلات الناجحة المسجلة في النظام.")
        
    elif report_type == "سجل جميع العمليات":
        st.subheader("جميع حركات الشحن والخصم")
        df = get_history(driver_id=None)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="تحميل السجل كملف CSV",
                data=csv,
                file_name=f"سجل_العمليات_الكامل_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("لا توجد حركات مسجلة بعد.")
            
    elif report_type == "سجل مندوب معين":
        st.subheader("البحث وعرض سجل مندوب محدد")
        
        col_search_hist, col_button_hist = st.columns([3, 1])
        with col_search_hist:
            search_term_hist = st.text_input("ابحث بالترقيم (ID) أو رقم الواتساب أو الاسم", key="search_hist_input")
        with col_button_hist:
            if st.button("بحث وعرض السجل", key="search_hist_btn", type="primary"):
                # search_driver يعمل الآن بالبحث الشامل
                driver_data = search_driver(search_term_hist)
                if driver_data:
                    st.session_state['search_result_id'] = driver_data['driver_id']
                    st.success(f"تم تحديد المندوب: {driver_data['name']}")
                else:
                    st.error("لم يتم العثور على المندوب.")
                    st.session_state['search_result_id'] = None
        
        selected_id = st.session_state['search_result_id']
        
        if selected_id:
            # استخدام search_driver للحصول على الاسم (يعمل الآن بشكل صحيح)
            driver_name = search_driver(selected_id)['name'] 
            st.markdown(f"**سجل حركات المندوب: {driver_name} (ID: {selected_id})**")
            df = get_history(driver_id=selected_id)
            
            if not df.empty:
                st.dataframe(df, use_container_width=True)
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="تحميل السجل كملف CSV",
                    data=csv,
                    file_name=f"سجل_المندوب_{selected_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )
            else:
                st.info("لا توجد حركات مسجلة لهذا المندوب.")
        else:
            st.info("يرجى استخدام شريط البحث أعلاه لتحديد المندوب المطلوب.")


# ----------------------------------------------------------------------------------
# 6. إعدادات التطبيق (الشعار) (لم يتغير)
# ----------------------------------------------------------------------------------
elif current_menu == "إعدادات التطبيق (الشعار)":
    st.header("تغيير شعار الشركة")
    st.markdown("يمكنك رفع ملف صورة جديد (PNG أو JPG) ليحل محل الشعار الحالي في الواجهة الجانبية.")
    
    if os.path.exists(IMAGE_PATH):
        st.image(IMAGE_PATH, caption='الشعار الحالي', width=200)
    else:
        st.info("لا يوجد شعار حالي. يرجى رفع شعار جديد.")
        
    uploaded_file = st.file_uploader("اختر صورة الشعار (PNG أو JPG)", type=["png", "jpg", "jpeg"])
    
    if uploaded_file is not None:
        image_bytes = uploaded_file.read()
        
        try:
            with open(IMAGE_PATH, "wb") as f:
                f.write(image_bytes)
            
            st.success("✅ تم رفع وحفظ الشعار الجديد بنجاح!")
            st.rerun() 

        except Exception as e:
            st.error(f"حدث خطأ أثناء حفظ الملف: {e}")