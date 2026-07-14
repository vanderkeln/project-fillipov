import sys
import os
import pandas as pd
import numpy as np
from scipy.stats import pearsonr
import matplotlib.pyplot as plt
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QTabWidget,
    QTextEdit, QTableWidget, QTableWidgetItem, QComboBox,
    QScrollArea, QFrame, QGridLayout, QGroupBox, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
import re
import warnings
warnings.filterwarnings('ignore')

def read_data(file_path, sheet_name):
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=0)
    df = df.dropna(how='all').dropna(axis=1, how='all')
    df.columns = df.columns.str.strip()
    new_cols = []
    for col in df.columns:
        if 'cyl' in col.lower():
            num = re.search(r'\d+', col)
            if num:
                new_cols.append(f'cyl{num.group()}')
            else:
                new_cols.append(col)
        else:
            new_cols.append(col)
    df.columns = new_cols
    return df

def detect_cylinders(df):
    return len([col for col in df.columns if col.startswith('cyl')])

def detect_parameters(df):
    if 'parameters' not in df.columns:
        raise KeyError("В таблице нет столбца 'parameters'")
    params = df['parameters'].dropna().unique()
    params = [str(p).strip().lower() for p in params if isinstance(p, str)]
    return params

def group_blocks(df, params):
    blocks = []
    n_params = len(params)
    idx_params = df[df['parameters'].notna()].index.tolist()
    for i in range(0, len(idx_params), n_params):
        start = idx_params[i]
        if i + n_params <= len(idx_params):
            block = df.iloc[start:start+n_params].copy()
            blocks.append(block)
    return blocks

def average_block(block, params, cyl_cols):
    avg_dict = {}
    date_val = block.iloc[0]['DATE'] if 'DATE' in block.columns else None
    rh_val = block.iloc[0]['R/H'] if 'R/H' in block.columns else None
    for p in params:
        row = block[block['parameters'].str.lower() == p]
        if not row.empty:
            vals = row[cyl_cols].values.flatten()
            vals_num = [float(v) for v in vals if pd.notna(v) and v != 0]
            avg_dict[p] = np.mean(vals_num) if vals_num else 0.0
        else:
            avg_dict[p] = 0.0
    return date_val, rh_val, avg_dict

def polynomial_fit(x, y, deg):
    coeffs = np.polyfit(x, y, deg)
    func = lambda x: np.polyval(coeffs, x)
    return func, coeffs

def filter_outliers(x, y, deg, k):
    if len(x) < 3:
        return np.ones(len(x), dtype=bool), None, None, None, None
    func, _ = polynomial_fit(x, y, deg)
    y_fit = func(x)
    residuals = y - y_fit
    q1 = np.percentile(residuals, 25)
    q3 = np.percentile(residuals, 75)
    iqr = q3 - q1
    lower_bound = q1 - k * iqr
    upper_bound = q3 + k * iqr
    mask = (residuals >= lower_bound) & (residuals <= upper_bound)
    return mask, func, lower_bound, upper_bound, residuals

def evaluate_simplex(expr, values):
    try:
        expr_lower = expr.lower()
        safe_dict = {k: v for k, v in values.items()}
        result = eval(expr_lower, {"__builtins__": {}}, safe_dict)
        return float(result)
    except:
        return np.nan

class EngineAnalyzer:
    def __init__(self, file_path, sheet_name, numerator, denominator, poly_deg, k_iqr):
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.numerator = numerator
        self.denominator = denominator
        self.poly_deg = poly_deg
        self.k_iqr = k_iqr
        self.df = None
        self.params = []
        self.cylinders = 0
        self.blocks = []
        self.avg_df = None
        self.filter_masks = {}
        self.clean_indices = None
        self.simplex_df = None
        self.poly_results = {}
        self.poly_functions = {}
        self.corr_results = {}
        self.partial_corr = {}
        self.output_excel = "results.xlsx"
        self.plot_dir = "plots"

    def run(self, log_callback=None):
        try:
            if log_callback:
                log_callback("Загрузка данных...")
            self.df = read_data(self.file_path, self.sheet_name)
            self.cylinders = detect_cylinders(self.df)
            self.params = detect_parameters(self.df)
            if log_callback:
                log_callback(f"Обнаружено цилиндров: {self.cylinders}")
                log_callback(f"Обнаружены параметры: {self.params}")

            self.blocks = group_blocks(self.df, self.params)
            if log_callback:
                log_callback(f"Всего блоков: {len(self.blocks)}")

            cyl_cols = [f'cyl{i}' for i in range(1, self.cylinders+1)]
            rows = []
            for block in self.blocks:
                date, rh, avg_dict = average_block(block, self.params, cyl_cols)
                row = {'DATE': date, 'R/H': rh}
                row.update(avg_dict)
                rows.append(row)
            self.avg_df = pd.DataFrame(rows)
            if log_callback:
                log_callback("Средние значения вычислены.")

            # Фильтрация
            self.filter_masks = {}
            all_good = np.ones(len(self.avg_df), dtype=bool)
            for param in self.params:
                x = self.avg_df['R/H'].values
                y = self.avg_df[param].values
                valid = ~np.isnan(y)
                x_valid = x[valid]
                y_valid = y[valid]
                if len(x_valid) < 3:
                    mask = np.ones(len(y), dtype=bool)
                else:
                    mask_valid, _, _, _, _ = filter_outliers(x_valid, y_valid, self.poly_deg, self.k_iqr)
                    mask = np.zeros(len(y), dtype=bool)
                    mask[valid] = mask_valid
                self.filter_masks[param] = mask
                self.avg_df[f'{param}_flag'] = (~mask).astype(int)
                all_good &= mask
            self.clean_indices = all_good
            self.clean_avg_df = self.avg_df[all_good].copy()
            if log_callback:
                log_callback(f"После фильтрации осталось {len(self.clean_avg_df)} блоков из {len(self.avg_df)}.")

            # Симплекс
            rows_simplex = []
            for idx, block in enumerate(self.blocks):
                if not self.clean_indices[idx]:
                    continue
                param_values = {}
                for p in self.params:
                    row = block[block['parameters'].str.lower() == p]
                    if not row.empty:
                        vals = row[cyl_cols].values.flatten()
                        vals_num = [float(v) for v in vals if pd.notna(v)]
                        if len(vals_num) < self.cylinders:
                            vals_num += [np.nan] * (self.cylinders - len(vals_num))
                        param_values[p] = np.array(vals_num)
                    else:
                        param_values[p] = np.full(self.cylinders, np.nan)
                cyl_simplex = []
                for cyl_idx in range(self.cylinders):
                    cyl_vals = {p: param_values[p][cyl_idx] for p in self.params}
                    if any(np.isnan(v) for v in cyl_vals.values()):
                        cyl_simplex.append(np.nan)
                    else:
                        num = evaluate_simplex(self.numerator, cyl_vals)
                        den = evaluate_simplex(self.denominator, cyl_vals)
                        if den == 0 or np.isnan(den) or np.isnan(num):
                            cyl_simplex.append(np.nan)
                        else:
                            cyl_simplex.append(num / den)
                avg_simplex = np.nanmean(cyl_simplex)
                rh = block.iloc[0]['R/H'] if 'R/H' in block.columns else np.nan
                row = {'R/H': rh}
                for i, val in enumerate(cyl_simplex):
                    row[f'cyl{i+1}'] = val
                row['AVG'] = avg_simplex
                rows_simplex.append(row)
            self.simplex_df = pd.DataFrame(rows_simplex)
            if log_callback:
                log_callback(f"Симплекс вычислен для {len(self.simplex_df)} блоков.")

            # Аппроксимация полиномов
            columns = [f'cyl{i}' for i in range(1, self.cylinders+1)] + ['AVG']
            for col in columns:
                x = self.simplex_df['R/H'].values
                y = self.simplex_df[col].values
                valid = ~np.isnan(y)
                x_valid = x[valid]
                y_valid = y[valid]
                if len(x_valid) < self.poly_deg + 1:
                    self.poly_results[col] = None
                    self.poly_functions[col] = None
                    continue
                func, coeffs = polynomial_fit(x_valid, y_valid, self.poly_deg)
                self.poly_results[col] = coeffs
                self.poly_functions[col] = func
            if log_callback:
                log_callback("Полиномиальная аппроксимация выполнена.")

            # Корреляции
            for col in columns:
                x = self.simplex_df['R/H'].values
                y = self.simplex_df[col].values
                valid = ~np.isnan(y)
                x_clean = x[valid]
                y_clean = y[valid]
                if len(x_clean) < 3:
                    self.corr_results[col] = {'n': len(x_clean), 'r': np.nan, 'p': np.nan}
                else:
                    r, p = pearsonr(x_clean, y_clean)
                    self.corr_results[col] = {'n': len(x_clean), 'r': r, 'p': p}
            if log_callback:
                log_callback("Корреляции вычислены.")

            # Частная корреляция
            idx_col = None
            for col in self.avg_df.columns:
                if col.lower() == 'index':
                    idx_col = col
                    break
            if idx_col is not None:
                x_rh = self.avg_df.loc[self.clean_indices, 'R/H'].values
                x_index = self.avg_df.loc[self.clean_indices, idx_col].values
                for col in columns:
                    y = self.simplex_df[col].values
                    rh_clean, idx_clean, y_clean = [], [], []
                    for i in range(len(y)):
                        if (not np.isnan(y[i]) and not np.isnan(x_index[i]) and not np.isnan(x_rh[i])):
                            rh_clean.append(x_rh[i])
                            idx_clean.append(x_index[i])
                            y_clean.append(y[i])
                    if len(rh_clean) < 4:
                        self.partial_corr[col] = {'n': len(rh_clean), 'r': np.nan, 'p': np.nan}
                        continue
                    slope, intercept = np.polyfit(idx_clean, y_clean, 1)
                    residuals = y_clean - (slope * np.array(idx_clean) + intercept)
                    r, p = pearsonr(rh_clean, residuals)
                    self.partial_corr[col] = {'n': len(rh_clean), 'r': r, 'p': p}
                if log_callback:
                    log_callback("Частные корреляции вычислены.")
            else:
                if log_callback:
                    log_callback("Предупреждение: столбец Index не найден, частная корреляция пропущена.")
                self.partial_corr = {}

            # Сохранение в Excel
            os.makedirs(self.plot_dir, exist_ok=True)
            with pd.ExcelWriter(self.output_excel, engine='openpyxl') as writer:
                self.avg_df.to_excel(writer, sheet_name='Averages', index=False)
                self.simplex_df.to_excel(writer, sheet_name='Simplex', index=False)
                poly_rows = []
                for col, coeffs in self.poly_results.items():
                    if coeffs is not None:
                        row = {'Cylinder': col}
                        for i, c in enumerate(coeffs[::-1]):
                            row[f'a{i}'] = c
                        poly_rows.append(row)
                pd.DataFrame(poly_rows).to_excel(writer, sheet_name='Polynomials', index=False)
                corr_rows = []
                for col, res in self.corr_results.items():
                    corr_rows.append({'Cylinder': col, 'n': res['n'], 'r': res['r'], 'p': res['p']})
                pd.DataFrame(corr_rows).to_excel(writer, sheet_name='Correlations', index=False)
                pcorr_rows = []
                for col, res in self.partial_corr.items():
                    pcorr_rows.append({'Cylinder': col, 'n': res['n'], 'r': res['r'], 'p': res['p']})
                pd.DataFrame(pcorr_rows).to_excel(writer, sheet_name='PartialCorr', index=False)

            # Сохранение графиков
            self._save_plots()
            if log_callback:
                log_callback(f"Результаты сохранены в {self.output_excel} и {self.plot_dir}")
                log_callback("Анализ завершён успешно!")
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"ОШИБКА: {str(e)}")
            return False

    def _save_plots(self):
        for param in self.params:
            if param not in self.avg_df.columns:
                continue
            x = self.avg_df['R/H'].values
            y = self.avg_df[param].values
            mask = self.filter_masks.get(param, np.ones(len(x), dtype=bool))
            fig, ax = plt.subplots(figsize=(8,5))
            ax.scatter(x[mask], y[mask], color='blue', label='Нормальные')
            ax.scatter(x[~mask], y[~mask], color='red', label='Выбросы')
            if np.any(mask) and len(x[mask]) >= self.poly_deg+1:
                x_valid = x[mask]
                y_valid = y[mask]
                func, _ = polynomial_fit(x_valid, y_valid, self.poly_deg)
                x_sorted = np.sort(x_valid)
                y_fit = func(x_sorted)
                residuals = y_valid - func(x_valid)
                q1 = np.percentile(residuals, 25)
                q3 = np.percentile(residuals, 75)
                iqr = q3 - q1
                lower = y_fit - self.k_iqr * iqr
                upper = y_fit + self.k_iqr * iqr
                ax.plot(x_sorted, y_fit, 'gray', label='Аппроксимация')
                ax.plot(x_sorted, lower, 'r--', label='Нижняя граница')
                ax.plot(x_sorted, upper, 'r--', label='Верхняя граница')
            ax.set_xlabel('R/H')
            ax.set_ylabel(param)
            ax.set_title(f'Фильтрация {param} (k={self.k_iqr})')
            ax.legend()
            plt.tight_layout()
            plt.savefig(os.path.join(self.plot_dir, f'filter_{param}.png'), dpi=150)
            plt.close()

        # Тренды симплекса
        fig, ax = plt.subplots(figsize=(10,6))
        columns = [f'cyl{i}' for i in range(1, self.cylinders+1)] + ['AVG']
        colors = plt.cm.tab10(np.linspace(0, 1, len(columns)))
        for idx, col in enumerate(columns):
            if self.poly_functions.get(col) is not None:
                x = self.simplex_df['R/H'].values
                y = self.simplex_df[col].values
                valid = ~np.isnan(y)
                if np.any(valid):
                    x_plot = np.linspace(min(x[valid]), max(x[valid]), 100)
                    y_plot = self.poly_functions[col](x_plot)
                    ax.plot(x_plot, y_plot, color=colors[idx], label=col)
                    ax.scatter(x[valid], y[valid], color=colors[idx], s=20, alpha=0.5)
        ax.set_xlabel('R/H')
        ax.set_ylabel('Симплекс')
        ax.set_title(f'Тренды симплекса ({self.numerator}/{self.denominator})')
        ax.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(self.plot_dir, 'simplex_trends.png'), dpi=150)
        plt.close()

# ============================================================
#  GUI НА PYQT5
# ============================================================

class AnalysisThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool)

    def __init__(self, file_path, sheet_name, numerator, denominator, poly_deg, k_iqr):
        super().__init__()
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.numerator = numerator
        self.denominator = denominator
        self.poly_deg = poly_deg
        self.k_iqr = k_iqr

    def run(self):
        analyzer = EngineAnalyzer(
            self.file_path, self.sheet_name,
            self.numerator, self.denominator,
            self.poly_deg, self.k_iqr
        )
        success = analyzer.run(log_callback=self.log_signal.emit)
        self.finished_signal.emit(success)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Диагностический анализ двигателя")
        self.setGeometry(100, 100, 1000, 700)

        # Центральный виджет и вкладки
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Вкладки
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Вкладка "Настройки"
        self.settings_tab = QWidget()
        self.tabs.addTab(self.settings_tab, "Настройки")
        self.init_settings_tab()

        # Вкладка "Графики"
        self.plots_tab = QWidget()
        self.tabs.addTab(self.plots_tab, "Графики")
        self.init_plots_tab()

        # Вкладка "Результаты"
        self.results_tab = QWidget()
        self.tabs.addTab(self.results_tab, "Результаты")
        self.init_results_tab()

        # Вкладка "Лог"
        self.log_tab = QWidget()
        self.tabs.addTab(self.log_tab, "Лог")
        self.init_log_tab()

        # Статус-бар
        self.statusBar().showMessage("Готов")

    def init_settings_tab(self):
        layout = QVBoxLayout(self.settings_tab)

        # Группа файла
        file_group = QGroupBox("Исходные данные")
        file_layout = QGridLayout()
        file_group.setLayout(file_layout)

        file_layout.addWidget(QLabel("Файл Excel:"), 0, 0)
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("Выберите файл...")
        file_layout.addWidget(self.file_edit, 0, 1)
        self.file_btn = QPushButton("Обзор...")
        self.file_btn.clicked.connect(self.browse_file)
        file_layout.addWidget(self.file_btn, 0, 2)

        file_layout.addWidget(QLabel("Имя листа:"), 1, 0)
        self.sheet_edit = QLineEdit("DG1")
        file_layout.addWidget(self.sheet_edit, 1, 1)

        # Группа параметров симплекса
        sim_group = QGroupBox("Симплекс")
        sim_layout = QGridLayout()
        sim_group.setLayout(sim_layout)

        sim_layout.addWidget(QLabel("Числитель:"), 0, 0)
        self.num_edit = QLineEdit("Pz")
        sim_layout.addWidget(self.num_edit, 0, 1)

        sim_layout.addWidget(QLabel("Знаменатель:"), 1, 0)
        self.den_edit = QLineEdit("Index")
        sim_layout.addWidget(self.den_edit, 1, 1)

        sim_layout.addWidget(QLabel("Степень полинома (1 или 2):"), 2, 0)
        self.deg_edit = QLineEdit("2")
        sim_layout.addWidget(self.deg_edit, 2, 1)

        sim_layout.addWidget(QLabel("Коэффициент IQR (k):"), 3, 0)
        self.k_edit = QLineEdit("0.9")
        sim_layout.addWidget(self.k_edit, 3, 1)

        # Кнопка запуска
        self.run_btn = QPushButton("Запустить анализ")
        self.run_btn.clicked.connect(self.run_analysis)
        self.run_btn.setStyleSheet("font-weight: bold; background-color: #4CAF50; color: white; padding: 10px;")

        # Добавляем всё в основной layout
        layout.addWidget(file_group)
        layout.addWidget(sim_group)
        layout.addWidget(self.run_btn)
        layout.addStretch()

    def init_plots_tab(self):
        layout = QVBoxLayout(self.plots_tab)
        self.plots_scroll = QScrollArea()
        self.plots_scroll.setWidgetResizable(True)
        self.plots_container = QWidget()
        self.plots_layout = QVBoxLayout(self.plots_container)
        self.plots_scroll.setWidget(self.plots_container)
        layout.addWidget(self.plots_scroll)

    def init_results_tab(self):
        layout = QVBoxLayout(self.results_tab)
        self.results_combo = QComboBox()
        self.results_combo.addItems(["Averages", "Simplex", "Polynomials", "Correlations", "PartialCorr"])
        self.results_combo.currentIndexChanged.connect(self.load_result_sheet)
        layout.addWidget(self.results_combo)

        self.results_table = QTableWidget()
        layout.addWidget(self.results_table)

    def init_log_tab(self):
        layout = QVBoxLayout(self.log_tab)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите Excel-файл", "",
            "Excel files (*.xlsx *.xls)"
        )
        if file_path:
            self.file_edit.setText(file_path)

    def run_analysis(self):
        # Сбор параметров
        file_path = self.file_edit.text().strip()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Ошибка", "Укажите существующий файл Excel.")
            return

        sheet_name = self.sheet_edit.text().strip()
        numerator = self.num_edit.text().strip()
        denominator = self.den_edit.text().strip()
        try:
            poly_deg = int(self.deg_edit.text().strip())
            if poly_deg not in (1, 2):
                raise ValueError
        except:
            QMessageBox.warning(self, "Ошибка", "Степень полинома должна быть 1 или 2.")
            return
        try:
            k_iqr = float(self.k_edit.text().strip())
        except:
            QMessageBox.warning(self, "Ошибка", "Коэффициент IQR должен быть числом.")
            return

        # Очистка лога и графиков
        self.log_text.clear()
        self.clear_plots()

        # Запуск в отдельном потоке
        self.run_btn.setEnabled(False)
        self.statusBar().showMessage("Выполняется анализ...")
        self.thread = AnalysisThread(file_path, sheet_name, numerator, denominator, poly_deg, k_iqr)
        self.thread.log_signal.connect(self.append_log)
        self.thread.finished_signal.connect(self.analysis_finished)
        self.thread.start()

    def append_log(self, message):
        self.log_text.append(message)

    def clear_plots(self):
        # Удаляем все виджеты из контейнера графиков
        for i in reversed(range(self.plots_layout.count())):
            widget = self.plots_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

    def analysis_finished(self, success):
        self.run_btn.setEnabled(True)
        if success:
            self.statusBar().showMessage("Анализ завершён успешно")
            self.load_plots()
            self.load_result_sheet(0)  # загружаем первый лист
            self.tabs.setCurrentIndex(1)  # переключаем на вкладку "Графики"
        else:
            self.statusBar().showMessage("Анализ завершён с ошибкой (см. лог)")

    def load_plots(self):
        # Загружаем PNG из папки plots
        plot_dir = "plots"
        if not os.path.exists(plot_dir):
            return
        png_files = [f for f in os.listdir(plot_dir) if f.endswith('.png')]
        for fname in sorted(png_files):
            label = QLabel()
            pixmap = QPixmap(os.path.join(plot_dir, fname))
            if not pixmap.isNull():
                # Масштабируем под ширину, сохраняя пропорции
                scaled = pixmap.scaledToWidth(800, Qt.SmoothTransformation)
                label.setPixmap(scaled)
                label.setAlignment(Qt.AlignCenter)
                self.plots_layout.addWidget(label)
        # Добавим растяжение снизу
        self.plots_layout.addStretch()

    def load_result_sheet(self, index):
        sheet_name = self.results_combo.currentText()
        excel_path = "results.xlsx"
        if not os.path.exists(excel_path):
            return
        try:
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
        except:
            return
        self.results_table.setRowCount(df.shape[0])
        self.results_table.setColumnCount(df.shape[1])
        self.results_table.setHorizontalHeaderLabels(df.columns.astype(str))
        for i, row in df.iterrows():
            for j, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                self.results_table.setItem(i, j, item)
        self.results_table.resizeColumnsToContents()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())