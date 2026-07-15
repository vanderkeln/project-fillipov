import streamlit as st
import pandas as pd
import os
import tempfile
from engine_analyzer import EngineAnalyzer

st.set_page_config(page_title="Engine Diagnostic", layout="wide")

# ---------- ПЕРЕКЛЮЧАТЕЛЬ ЯЗЫКА (кнопки в шапке) ----------
if 'lang' not in st.session_state:
    st.session_state.lang = 'ru'

col1, col2, col3 = st.columns([1, 6, 1])
with col1:
    if st.button("🇷🇺 Русский", use_container_width=True):
        st.session_state.lang = 'ru'
        st.rerun()
with col3:
    if st.button("🇬🇧 English", use_container_width=True):
        st.session_state.lang = 'en'
        st.rerun()
# -----------------------------------------------------------

# Словарь переводов
if st.session_state.lang == 'ru':
    T = {
        'title': '🚀 Диагностический анализ двигателя',
        'data': '📂 Данные',
        'upload': 'Загрузите Excel-файл',
        'sheet': 'Имя листа',
        'simplex': '🧮 Симплекс',
        'num': 'Числитель',
        'den': 'Знаменатель',
        'filter': '📊 Фильтрация',
        'poly': 'Степень полинома',
        'k_mode': 'Режим коэффициента IQR',
        'k_common': 'Общий',
        'k_individual': 'Индивидуальный',
        'k_label': 'Общий коэффициент k',
        'k_hint': 'Введите коэффициенты для каждого параметра:',
        'run': '🔍 Запустить анализ',
        'running': '⏳ Выполняется анализ...',
        'success': '✅ Анализ завершён успешно!',
        'error': '❌ Ошибка при выполнении анализа. Проверьте логи выше.',
        'wait_file': '👈 Загрузите Excel-файл и настройте параметры.',
        'wait_run': '👆 Настройте параметры и нажмите кнопку запуска.',
        'tab1': '📊 Симплекс',
        'tab2': '📈 Коэффициенты',
        'tab3': '📉 Корреляции',
        'tab4': '🖼 Графики',
        'corr_pearson': 'Корреляции Пирсона',
        'corr_partial': 'Частные корреляции (контроль по Index)',
        'download': '📥 Скачать результаты (Excel)',
        'no_results': 'Файл результатов не найден.',
        'no_plots': 'Графики не найдены.',
        'file_loaded': 'Файл загружен:'
    }
else:
    T = {
        'title': '🚀 Engine Diagnostic Analysis',
        'data': '📂 Data',
        'upload': 'Upload Excel file',
        'sheet': 'Sheet name',
        'simplex': '🧮 Simplex',
        'num': 'Numerator',
        'den': 'Denominator',
        'filter': '📊 Filtering',
        'poly': 'Polynomial degree',
        'k_mode': 'IQR coefficient mode',
        'k_common': 'Common',
        'k_individual': 'Individual',
        'k_label': 'Common coefficient k',
        'k_hint': 'Enter coefficients for each parameter:',
        'run': '🔍 Run analysis',
        'running': '⏳ Running analysis...',
        'success': '✅ Analysis completed successfully!',
        'error': '❌ Error during analysis. Check logs above.',
        'wait_file': '👈 Upload Excel file and configure parameters.',
        'wait_run': '👆 Configure parameters and click run.',
        'tab1': '📊 Simplex',
        'tab2': '📈 Coefficients',
        'tab3': '📉 Correlations',
        'tab4': '🖼 Plots',
        'corr_pearson': 'Pearson Correlations',
        'corr_partial': 'Partial Correlations (controlling for Index)',
        'download': '📥 Download results (Excel)',
        'no_results': 'Results file not found.',
        'no_plots': 'No plots found.',
        'file_loaded': 'File loaded:'
    }

st.title(T['title'])

# --- Боковая панель ---
with st.sidebar:
    st.header(T['data'])
    uploaded_file = st.file_uploader(T['upload'], type=["xlsx", "xls"])
    sheet_name = st.text_input(T['sheet'], "DG1")

    st.header(T['simplex'])
    numerator = st.text_input(T['num'], "Pz")
    denominator = st.text_input(T['den'], "Index")

    st.header(T['filter'])
    poly_deg = st.selectbox(T['poly'], [1, 2], index=1)
    k_mode = st.radio(T['k_mode'], [T['k_common'], T['k_individual']], index=0)
    if k_mode == T['k_common']:
        k_iqr = st.number_input(T['k_label'], value=0.9, step=0.05, format="%.2f")
        k_params = None
    else:
        st.write(T['k_hint'])
        k_params = {}
        param_names = ["Pz", "Pc", "Pi", "Ni", "Index"]
        for p in param_names:
            val = st.number_input(f"k для {p}", value=0.9, step=0.05, format="%.2f", key=f"k_{p}")
            k_params[p.lower()] = val
        k_iqr = None

    run_btn = st.button(T['run'], type="primary", use_container_width=True)

# --- Основная область ---
if uploaded_file and run_btn:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    log_container = st.container()
    log_placeholder = log_container.empty()
    log_messages = []

    def log_callback(msg):
        log_messages.append(msg)
        log_placeholder.text("\n".join(log_messages[-20:]))

    with st.spinner(T['running']):
        analyzer = EngineAnalyzer(
            file_path=tmp_path,
            sheet_name=sheet_name,
            numerator=numerator,
            denominator=denominator,
            poly_deg=poly_deg,
            k_iqr=k_iqr,
            k_params=k_params
        )
        success = analyzer.run(log_callback=log_callback)

    if success:
        st.success(T['success'])

        tab1, tab2, tab3, tab4 = st.tabs([T['tab1'], T['tab2'], T['tab3'], T['tab4']])

        with tab1:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Simplex")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning(T['no_results'])

        with tab2:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Polynomials")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning(T['no_results'])

        with tab3:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Correlations")
                st.subheader(T['corr_pearson'])
                st.dataframe(df, use_container_width=True)
                df2 = pd.read_excel("results.xlsx", sheet_name="PartialCorr")
                st.subheader(T['corr_partial'])
                st.dataframe(df2, use_container_width=True)
            else:
                st.warning(T['no_results'])

        with tab4:
            if os.path.exists("plots"):
                images = [f for f in os.listdir("plots") if f.endswith(".png")]
                if images:
                    for img in images:
                        st.image(os.path.join("plots", img), caption=img, use_column_width=True)
                else:
                    st.info(T['no_plots'])
            else:
                st.info(T['no_plots'])

        with open("results.xlsx", "rb") as f:
            st.download_button(
                label=T['download'],
                data=f,
                file_name="results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        os.unlink(tmp_path)

    else:
        st.error(T['error'])

elif uploaded_file and not run_btn:
    st.info(T['wait_run'])
else:
    st.info(T['wait_file'])

if uploaded_file:
    st.sidebar.success(f"{T['file_loaded']} {uploaded_file.name}")
