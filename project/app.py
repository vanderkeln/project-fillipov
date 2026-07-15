import streamlit as st
import pandas as pd
import os
import tempfile
import zipfile
import io
from engine_analyzer import EngineAnalyzer, get_sheet_names
from deep_translator import GoogleTranslator

st.set_page_config(page_title="Engine Diagnostic", layout="wide")

if "lang" not in st.session_state:
    st.session_state.lang = "ru"

LANGUAGES = {
    "ru": "Русский",
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
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
    "zh-CN": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
}

with st.sidebar:
    st.markdown("🌐 Язык")
    lang = st.selectbox(
        "",
        options=list(LANGUAGES.keys()),
        format_func=lambda x: translate_text(LANGUAGE_NAMES_EN[x], st.session_state.lang),
        index=0 if st.session_state.lang == "ru" else list(LANGUAGES.keys()).index(st.session_state.lang),
    )
    if lang != st.session_state.lang:
        st.session_state.lang = lang
        st.rerun()


@st.cache_data(ttl=3600)
def translate_text(text, target_lang):
    if target_lang == "ru":
        return text
    try:
        return GoogleTranslator(source="ru", target=target_lang).translate(text)
    except Exception:
        return text


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
    "filter": "Фильтрация",
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
        )
        success = analyzer.run(log_callback=log_callback)

    if success:
        st.success(_(TEXTS["success"]))
        st.info(f"{_(TEXTS['using_sheet'])} {analyzer.used_sheet_name}")
        st.info(_(TEXTS["results_saved"]))

        tab1, tab2, tab3, tab4 = st.tabs(
            [
                _(TEXTS["tab1"]),
                _(TEXTS["tab2"]),
                _(TEXTS["tab3"]),
                _(TEXTS["tab4"]),
            ]
        )

        with tab1:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Simplex")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning(_(TEXTS["no_results"]))

        with tab2:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Polynomials")
                st.dataframe(df, use_container_width=True)
            else:
                st.warning(_(TEXTS["no_results"]))

        with tab3:
            if os.path.exists("results.xlsx"):
                df = pd.read_excel("results.xlsx", sheet_name="Correlations")
                st.subheader(_(TEXTS["corr_pearson"]))
                st.dataframe(df, use_container_width=True)
                df2 = pd.read_excel("results.xlsx", sheet_name="PartialCorr")
                st.subheader(_(TEXTS["corr_partial"]))
                st.dataframe(df2, use_container_width=True)
            else:
                st.warning(_(TEXTS["no_results"]))

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

        if uploaded_file is not None and os.path.exists(file_path):
            os.unlink(file_path)

    else:
        st.error(_(TEXTS["error"]))

elif not file_path and run_btn:
    st.error(_(TEXTS["wait_file"]))
elif file_path and not run_btn:
    st.info(_(TEXTS["wait_run"]))
else:
    st.info(_(TEXTS["wait_file"]))

if uploaded_file:
    st.sidebar.success(f"{_(TEXTS['file_loaded'])} {uploaded_file.name}")
elif file_name_input.strip() != "" and os.path.exists(file_name_input.strip()):
    st.sidebar.success(f"{_(TEXTS['file_loaded'])} {file_name_input.strip()}")
