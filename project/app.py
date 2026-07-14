import streamlit as st
import pandas as pd
import os
import tempfile
from engine_analyzer import EngineAnalyzer

st.set_page_config(page_title="Диагностика двигателя", layout="wide")
st.title("🚀 Диагностический анализ двигателя")

with st.sidebar:
    st.header("⚙️ Параметры анализа")
    uploaded_file = st.file_uploader("📂 Загрузите Excel-файл", type=["xlsx", "xls"])
    sheet_name = st.text_input("Имя листа", "DG1")
    numerator = st.text_input("Числитель симплекса", "Pz")
    denominator = st.text_input("Знаменатель симплекса", "Index")
    poly_deg = st.selectbox("Степень полинома", [1, 2], index=1)
    k_iqr = st.number_input("Коэффициент IQR (k)", value=0.9, step=0.05)
    run_btn = st.button("🔍 Запустить анализ", type="primary", use_container_width=True)

if uploaded_file and run_btn:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    with st.spinner("⏳ Выполняется анализ... Пожалуйста, подождите."):
        analyzer = EngineAnalyzer(
            file_path=tmp_path,
            sheet_name=sheet_name,
            numerator=numerator,
            denominator=denominator,
            poly_deg=poly_deg,
            k_iqr=k_iqr
        )
        success = analyzer.run(log_callback=lambda msg: st.info(msg))

    if success:
        st.success("✅ Анализ завершён успешно!")

        tab1, tab2, tab3, tab4 = st.tabs(["📊 Симплекс", "📈 Коэффициенты", "📉 Корреляции", "🖼 Графики"])

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

        with tab3:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Correlations")
                st.subheader("Корреляции Пирсона")
                st.dataframe(df, use_container_width=True)
                df2 = pd.read_excel("results.xlsx", sheet_name="PartialCorr")
                st.subheader("Частные корреляции (контроль по Index)")
                st.dataframe(df2, use_container_width=True)

        with tab4:
            if os.path.exists("plots"):
                images = [f for f in os.listdir("plots") if f.endswith(".png")]
                if images:
                    for img in images:
                        st.image(os.path.join("plots", img), caption=img, use_column_width=True)
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
        st.error("❌ Ошибка при выполнении анализа. Проверьте сообщения выше.")

elif uploaded_file and not run_btn:
    st.info("👆 Настройте параметры и нажмите кнопку запуска.")
else:
    st.info("👈 Загрузите Excel-файл и настройте параметры.")