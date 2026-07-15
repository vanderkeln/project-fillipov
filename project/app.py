import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os
import tempfile
from engine_analyzer import EngineAnalyzer

st.set_page_config(page_title="Engine Diagnostic", layout="wide")

# ---------- Google Translate (гарантированно работает) ----------
# Размещаем в отдельном блоке с фиксированной высотой
translate_html = """
<div style="text-align: right; padding: 10px; background: #f0f2f6; border-radius: 5px; margin-bottom: 10px;">
    <div id="google_translate_element"></div>
</div>
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
<style>
    /* Скрываем верхнюю панель Google */
    .goog-te-banner-frame.skiptranslate {
        display: none !important;
    }
    body {
        top: 0px !important;
    }
    .goog-te-gadget {
        font-family: inherit !important;
    }
    .goog-te-combo {
        padding: 5px 10px;
        border-radius: 4px;
        border: 1px solid #ccc;
        font-size: 14px;
    }
</style>
"""
components.html(translate_html, height=120)

st.title("🚀 Диагностический анализ двигателя")

# ---------- Остальной интерфейс ----------
with st.sidebar:
    st.header("📂 Данные")
    uploaded_file = st.file_uploader("Загрузите Excel-файл", type=["xlsx", "xls"])
    sheet_name = st.text_input("Имя листа", "DG1")

    st.header("🧮 Симплекс")
    numerator = st.text_input("Числитель", "Pz")
    denominator = st.text_input("Знаменатель", "Index")

    st.header("📊 Фильтрация")
    poly_deg = st.selectbox("Степень полинома", [1, 2], index=1)
    k_mode = st.radio("Режим коэффициента IQR", ["Общий", "Индивидуальный"], index=0)
    if k_mode == "Общий":
        k_iqr = st.number_input("Общий коэффициент k", value=0.9, step=0.05, format="%.2f")
        k_params = None
    else:
        st.write("Введите коэффициенты для каждого параметра:")
        k_params = {}
        param_names = ["Pz", "Pc", "Pi", "Ni", "Index"]
        for p in param_names:
            val = st.number_input(f"k для {p}", value=0.9, step=0.05, format="%.2f", key=f"k_{p}")
            k_params[p.lower()] = val
        k_iqr = None

    run_btn = st.button("🔍 Запустить анализ", type="primary", use_container_width=True)

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

    with st.spinner("⏳ Выполняется анализ..."):
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
        st.success("✅ Анализ завершён успешно!")

        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Симплекс", "📈 Коэффициенты",
            "📉 Корреляции", "🖼 Графики"
        ])

        with tab1:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Simplex")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Файл результатов не найден.")

        with tab2:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Polynomials")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning("Файл результатов не найден.")

        with tab3:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Correlations")
                st.subheader("Корреляции Пирсона")
                st.dataframe(df, use_container_width=True)
                df2 = pd.read_excel("results.xlsx", sheet_name="PartialCorr")
                st.subheader("Частные корреляции (контроль по Index)")
                st.dataframe(df2, use_container_width=True)
            else:
                st.warning("Файл результатов не найден.")

        with tab4:
            if os.path.exists("plots"):
                images = [f for f in os.listdir("plots") if f.endswith(".png")]
                if images:
                    for img in images:
                        st.image(os.path.join("plots", img), caption=img, use_column_width=True)
                else:
                    st.info("Графики не найдены.")
            else:
                st.info("Графики не найдены.")

        with open("results.xlsx", "rb") as f:
            st.download_button(
                label="📥 Скачать результаты (Excel)",
                data=f,
                file_name="results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        os.unlink(tmp_path)

    else:
        st.error("❌ Ошибка при выполнении анализа. Проверьте логи выше.")

elif uploaded_file and not run_btn:
    st.info("👆 Настройте параметры и нажмите кнопку запуска.")
else:
    st.info("👈 Загрузите Excel-файл и настройте параметры.")

if uploaded_file:
    st.sidebar.success(f"Файл загружен: {uploaded_file.name}")
