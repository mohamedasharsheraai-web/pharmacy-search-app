import os
import json
import re
import streamlit as st
import pandas as pd

# ==========================================
# ⚙️ إعدادات الصفحة المباشرة الخفيفة
# ==========================================
st.set_page_config(page_title="نظام بحث الصيدليات", page_icon="💊", layout="wide")

USER_DB_FILE = "users.json"
DATA_FOLDER = "data"

IBNSINA_FOLDER = os.path.join(DATA_FOLDER, "ibnsina")
PHARMA_FOLDER = os.path.join(DATA_FOLDER, "pharma")

for folder in [DATA_FOLDER, IBNSINA_FOLDER, PHARMA_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

def is_excel_file(filename):
    return filename.lower().endswith(('.xlsx', '.xls'))

def read_excel_fast(file_path):
    # قراءة هيدر سريعة
    df_temp = pd.read_excel(file_path, header=None, nrows=15)
    header_row = 0

    for idx, row in df_temp.iterrows():
        row_str = row.astype(str).str.lower().to_string()
        if any(k in row_str for k in ['customer', 'customer name', 'client', 'branch', 'mat. desc.', 'item name']):
            header_row = idx
            break

    df = pd.read_excel(file_path, header=header_row)
    df.columns = df.columns.astype(str).str.strip()
    return df

def clean_code_val(val):
    if pd.isna(val) or str(val).strip() in ['nan', 'None', '-', '']:
        return '-'
    try:
        val_float = float(val)
        val_str = str(int(val_float))
    except Exception:
        val_str = str(val).strip()
        if val_str.endswith('.0'):
            val_str = val_str[:-2]
    
    clean_code = val_str.lstrip('0')
    return clean_code if clean_code else '0'

def extract_year_month_from_filename(file_name):
    base_name = os.path.splitext(file_name)[0]
    
    m_prefix = re.match(r'^(\d{4})_(\d{1,2})', base_name)
    if m_prefix:
        y, m = int(m_prefix.group(1)), int(m_prefix.group(2))
        return f"{y}_{m:02d}"

    year_match = re.search(r'(20\d{2})', base_name)
    year = int(year_match.group(1)) if year_match else 2026

    arabic_months = {
        'يناير': 1, 'فبراير': 2, 'مارس': 3, 'أبريل': 4, 'ابريل': 4,
        'مايو': 5, 'يونيو': 6, 'يوليو': 7, 'أغسطس': 8, 'اغسطس': 8,
        'سبتمبر': 9, 'أكتوبر': 10, 'اكتوبر': 10, 'نوفمبر': 11, 'ديسمبر': 12
    }
    for month_name, m_num in arabic_months.items():
        if month_name in base_name:
            return f"{year}_{m_num:02d}"

    m_ym = re.search(r'(\d{1,2})\s*[-_]\s*(20\d{2})', base_name)
    if m_ym:
        m, y = int(m_ym.group(1)), int(m_ym.group(2))
        return f"{y}_{m:02d}"
    
    m_my = re.search(r'(20\d{2})\s*[-_]\s*(\d{1,2})', base_name)
    if m_my:
        y, m = int(m_my.group(1)), int(m_my.group(2))
        return f"{y}_{m:02d}"

    m_single = re.search(r'(?:شهر|\b)\s*(\d{1,2})\b', base_name)
    if m_single:
        m = int(m_single.group(1))
        if 1 <= m <= 12:
            return f"{year}_{m:02d}"

    return "غير محدد"

# تخزين ثابت سريع في الميموري بدون انتهاء صلاحية مالم يتم الضغط على تحديث
@st.cache_data(show_spinner=False)
def load_distributor_data_fast(folder_path):
    files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if is_excel_file(f)]
    if not files:
        return None
    
    dataframes = []
    
    for file_path in files:
        file_name = os.path.basename(file_path)
        try:
            df = read_excel_fast(file_path)
            
            year_month = None
            date_col = next((c for c in df.columns if any(k in c.lower() for k in ['invoice date', 'date', 'التاريخ'])), None)
            
            if date_col and not df[date_col].dropna().empty:
                try:
                    parsed_dates = pd.to_datetime(df[date_col], errors='coerce')
                    valid_dates = parsed_dates.dropna()
                    if not valid_dates.empty:
                        sample_date = valid_dates.iloc[0]
                        year_month = sample_date.strftime('%Y_%m')
                except Exception:
                    year_month = None
            
            if not year_month or year_month == "غير محدد":
                year_month = extract_year_month_from_filename(file_name)

            df['سنة_شهر'] = year_month
            df['المصدر_الملف'] = file_name
            dataframes.append(df)
        except Exception:
            continue

    if dataframes:
        full_df = pd.concat(dataframes, ignore_index=True)
        return full_df.sort_values(by=['سنة_شهر'], ascending=True)
    return None

def audit_uploaded_files():
    audit_results = []
    total_files_checked = 0

    distributors = [("ابن سينا", IBNSINA_FOLDER), ("فارما أوفيرسيز", PHARMA_FOLDER)]

    for dist_title, folder_path in distributors:
        files = [f for f in os.listdir(folder_path) if is_excel_file(f)]
        for f in files:
            total_files_checked += 1
            file_path = os.path.join(folder_path, f)
            try:
                df = read_excel_fast(file_path)
                cols = [str(c).strip().lower() for c in df.columns]

                has_name = any(k in ' '.join(cols) for k in ['customer name', 'client name', 'اسم العميل', 'الصيدلية'])
                has_qty = any(k in ' '.join(cols) for k in ['quantity', 'qty', 'الكمية', 'value'])

                if df.empty:
                    audit_results.append((dist_title, f, "❌ الملف فارغ تماماً لا يحتوي على بيانات."))
                elif not has_name:
                    audit_results.append((dist_title, f, "⚠️ لم يتم العثور على عمود اسم العميل."))
                elif not has_qty:
                    audit_results.append((dist_title, f, "⚠️ لم يتم العثور على عمود الكمية."))
            except Exception as e:
                audit_results.append((dist_title, f, f"💥 عطل في فتح وقراءة الملف: {str(e)}"))

    return total_files_checked, audit_results

# تهيئة الجلسة
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = True
if 'user_info' not in st.session_state:
    st.session_state['user_info'] = {"phone": "01000000000", "name": "المدير العام", "role": "admin"}
if 'current_page' not in st.session_state:
    st.session_state['current_page'] = 'welcome'
if 'selected_year' not in st.session_state:
    st.session_state['selected_year'] = 2026
if 'selected_upload_dist' not in st.session_state:
    st.session_state['selected_upload_dist'] = None

if 'search_query' not in st.session_state:
    st.session_state['search_query'] = ""
if 'selected_region_key' not in st.session_state:
    st.session_state['selected_region_key'] = "كل المناطق"

def clear_search():
    st.session_state['search_query'] = ""

def clear_region():
    st.session_state['selected_region_key'] = "كل المناطق"

# ==========================================
# 🏠 النظام الأساسي الخفيف
# ==========================================
user = st.session_state['user_info']

with st.sidebar:
    st.write(f"👤 **أهلاً: {user['name']}**")
    st.caption(f"الرتبة: {'مدير نظام' if user['role'] == 'admin' else 'مستخدم'}")
    st.markdown("---")
    
    if st.button("الرئيسية 🏠", use_container_width=True):
        st.session_state['current_page'] = 'welcome'
        st.rerun()

    if user['role'] == 'admin':
        st.subheader("⚙️ لوحة التحكم")

        with st.expander("👤 ➕ إضافة مستخدم جديد"):
            new_name = st.text_input("الاسم:")
            new_phone = st.text_input("رقم التليفون:")
            new_pass = st.text_input("كلمة المرور:", type="password")
            new_role = st.selectbox("نوع الحساب:", ["user", "admin"])
            
            if st.button("حفظ الحساب 💾", use_container_width=True):
                if new_phone and new_pass and new_name:
                    st.success("تمت إضافة الحساب بنجاح!")
                else:
                    st.warning("يرجى ملء جميع البيانات.")

        if st.button("📁 ارفع ملفاتك (إدارة المكتبة)", use_container_width=True):
            st.session_state['current_page'] = 'upload_select_distributor'
            st.rerun()

        if st.button("🔍 فحص سلامة الشيتات المرفوعة", use_container_width=True):
            st.session_state['current_page'] = 'health_check'
            st.rerun()

# --- الرئيسية ---
if st.session_state['current_page'] == 'welcome':
    st.markdown(f"<h1 style='text-align: center;'>👋 أهلاً بك يا {user['name']}</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center; color: gray;'>اختر الموزع للبدء في عملية البحث</h4>", unsafe_allow_html=True)
    st.write("")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("---")
        if st.button("🏢 البحث في ابن سينا", use_container_width=True):
            st.session_state['current_page'] = 'ibnsina'
            st.rerun()

    with c2:
        st.markdown("---")
        if st.button("📦 البحث في فارما", use_container_width=True):
            st.session_state['current_page'] = 'pharma'
            st.rerun()

elif st.session_state['current_page'] == 'upload_select_distributor':
    st.header("📁 إدارة مكتبة الشيتات - اختر الموزع")
    col_ibn, col_ph = st.columns(2)
    with col_ibn:
        if st.button("🏢 مكتبة ابن سينا", use_container_width=True):
            st.session_state['selected_upload_dist'] = "ibnsina"
            st.session_state['current_page'] = 'upload_calendar'
            st.rerun()
    with col_ph:
        if st.button("📦 مكتبة فارما أوفيرسيز", use_container_width=True):
            st.session_state['selected_upload_dist'] = "pharma"
            st.session_state['current_page'] = 'upload_calendar'
            st.rerun()

elif st.session_state['current_page'] == 'upload_calendar':
    dist_name = "ابن سينا" if st.session_state['selected_upload_dist'] == "ibnsina" else "فارما أوفيرسيز"
    target_dir = IBNSINA_FOLDER if st.session_state['selected_upload_dist'] == "ibnsina" else PHARMA_FOLDER

    st.button("⬅️ تغيير الموزع", on_click=lambda: st.session_state.update({'current_page': 'upload_select_distributor'}))
    st.header(f"🗓️ تقويم الشيتات المرفوعة - {dist_name}")

    col_y1, col_y2, col_y3 = st.columns([1, 2, 1])
    with col_y1:
        if st.button("◀️ السنة السابقة"):
            st.session_state['selected_year'] -= 1
            st.rerun()
    with col_y2:
        st.markdown(f"<h3 style='text-align: center;'>سنة {st.session_state['selected_year']}</h3>", unsafe_allow_html=True)
    with col_y3:
        if st.button("السنة القادمة ▶️"):
            st.session_state['selected_year'] += 1
            st.rerun()

    st.divider()

    months = [
        "01 - يناير", "02 - فبراير", "03 - مارس", "04 - أبريل", 
        "05 - مايو", "06 - يونيو", "07 - يوليو", "08 - أغسطس", 
        "09 - سبتمبر", "10 - أكتوبر", "11 - نوفمبر", "12 - ديسمبر"
    ]

    for idx in range(0, 12, 3):
        cols = st.columns(3)
        for j in range(3):
            m_idx = idx + j
            if m_idx < 12:
                month_str = months[m_idx]
                year_val = st.session_state['selected_year']
                file_prefix = f"{year_val}_{m_idx+1:02d}"

                existing_files = [f for f in os.listdir(target_dir) if is_excel_file(f) and (f.startswith(file_prefix) or extract_year_month_from_filename(f) == file_prefix)]

                with cols[j]:
                    with st.container(border=True):
                        st.subheader(month_str)

                        if existing_files:
                            current_file = existing_files[0]
                            st.success(f"📄 {current_file}")
                            if st.button(f"❌ مسح ملف {month_str}", key=f"del_{file_prefix}"):
                                os.remove(os.path.join(target_dir, current_file))
                                st.cache_data.clear()
                                st.success("تم الحذف!")
                                st.rerun()
                        else:
                            st.info("لا يوجد شيت مرفوع")
                            new_file = st.file_uploader(f"رفع شيت {month_str}:", type=["xlsx", "xls", "XLSX", "XLS"], key=f"up_{file_prefix}")
                            if new_file:
                                save_name = f"{file_prefix}_{new_file.name}"
                                with open(os.path.join(target_dir, save_name), "wb") as f:
                                    f.write(new_file.getbuffer())
                                st.cache_data.clear()
                                st.success("تم الرفع بنجاح!")
                                st.rerun()

# --- شاشة فحص سلامة الملفات ---
elif st.session_state['current_page'] == 'health_check':
    st.button("⬅️ العودة للرئيسية", on_click=lambda: st.session_state.update({'current_page': 'welcome'}))
    st.header("🔍 نتيجة فحص سلامة وقراءة الشيتات المرفوعة")

    total_count, errors = audit_uploaded_files()
    st.divider()

    if total_count == 0:
        st.info("ℹ️ لا توجد أي ملفات مرفوعة حالياً في النظام لتتم المراجعة عليها.")
    elif not errors:
        st.success(f"🟢 **جميع الملفات المرفوعة (عددها {total_count} ملف) سليمة ومقروءة 100%.**")
    else:
        st.warning(f"⚠️ تم فحص {total_count} ملف، وعثر النظام على بعض الملاحظات في {len(errors)} ملف:")
        for dist, fname, issue in errors:
            st.error(f"🏢 **الموزع:** {dist} | 📄 **الملف:** `{fname}` 👈 **المشكلة:** {issue}")

# --- شاشة البحث الفائقة السرعة ---
elif st.session_state['current_page'] in ['ibnsina', 'pharma']:
    dist_code = st.session_state['current_page']
    dist_title = "ابن سينا" if dist_code == 'ibnsina' else "فارما أوفيرسيز"
    target_folder = IBNSINA_FOLDER if dist_code == 'ibnsina' else PHARMA_FOLDER

    c_top1, c_top2 = st.columns([4, 1])
    with c_top1:
        st.button("⬅️ العودة للرئيسية", on_click=lambda: st.session_state.update({'current_page': 'welcome'}))
    with c_top2:
        if st.button("🔄 تحديث البيانات", help="تفرغ الذاكرة المؤقتة لقراءة ملفات جديدة"):
            st.cache_data.clear()
            st.rerun()

    st.header(f"🔍 البحث في قاعدة بيانات: {dist_title}")

    # تحميل داتا صامت فورية
    df_dist = load_distributor_data_fast(target_folder)

    if df_dist is None or df_dist.empty:
        st.warning(f"لا توجد شيتات مرفوعة حالياً في مكتبة {dist_title}. برجاء الذهاب لـ 'ارفع ملفاتك' ورفع الشيتات أولاً.")
    else:
        cols = list(df_dist.columns)
        
        c_code = next((c for c in cols if c.strip().lower() in ['customer', 'client code', 'كود العميل', 'customer code']), None)
        c_name = next((c for c in cols if c.strip().lower() in ['customer name', 'client name', 'اسم العميل', 'الصيدلية']), cols[0])
        region_col = next((c for c in cols if c.strip().lower() in ['sal. dist. desc.', 'governorate', 'المحافظة', 'المنطقة']), None)
        
        b_code = next((c for c in cols if c.strip().lower() in ['branch', 'branch code', 'كود الفرع']), None)
        b_name = next((c for c in cols if c.strip().lower() in ['branch name', 'اسم الفرع', 'الفرع']), None)
        
        item_col = next((c for c in cols if c.strip().lower() in ['mat. desc.', 'item name', 'المنتج']), None)
        qty_col = next((c for c in cols if c.strip().lower() in ['qty', 'quantity', 'الكمية']), None)
        addr_col = next((c for c in cols if c.strip().lower() in ['customer address', 'address_en', 'العنوان']), None)

        if 'clean_code' not in df_dist.columns:
            if c_code and c_code in df_dist.columns:
                df_dist['clean_code'] = df_dist[c_code].apply(clean_code_val)
            else:
                df_dist['clean_code'] = '-'

        st.markdown("### 🔍 أدوات تصفية البحث:")
        c_inp, c_clr_inp, c_reg, c_clr_reg = st.columns([3, 0.4, 2.6, 0.4])

        with c_inp:
            name_query = st.text_input(
                "1. اكتب كود العميل (أو الاسم):", 
                key="search_query", 
                placeholder="مثال: 1522888 / شوكت"
            )

        with c_clr_inp:
            st.write("")
            st.write("")
            st.button("❌", key="btn_clr_search", on_click=clear_search, help="مسح خانة البحث")

        with c_reg:
            available_regions = ["كل المناطق"]
            if region_col and region_col in df_dist.columns:
                raw_regs = df_dist[region_col].dropna().unique().tolist()
                clean_regs = sorted([str(r).strip() for r in raw_regs if r and str(r).lower() != 'nan'])
                available_regions.extend(clean_regs)

            if st.session_state['selected_region_key'] not in available_regions:
                st.session_state['selected_region_key'] = "كل المناطق"

            selected_region = st.selectbox(
                "2. اختر المنطقة:", 
                options=available_regions,
                key="selected_region_key"
            )

        with c_clr_reg:
            st.write("")
            st.write("")
            st.button("❌", key="btn_clr_region", on_click=clear_region, help="مسح المنطقة وإرجاع الكل")

        filtered_df = df_dist

        if region_col and selected_region != "كل المناطق":
            filtered_df = filtered_df[filtered_df[region_col].astype(str).str.strip() == selected_region]

        if name_query.strip():
            q_clean = name_query.strip().lstrip('0')
            mask = pd.Series(False, index=filtered_df.index)
            
            if c_name in filtered_df.columns:
                mask = mask | filtered_df[c_name].astype(str).str.contains(name_query.strip(), case=False, na=False, regex=False)
            if 'clean_code' in filtered_df.columns:
                mask = mask | filtered_df['clean_code'].astype(str).str.contains(q_clean, case=False, na=False, regex=False)
            
            filtered_df = filtered_df[mask]

        if name_query.strip() or selected_region != "كل المناطق":
            if not filtered_df.empty:
                unique_clients = filtered_df[['clean_code', c_name, region_col] if region_col else ['clean_code', c_name]].drop_duplicates(subset=['clean_code'])

                pharmacy_options = []
                for _, row in unique_clients.iterrows():
                    p_code_val = str(row.get('clean_code', '-'))
                    p_name = str(row.get(c_name, 'بدون اسم'))
                    p_reg = str(row.get(region_col, 'غير محدد')) if region_col else '-'

                    label = f"🔑 الكود: {p_code_val} | 🏥 {p_name} | 📍 المنطقة: {p_reg}"
                    pharmacy_options.append((label, p_code_val, p_name))

                st.write("")
                selected_choice = st.selectbox(
                    "🎯 النتائج المطابقة (اختر العميل للنتائج التفصيلية):", 
                    options=pharmacy_options, 
                    format_func=lambda x: x[0]
                )

                if selected_choice:
                    target_code = selected_choice[1]
                    target_pharm_name = selected_choice[2]

                    if target_code != '-' and target_code != '':
                        pharm_details = df_dist[
                            (df_dist['clean_code'] == target_code) |
                            (df_dist[c_name].astype(str) == target_pharm_name)
                        ]
                    else:
                        pharm_details = df_dist[df_dist[c_name].astype(str) == target_pharm_name]

                    st.divider()
                    st.subheader(f"📌 كارت البيانات للصيدلية: {target_pharm_name}")

                    first_row = pharm_details.iloc[0]
                    val_code = first_row.get('clean_code', '-')
                    val_name = str(first_row.get(c_name, '-'))
                    val_region = str(first_row.get(region_col, '-')) if region_col else '-'

                    m1, m2, m3 = st.columns(3)
                    
                    with m1:
                        st.caption("🔑 كود الصيدلية الثابت:")
                        st.code(val_code, language=None)

                    with m2:
                        st.caption("🏥 اسم الصيدلية بالكامل:")
                        st.code(val_name, language=None)

                    with m3:
                        st.caption("📍 المنطقة / المحافظة:")
                        st.code(val_region, language=None)

                    if addr_col and addr_col in first_row:
                        val_addr = str(first_row.get(addr_col, '-'))
                        st.caption("📍 العنوان التفصيلي:")
                        st.code(val_addr, language=None)

                    months_found = pharm_details['سنة_شهر'].unique().tolist()
                    st.success(f"📊 تم العثور على مسحوبات للعميل في **{len(months_found)}** شهر/ملف: ({' ، '.join(months_found)})")

                    st.markdown("### 📦 سجل كافة مسحوبات العميل من جميع الشيتات:")
                    
                    ordered_cols = [c for c in ['سنة_شهر', b_code, b_name, item_col, qty_col, addr_col] if c and c in pharm_details.columns]
                    final_df_display = pharm_details[ordered_cols] if ordered_cols else pharm_details
                    
                    st.dataframe(final_df_display, use_container_width=True, hide_index=True)

            else:
                st.warning("❌ لم يتم العثور على نتائج تطابق كود العميل أو اسم الصيدلية المحدد.")
