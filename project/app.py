import streamlit as st
import pandas as pd
import os
import tempfile
import zipfile
import io
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import pearsonr, t
from engine_analyzer import EngineAnalyzer, get_sheet_names
from deep_translator import GoogleTranslator

LANGUAGES = {
    "ru": "Русский",
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "el": "Ελληνικά",
    "zh-CN": "中文",
    "ja": "日本語",
    "ko": "한국어",
}

LANGUAGE_NAMES_EN = {
    "ru": "Russian",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "el": "Greek",
    "zh-CN": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

if "lang" not in st.session_state:
    st.session_state.lang = "ru"
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
if "analyzer" not in st.session_state:
    st.session_state.analyzer = None

st.set_page_config(page_title="Engine Diagnostic", layout="wide")

@st.cache_data(ttl=3600)
def translate_text(text, target_lang):
    if target_lang == "ru":
        return text
    try:
        return GoogleTranslator(source="ru", target=target_lang).translate(text)
    except Exception:
        return text

with st.sidebar:
    st.markdown(f"🌐 {translate_text('Язык', st.session_state.lang)}")
    lang = st.selectbox(
        "",
        options=list(LANGUAGES.keys()),
        format_func=lambda x: translate_text(LANGUAGE_NAMES_EN[x], st.session_state.lang),
        index=0 if st.session_state.lang == "ru" else list(LANGUAGES.keys()).index(st.session_state.lang),
    )
    if lang != st.session_state.lang:
        st.session_state.lang = lang
        st.rerun()

TEXTS = {
    "title": "Диагностический анализ двигателя",
    "data": "Данные",
    "upload": "Загрузите Excel-файл",
    "or_enter_name": "Или введите имя файла (если он лежит в папке проекта):",
    "sheet": "Имя листа (если не указано, будет взят первый лист)",
    "sheet_hint": "Доступные листы в файле:",
    "simplex": "Симплекс",
    "num": "Числитель",
    "den": "Знаменатель",
    "filter": "Параметры фильтрации",
    "poly": "Степень полинома",
    "k_mode": "Режим коэффициента IQR",
    "k_common": "Общий",
    "k_individual": "Индивидуальный",
    "k_label": "Общий коэффициент k",
    "k_hint": "Введите коэффициенты для каждого параметра:",
    "run": "Запустить анализ",
    "running": "Выполняется анализ...",
    "success": "Анализ завершён успешно!",
    "error": "Ошибка при выполнении анализа. Проверьте логи выше.",
    "wait_file": "Загрузите Excel-файл или укажите имя файла.",
    "wait_run": "Настройте параметры и нажмите кнопку запуска.",
    "tab1": "Симплекс",
    "tab2": "Коэффициенты",
    "tab3": "Корреляции",
    "tab4": "Графики",
    "corr_pearson": "Корреляции Пирсона",
    "corr_partial": "Частные корреляции (контроль по Index)",
    "download_results": "Скачать результаты (Excel)",
    "download_plots": "Скачать все графики (ZIP)",
    "no_results": "Файл результатов не найден.",
    "no_plots": "Графики не найдены.",
    "file_loaded": "Файл загружен:",
    "results_saved": "Результаты сохранены в файл results.xlsx и папку plots",
    "file_not_found": "Файл не найден. Проверьте имя или загрузите файл через загрузчик.",
    "using_sheet": "Используется лист:",
    "select_param": "Выберите параметр для корреляции",
    "data_source": "Использовать данные",
    "data_all": "все",
    "data_clean": "после фильтрации",
    "no_corr_data": "Нет данных для корреляционного анализа.",
    "not_enough_points": "Недостаточно точек для построения графика.",
    "custom_y": "Пользовательский параметр (введите значения Y через запятую или пробел)",
    "apply_custom": "Применить",
    "custom_corr_title": "Корреляция для пользовательских данных",
    "custom_data_len": "Количество введённых значений:",
    "custom_data_mismatch": "Количество введённых значений не совпадает с количеством точек X ({}).",
}

def _(text):
    return translate_text(text, st.session_state.lang)

st.title(_(TEXTS["title"]))

with st.sidebar:
    st.header(_(TEXTS["data"]))
    uploaded_file = st.file_uploader(_(TEXTS["upload"]), type=["xlsx", "xls"])
    file_name_input = st.text_input(_(TEXTS["or_enter_name"]), "")
    sheet_name = st.text_input(_(TEXTS["sheet"]), "")

    if uploaded_file is not None:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(uploaded_file.getbuffer())
            tmp_path = tmp.name
        sheet_list = get_sheet_names(tmp_path)
        os.unlink(tmp_path)
        if sheet_list:
            st.info(f"{_(TEXTS['sheet_hint'])} {', '.join(sheet_list)}")

    st.header(_(TEXTS["simplex"]))
    numerator = st.text_input(_(TEXTS["num"]), "Pz")
    denominator = st.text_input(_(TEXTS["den"]), "Index")

    st.header(_(TEXTS["filter"]))
    apply_filter = st.checkbox("Применить фильтрацию выбросов", value=True)
    poly_deg = st.selectbox(_(TEXTS["poly"]), [1, 2], index=1)
    k_mode = st.radio(_(TEXTS["k_mode"]), [_(TEXTS["k_common"]), _(TEXTS["k_individual"])], index=0)

    if k_mode == _(TEXTS["k_common"]):
        k_iqr = st.number_input(_(TEXTS["k_label"]), value=0.9, step=0.05, format="%.2f")
        k_params = None
    else:
        st.write(_(TEXTS["k_hint"]))
        k_params = {}
        param_names = ["Pz", "Pc", "Pi", "Ni", "Index"]
        for p in param_names:
            val = st.number_input(f"k для {p}", value=0.9, step=0.05, format="%.2f", key=f"k_{p}")
            k_params[p.lower()] = val
        k_iqr = None

    run_btn = st.button(_(TEXTS["run"]), type="primary", use_container_width=True)

# Определяем путь к файлу
file_path = None
if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded_file.getbuffer())
        file_path = tmp.name
elif file_name_input.strip() != "":
    if os.path.exists(file_name_input.strip()):
        file_path = file_name_input.strip()
    else:
        st.error(_(TEXTS["file_not_found"]))

# Запуск анализа
if file_path and run_btn:
    log_container = st.container()
    log_placeholder = log_container.empty()
    log_messages = []

    def log_callback(msg):
        translated = translate_text(msg, st.session_state.lang)
        log_messages.append(translated)
        log_placeholder.text("\n".join(log_messages[-20:]))

    with st.spinner(_(TEXTS["running"])):
        analyzer = EngineAnalyzer(
            file_path=file_path,
            sheet_name=sheet_name if sheet_name.strip() else None,
            numerator=numerator,
            denominator=denominator,
            poly_deg=poly_deg,
            k_iqr=k_iqr,
            k_params=k_params,
            lang=st.session_state.lang,
            translate_func=translate_text,
            apply_filter=apply_filter,
        )
        success = analyzer.run(log_callback=log_callback)

    if success:
        st.session_state.analysis_done = True
        st.session_state.analyzer = analyzer
        st.success(_(TEXTS["success"]))
        st.info(f"{_(TEXTS['using_sheet'])} {analyzer.used_sheet_name}")
        st.info(_(TEXTS["results_saved"]))
    else:
        st.error(_(TEXTS["error"]))

# ------------------------------------------------------------------
# Функция для построения графика с интервалом предсказания (границы для точек)
# ------------------------------------------------------------------
def plot_with_prediction_interval(x, y, label, xlabel="R/H", ylabel="Y", color='blue', alpha=0.05):
    """
    Строит scatter plot, линию регрессии и 95% интервал предсказания.
    Интервал предсказания показывает, где должны находиться отдельные точки.
    """
    if len(x) < 2:
        return None

    # Линейная регрессия
    coeffs = np.polyfit(x, y, 1)
    slope, intercept = coeffs
    y_pred = slope * x + intercept

    n = len(x)
    residuals = y - y_pred
    ss_res = np.sum(residuals**2)
    se_reg = np.sqrt(ss_res / (n - 2))  # стандартная ошибка регрессии

    # t-критическое для заданного уровня значимости
    t_val = t.ppf(1 - alpha/2, df=n-2)

    # Построение
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(x, y, alpha=0.7, color=color, label=label)

    # Линия регрессии
    x_line = np.linspace(min(x), max(x), 100)
    y_line = slope * x_line + intercept
    ax.plot(x_line, y_line, color='red', linestyle='--', label='Линия регрессии')

    # Интервал предсказания (границы для точек)
    mean_x = np.mean(x)
    # Для интервала предсказания добавляем 1 под корнем (учёт разброса отдельной точки)
    se_pred = se_reg * np.sqrt(1 + 1/n + (x_line - mean_x)**2 / np.sum((x - mean_x)**2))
    ci_lower = y_line - t_val * se_pred
    ci_upper = y_line + t_val * se_pred

    # Закрашенная область (интервал предсказания)
    ax.fill_between(x_line, ci_lower, ci_upper, color='gray', alpha=0.2, label='95% интервал предсказания')
    # Границы (пунктирные линии)
    ax.plot(x_line, ci_lower, color='gray', linestyle=':', linewidth=1.5, alpha=0.7)
    ax.plot(x_line, ci_upper, color='gray', linestyle=':', linewidth=1.5, alpha=0.7)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend()
    return fig

# Отображение результатов (если анализ выполнен и есть файлы)
if st.session_state.analysis_done and os.path.exists("results.xlsx"):
    analyzer = st.session_state.analyzer
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            _(TEXTS["tab1"]),
            _(TEXTS["tab2"]),
            _(TEXTS["tab3"]),
            _(TEXTS["tab4"]),
        ]
    )

    with tab1:
        df = pd.read_excel("results.xlsx", sheet_name="Simplex")
        st.dataframe(df, use_container_width=True)

    with tab2:
        df = pd.read_excel("results.xlsx", sheet_name="Polynomials")
        st.dataframe(df, use_container_width=True)

    with tab3:
        if analyzer and hasattr(analyzer, 'corr_params_all') and analyzer.corr_params_all:
            st.subheader(_(TEXTS["corr_pearson"]))
            data_source = st.radio(_(TEXTS["data_source"]), [_(TEXTS["data_clean"]), _(TEXTS["data_all"])], index=0)
            if data_source == _(TEXTS["data_clean"]):
                corr_dict = analyzer.corr_params_clean
                scatter_dict = analyzer.corr_scatter_data_clean
                x_rh = analyzer.clean_avg_df["R/H"].values if hasattr(analyzer, 'clean_avg_df') and len(analyzer.clean_avg_df) > 0 else None
            else:
                corr_dict = analyzer.corr_params_all
                scatter_dict = analyzer.corr_scatter_data_all
                x_rh = analyzer.avg_df["R/H"].values if hasattr(analyzer, 'avg_df') and len(analyzer.avg_df) > 0 else None

            if not corr_dict:
                st.info(_(TEXTS["no_corr_data"]))
            else:
                param_options = list(corr_dict.keys())
                selected_param = st.selectbox(_(TEXTS["select_param"]), param_options, index=0)

                if selected_param in corr_dict:
                    res = corr_dict[selected_param]
                    df_show = pd.DataFrame({
                        "Параметр": [selected_param],
                        "n": [res["n"]],
                        "r": [res["r"]],
                        "p-value": [res["p"]]
                    })
                    st.dataframe(df_show, use_container_width=True)

                    # График с интервалом предсказания
                    if selected_param in scatter_dict:
                        data = scatter_dict[selected_param]
                        x = data['x']
                        y = data['y']
                        if len(x) > 1:
                            fig = plot_with_prediction_interval(x, y, label=selected_param, xlabel="R/H", ylabel=selected_param, color='blue')
                            if fig:
                                st.pyplot(fig)
                        else:
                            st.info(_(TEXTS["not_enough_points"]))
                else:
                    st.info("Данные для параметра не найдены.")

            # ---- Ручной ввод данных ----
            st.subheader("📊 Ручной ввод данных")
            if x_rh is not None and len(x_rh) > 1:
                st.caption(f"Количество точек X (R/H): **{len(x_rh)}**")
                custom_y_str = st.text_area(
                    "Введите значения Y через запятую или пробел",
                    placeholder="Например: 12.5, 14.2, 13.8, 15.1, ...",
                    height=100
                )
                if st.button("Применить пользовательские данные"):
                    if custom_y_str.strip():
                        try:
                            parts = custom_y_str.replace(',', ' ').split()
                            custom_y = [float(v.strip()) for v in parts if v.strip()]
                        except Exception as e:
                            st.error(f"Ошибка парсинга: {e}")
                            custom_y = []
                        if len(custom_y) == len(x_rh):
                            r, p = pearsonr(x_rh, custom_y)
                            n = len(custom_y)
                            df_custom = pd.DataFrame({
                                "Параметр": ["Пользовательский"],
                                "n": [n],
                                "r": [r],
                                "p-value": [p]
                            })
                            st.dataframe(df_custom, use_container_width=True)

                            # График с интервалом предсказания
                            fig = plot_with_prediction_interval(x_rh, custom_y, label="Пользовательские данные", xlabel="R/H", ylabel="Пользовательский Y", color='green')
                            if fig:
                                st.pyplot(fig)
                            st.caption(f"Коэффициент корреляции **r = {r:.4f}**, p‑value = **{p:.4e}**")
                        else:
                            st.error(f"Количество введённых значений ({len(custom_y)}) не совпадает с количеством точек X ({len(x_rh)}).")
                    else:
                        st.warning("Введите хотя бы одно число.")
            else:
                st.info("Недостаточно точек для ручного ввода (нужно минимум 2 точки).")
        else:
            st.info(_(TEXTS["no_corr_data"]))

        # Частные корреляции
        if os.path.exists("results.xlsx"):
            df_pcorr = pd.read_excel("results.xlsx", sheet_name="PartialCorr")
            st.subheader(_(TEXTS["corr_partial"]))
            st.dataframe(df_pcorr, use_container_width=True)

    with tab4:
        if os.path.exists("plots"):
            images = [f for f in os.listdir("plots") if f.endswith(".png")]
            if images:
                for img in images:
                    st.image(os.path.join("plots", img), caption=img, use_column_width=True)
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                    for img in images:
                        zip_file.write(os.path.join("plots", img), img)
                zip_buffer.seek(0)
                st.download_button(
                    label=_(TEXTS["download_plots"]),
                    data=zip_buffer,
                    file_name="plots.zip",
                    mime="application/zip",
                )
            else:
                st.info(_(TEXTS["no_plots"]))
        else:
            st.info(_(TEXTS["no_plots"]))

    with open("results.xlsx", "rb") as f:
        st.download_button(
            label=_(TEXTS["download_results"]),
            data=f,
            file_name="results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    # Удаление временного файла, если он был создан
    if uploaded_file is not None and file_path and os.path.exists(file_path):
        os.unlink(file_path)

# Если файл загружен, но анализ не запущен
elif file_path and not run_btn and not st.session_state.analysis_done:
    st.info(_(TEXTS["wait_run"]))

# Если файл не загружен
elif not file_path and not run_btn and not st.session_state.analysis_done:
    st.info(_(TEXTS["wait_file"]))

# Отображение имени загруженного файла в сайдбаре
if uploaded_file:
    st.sidebar.success(f"{_(TEXTS['file_loaded'])} {uploaded_file.name}")
elif file_name_input.strip() != "" and os.path.exists(file_name_input.strip()):
    st.sidebar.success(f"{_(TEXTS['file_loaded'])} {file_name_input.strip()}")
