import streamlit as st
import pandas as pd
import os
import tempfile
from engine_analyzer import EngineAnalyzer

st.set_page_config(page_title="Диагностика двигателя", layout="wide")
st.title("🚀 Диагностический анализ двигателя")

# --- Боковая панель ---
with st.sidebar:
    st.header("📂 Данные")
    uploaded_file = st.file_uploader("Загрузите Excel-файл", type=["xlsx", "xls"])
    sheet_name = st.text_input("Имя листа", "DG1")

    st.header("🧮 Симплекс")
    numerator = st.text_input("Числитель", "Pz")
    denominator = st.text_input("Знаменатель", "Index")

    st.header("📊 Фильтрация")
    poly_deg = st.selectbox("Степень полинома", [1, 2], index=1)

    # Выбор типа коэффициента IQR
    k_mode = st.radio("Режим коэффициента IQR", ["Общий", "Индивидуальный"], index=0)
    if k_mode == "Общий":
        k_iqr = st.number_input("Общий коэффициент k", value=0.9, step=0.05, format="%.2f")
        k_params = None
    else:
        st.write("Введите коэффициенты для каждого параметра:")
        # Определим список возможных параметров (заглушка, позже будет обновлён после загрузки)
        # Пока предложим ввод через текстовое поле, но лучше сделать динамически после загрузки.
        # Однако можно сделать предустановленные поля для Pz, Pc, Pi, Ni, Index.
        # Используем expander для каждого параметра.
        k_params = {}
        # Мы не знаем параметры до загрузки, но можно сделать поля для типичных
        # А можно сделать текстовое поле для ввода словаря, но проще – для каждого параметра отдельно.
        # Сделаем для пяти основных:
        param_names = ["Pz", "Pc", "Pi", "Ni", "Index"]
        for p in param_names:
            val = st.number_input(f"k для {p}", value=0.9, step=0.05, format="%.2f", key=f"k_{p}")
            k_params[p.lower()] = val
        k_iqr = None

    run_btn = st.button("🔍 Запустить анализ", type="primary", use_container_width=True)

# --- Основная область ---
if uploaded_file and run_btn:
    # Сохраняем загруженный файл во временный файл
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name

    # Создаём контейнер для логов
    log_container = st.container()
    log_placeholder = log_container.empty()
    log_messages = []

    def log_callback(msg):
        log_messages.append(msg)
        log_placeholder.text("\n".join(log_messages[-20:]))  # показываем последние 20 строк

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

        # Вкладки результатов
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

        # Кнопка скачивания
        with open("results.xlsx", "rb") as f:
            st.download_button(
                label="📥 Скачать результаты (Excel)",
                data=f,
                file_name="results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # Удаляем временный файл
        os.unlink(tmp_path)

    else:
        st.error("❌ Ошибка при выполнении анализа. Проверьте логи выше.")

elif uploaded_file and not run_btn:
    st.info("👆 Настройте параметры и нажмите кнопку запуска.")
else:
    st.info("👈 Загрузите Excel-файл и настройте параметры.")

# Дополнительно: отображаем информацию о загруженном файле
if uploaded_file:
    st.sidebar.success(f"Файл загружен: {uploaded_file.name}")
