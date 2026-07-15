import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os
import tempfile
from engine_analyzer import EngineAnalyzer

st.set_page_config(page_title="Engine Diagnostic", layout="wide")

# ---------- Google Translate виджет ----------
# Размещаем в верхней части страницы (можно также в сайдбаре)
translate_html = """
<div id="google_translate_element" style="text-align: right; margin-bottom: 10px;"></div>
<script type="text/javascript">
function googleTranslateElementInit() {
  new google.translate.TranslateElement({
    pageLanguage: 'ru',
    includedLanguages: 'ru,en,de,fr,es,zh-CN,ja,ko,it,pt',
    layout: google.translate.TranslateElement.InlineLayout.SIMPLE
  }, 'google_translate_element');
}
</script>
<script type="text/javascript" src="//translate.google.com/translate_a/element.js?cb=googleTranslateElementInit"></script>
"""
components.html(translate_html, height=60)
# ---------------------------------------------

st.title("🚀 Диагностический анализ двигателя / Engine Diagnostic Analysis")

# --- Боковая панель ---
with st.sidebar:
    st.header("📂 Данные / Data")
    uploaded_file = st.file_uploader("Загрузите Excel-файл / Upload Excel file", type=["xlsx", "xls"])
    sheet_name = st.text_input("Имя листа / Sheet name", "DG1")

    st.header("🧮 Симплекс / Simplex")
    numerator = st.text_input("Числитель / Numerator", "Pz")
    denominator = st.text_input("Знаменатель / Denominator", "Index")

    st.header("📊 Фильтрация / Filtering")
    poly_deg = st.selectbox("Степень полинома / Polynomial degree", [1, 2], index=1)
    
    # Режим коэффициента IQR
    k_mode = st.radio("Режим коэффициента IQR / IQR coefficient mode", 
                      ["Общий / Common", "Индивидуальный / Individual"], index=0)
    if k_mode == "Общий / Common":
        k_iqr = st.number_input("Общий коэффициент k / Common coefficient k", value=0.9, step=0.05, format="%.2f")
        k_params = None
    else:
        st.write("Введите коэффициенты для каждого параметра / Enter coefficients for each parameter:")
        k_params = {}
        param_names = ["Pz", "Pc", "Pi", "Ni", "Index"]
        for p in param_names:
            val = st.number_input(f"k для {p}", value=0.9, step=0.05, format="%.2f", key=f"k_{p}")
            k_params[p.lower()] = val
        k_iqr = None

    run_btn = st.button("🔍 Запустить анализ / Run analysis", type="primary", use_container_width=True)

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

    with st.spinner("⏳ Выполняется анализ... / Running analysis..."):
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
        st.success("✅ Анализ завершён успешно! / Analysis completed successfully!")

        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Симплекс / Simplex", 
            "📈 Коэффициенты / Coefficients",
            "📉 Корреляции / Correlations", 
            "🖼 Графики / Plots"
        ])

        with tab1:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Simplex")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Файл результатов не найден. / Results file not found.")

        with tab2:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Polynomials")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Файл результатов не найден. / Results file not found.")

        with tab3:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Correlations")
                st.subheader("Корреляции Пирсона / Pearson Correlations")
                st.dataframe(df, use_container_width=True)
                df2 = pd.read_excel("results.xlsx", sheet_name="PartialCorr")
                st.subheader("Частные корреляции (контроль по Index) / Partial Correlations (controlling for Index)")
                st.dataframe(df2, use_container_width=True)
            else:
                st.warning("Файл результатов не найден. / Results file not found.")

        with tab4:
            if os.path.exists("plots"):
                images = [f for f in os.listdir("plots") if f.endswith(".png")]
                if images:
                    for img in images:
                        st.image(os.path.join("plots", img), caption=img, use_column_width=True)
                else:
                    st.info("Графики не найдены. / No plots found.")
            else:
                st.info("Графики не найдены. / No plots found.")

        with open("results.xlsx", "rb") as f:
            st.download_button(
                label="📥 Скачать результаты (Excel) / Download results (Excel)",
                data=f,
                file_name="results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        os.unlink(tmp_path)

    else:
        st.error("❌ Ошибка при выполнении анализа. Проверьте логи выше. / Error during analysis. Check logs above.")

elif uploaded_file and not run_btn:
    st.info("👆 Настройте параметры и нажмите кнопку запуска. / Configure parameters and click run.")
else:
    st.info("👈 Загрузите Excel-файл и настройте параметры. / Upload Excel file and configure parameters.")

if uploaded_file:
    st.sidebar.success(f"Файл загружен: / File loaded: {uploaded_file.name}")
