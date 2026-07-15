import pandas as pd
import numpy as np
from scipy.stats import pearsonr
import matplotlib.pyplot as plt
import os
import re
import warnings
warnings.filterwarnings('ignore')

# ============================================================
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

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
        return np.ones(len(x), dtype=bool), None, None, None, None, None, None
    func, _ = polynomial_fit(x, y, deg)
    y_fit = func(x)
    residuals = y - y_fit
    q1 = np.percentile(residuals, 25)
    q3 = np.percentile(residuals, 75)
    iqr = q3 - q1
    lower_bound = q1 - k * iqr
    upper_bound = q3 + k * iqr
    mask = (residuals >= lower_bound) & (residuals <= upper_bound)
    return mask, func, q1, q3, iqr, lower_bound, upper_bound

def evaluate_simplex(expr, values):
    try:
        expr_lower = expr.lower()
        safe_dict = {k: v for k, v in values.items()}
        result = eval(expr_lower, {"__builtins__": {}}, safe_dict)
        return float(result)
    except:
        return np.nan

# ============================================================
#  ОСНОВНОЙ КЛАСС АНАЛИЗАТОРА
# ============================================================

class EngineAnalyzer:
    def __init__(self, file_path, sheet_name, numerator, denominator, poly_deg, k_iqr=None, k_params=None):
        """
        k_iqr: общий коэффициент, если None – используются индивидуальные из k_params
        k_params: словарь {param: k} для каждого параметра
        """
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.numerator = numerator
        self.denominator = denominator
        self.poly_deg = poly_deg
        self.k_iqr = k_iqr
        self.k_params = k_params if k_params else {}
        self.df = None
        self.params = []
        self.cylinders = 0
        self.blocks = []
        self.avg_df = None
        self.filter_masks = {}
        self.filter_params = {}
        self.clean_indices = None
        self.simplex_df = None
        self.poly_results = {}
        self.poly_functions = {}
        self.corr_results = {}
        self.partial_corr = {}
        self.output_excel = "results.xlsx"
        self.plot_dir = "plots"

    def _get_k_for_param(self, param):
        if self.k_iqr is not None:
            return self.k_iqr
        return self.k_params.get(param, 1.0)

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

            # Фильтрация с индивидуальными k
            self.filter_masks = {}
            self.filter_params = {}
            all_good = np.ones(len(self.avg_df), dtype=bool)
            for param in self.params:
                k = self._get_k_for_param(param)
                x = self.avg_df['R/H'].values
                y = self.avg_df[param].values
                valid = ~np.isnan(y)
                x_valid = x[valid]
                y_valid = y[valid]
                if len(x_valid) < 3:
                    mask = np.ones(len(y), dtype=bool)
                    self.filter_params[param] = {'func': None, 'q1': None, 'q3': None, 'iqr': None, 'k': k}
                else:
                    mask, func, q1, q3, iqr, _, _ = filter_outliers(x_valid, y_valid, self.poly_deg, k)
                    self.filter_params[param] = {
                        'func': func,
                        'q1': q1,
                        'q3': q3,
                        'iqr': iqr,
                        'k': k,
                        'x': x_valid,
                        'y': y_valid
                    }
                    full_mask = np.zeros(len(y), dtype=bool)
                    full_mask[valid] = mask
                    mask = full_mask
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
        # Графики фильтрации для каждого параметра
        for param in self.params:
            if param not in self.avg_df.columns:
                continue
            x = self.avg_df['R/H'].values
            y = self.avg_df[param].values
            mask = self.filter_masks.get(param, np.ones(len(x), dtype=bool))
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.scatter(x[mask], y[mask], color='blue', s=60, alpha=0.7, label=f'Нормальные (n={np.sum(mask)})')
            ax.scatter(x[~mask], y[~mask], color='red', s=80, alpha=0.8, label=f'Выбросы (n={np.sum(~mask)})')
            params = self.filter_params.get(param)
            if params is not None and params['func'] is not None:
                func = params['func']
                q1 = params['q1']
                q3 = params['q3']
                iqr = params['iqr']
                k = params['k']
                x_sorted = np.sort(x)
                y_fit = func(x_sorted)
                lower = y_fit + (q1 - k * iqr)
                upper = y_fit + (q3 + k * iqr)
                ax.plot(x_sorted, y_fit, 'gray', linewidth=2, label='Аппроксимация')
                ax.plot(x_sorted, lower, 'r--', linewidth=1.5, label='Нижняя граница')
                ax.plot(x_sorted, upper, 'r--', linewidth=1.5, label='Верхняя граница')
            ax.set_xlabel('R/H', fontsize=12)
            ax.set_ylabel(param, fontsize=12)
            ax.set_title(f'Фильтрация {param} (k={self._get_k_for_param(param)})', fontsize=14)
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.legend(fontsize=10)
            plt.tight_layout()
            plt.savefig(os.path.join(self.plot_dir, f'filter_{param}.png'), dpi=150)
            plt.close()

        # График трендов симплекса – только линии аппроксимации
        fig, ax = plt.subplots(figsize=(12, 7))
        columns = [f'cyl{i}' for i in range(1, self.cylinders+1)] + ['AVG']
        colors = plt.cm.tab10(np.linspace(0, 1, len(columns)))
        for idx, col in enumerate(columns):
            if self.poly_functions.get(col) is not None:
                x = self.simplex_df['R/H'].values
                y = self.simplex_df[col].values
                valid = ~np.isnan(y)
                n_points = np.sum(valid)
                if n_points == 0:
                    continue
                x_plot = np.linspace(min(x[valid]), max(x[valid]), 100)
                y_plot = self.poly_functions[col](x_plot)
                ax.plot(x_plot, y_plot, color=colors[idx], linewidth=2.5, label=f'{col} (n={n_points})')
        ax.set_xlabel('R/H', fontsize=12)
        ax.set_ylabel('Симплекс', fontsize=12)
        ax.set_title(f'Тренды симплекса ({self.numerator}/{self.denominator})', fontsize=14)
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.legend(fontsize=10)
        plt.tight_layout()
        plt.savefig(os.path.join(self.plot_dir, 'simplex_trends.png'), dpi=150)
        plt.close()
