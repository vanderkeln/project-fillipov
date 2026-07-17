import pandas as pd
import numpy as np
from scipy.stats import pearsonr
import matplotlib.pyplot as plt
import os
import re
import warnings
warnings.filterwarnings("ignore")

def get_sheet_names(file_path):
    try:
        xl = pd.ExcelFile(file_path)
        return xl.sheet_names
    except Exception:
        return []

def read_data(file_path, sheet_name=None):
    if sheet_name is None or sheet_name.strip() == "":
        sheet_names = get_sheet_names(file_path)
        if sheet_names:
            sheet_name = sheet_names[0]
        else:
            raise ValueError("Не удалось найти ни одного листа в файле.")
    try:
        df = pd.read_excel(file_path, sheet_name=sheet_name, header=0)
    except Exception:
        sheet_names = get_sheet_names(file_path)
        if sheet_names:
            sheet_name = sheet_names[0]
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=0)
        else:
            raise ValueError("Не удалось прочитать файл. Проверьте, что файл содержит данные.")
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = df.columns.str.strip()
    new_cols = []
    for col in df.columns:
        if "cyl" in col.lower():
            num = re.search(r"\d+", col)
            if num:
                new_cols.append(f"cyl{num.group()}")
            else:
                new_cols.append(col)
        else:
            new_cols.append(col)
    df.columns = new_cols
    return df, sheet_name

def detect_cylinders(df):
    return len([col for col in df.columns if col.startswith("cyl")])

def detect_parameters(df):
    if "parameters" not in df.columns:
        raise KeyError("В таблице нет столбца 'parameters'")
    params = df["parameters"].dropna().unique()
    params = [str(p).strip().lower() for p in params if isinstance(p, str)]
    return params

def group_blocks(df, params):
    blocks = []
    n_params = len(params)
    idx_params = df[df["parameters"].notna()].index.tolist()
    for i in range(0, len(idx_params), n_params):
        start = idx_params[i]
        if i + n_params <= len(idx_params):
            block = df.iloc[start:start+n_params].copy()
            blocks.append(block)
    return blocks

def average_block(block, params, cyl_cols):
    avg_dict = {}
    date_val = block.iloc[0]["DATE"] if "DATE" in block.columns else None
    rh_val = block.iloc[0]["R/H"] if "R/H" in block.columns else None
    for p in params:
        row = block[block["parameters"].str.lower() == p]
        if not row.empty:
            vals = row[cyl_cols].values.flatten()
            vals_num = [float(v) for v in vals if pd.notna(v) and v != 0]
            avg_dict[p] = np.mean(vals_num) if vals_num else 0.0
        else:
            avg_dict[p] = 0.0
    return date_val, rh_val, avg_dict

def polyfit_vba(x, y, deg):
    n = len(x)
    if deg == 1:
        m = 2
    elif deg == 2:
        m = 3
    else:
        raise ValueError("deg должен быть 1 или 2")

    x_pow = np.zeros(2*deg + 1)
    for i in range(2*deg + 1):
        x_pow[i] = np.sum(x**i)

    A = np.zeros((m, m))
    b = np.zeros(m)
    for r in range(m):
        for c in range(m):
            A[r, c] = x_pow[r + c]
        b[r] = np.sum((x**r) * y)

    aug = np.hstack([A, b.reshape(-1, 1)])
    for col in range(m):
        pivot = np.argmax(np.abs(aug[col:, col])) + col
        if pivot != col:
            aug[[col, pivot]] = aug[[pivot, col]]
        if aug[col, col] != 0:
            aug[col] = aug[col] / aug[col, col]
        for row in range(m):
            if row != col and aug[row, col] != 0:
                factor = aug[row, col]
                aug[row] = aug[row] - factor * aug[col]
    coeffs = aug[:, -1]
    return coeffs

def percentile_vba(data, p):
    n = len(data)
    if n == 0:
        return np.nan
    if p < 0 or p > 1:
        raise ValueError("p должно быть от 0 до 1")
    pos = p * (n + 1)
    idx = int(pos) - 1
    frac = pos - int(pos)
    if idx < 0:
        return data[0]
    if idx >= n - 1:
        return data[-1]
    return data[idx] + frac * (data[idx+1] - data[idx])

def filter_outliers_vba(x, y, deg, k):
    if len(x) < 3:
        return np.ones(len(x), dtype=bool), None, None, None, None, None, None, None, None

    coeffs = polyfit_vba(x, y, deg)
    y_fit = np.polyval(coeffs[::-1], x)
    residuals = y - y_fit

    sorted_res = np.sort(residuals)
    q1 = percentile_vba(sorted_res, 0.25)
    q3 = percentile_vba(sorted_res, 0.75)
    iqr = q3 - q1

    lower_delta = -k * iqr
    upper_delta = k * iqr

    mask = (residuals >= lower_delta) & (residuals <= upper_delta)

    return mask, coeffs, q1, q3, iqr, lower_delta, upper_delta, residuals

def evaluate_simplex(expr, values):
    try:
        expr_lower = expr.lower()
        safe_dict = {k: v for k, v in values.items()}
        result = eval(expr_lower, {"__builtins__": {}}, safe_dict)
        return float(result)
    except Exception:
        return np.nan

class EngineAnalyzer:
    def __init__(
        self,
        file_path,
        sheet_name,
        numerator,
        denominator,
        poly_deg,
        k_iqr=None,
        k_params=None,
        lang="ru",
        translate_func=None,
        apply_filter=True,
    ):
        self.file_path = file_path
        self.sheet_name = sheet_name
        self.numerator = numerator
        self.denominator = denominator
        self.poly_deg = poly_deg
        self.k_iqr = k_iqr
        self.k_params = k_params if k_params else {}
        self.lang = lang
        self.translate_func = translate_func
        self.apply_filter = apply_filter
        self.df = None
        self.params = []
        self.cylinders = 0
        self.blocks = []
        self.avg_df = None
        self.clean_avg_df = None
        self.filter_masks = {}
        self.filter_params = {}
        self.clean_indices = None
        self.simplex_df = None
        self.poly_results = {}
        self.poly_functions = {}
        self.corr_results = {}
        self.corr_params_all = {}
        self.corr_scatter_data_all = {}
        self.corr_params_clean = {}
        self.corr_scatter_data_clean = {}
        self.partial_corr = {}
        self.output_excel = "results.xlsx"
        self.plot_dir = "plots"
        self.used_sheet_name = None

    def _get_k_for_param(self, param):
        if self.k_iqr is not None:
            return self.k_iqr
        return self.k_params.get(param, 1.0)

    def _translate_header(self, text):
        if self.translate_func is not None:
            translated = self.translate_func(text, self.lang)
            if self.lang != "ru" and translated != text:
                return f"{translated} ({text})"
        return text

    def run(self, log_callback=None):
        try:
            if log_callback:
                log_callback("Загрузка данных...")
            self.df, self.used_sheet_name = read_data(self.file_path, self.sheet_name)
            if log_callback:
                log_callback(f"Используется лист: {self.used_sheet_name}")
            self.cylinders = detect_cylinders(self.df)
            self.params = detect_parameters(self.df)
            if log_callback:
                log_callback(f"Обнаружено цилиндров: {self.cylinders}")
                log_callback(f"Обнаружены параметры: {self.params}")
            self.blocks = group_blocks(self.df, self.params)
            if log_callback:
                log_callback(f"Всего блоков: {len(self.blocks)}")
            cyl_cols = [f"cyl{i}" for i in range(1, self.cylinders + 1)]
            rows = []
            for block in self.blocks:
                _, rh, avg_dict = average_block(block, self.params, cyl_cols)
                row = {"R/H": rh}
                row.update(avg_dict)
                rows.append(row)
            self.avg_df = pd.DataFrame(rows)
            if log_callback:
                log_callback("Средние значения вычислены.")

            if self.apply_filter:
                self.filter_masks = {}
                self.filter_params = {}
                all_good = np.ones(len(self.avg_df), dtype=bool)
                for param in self.params:
                    k = self._get_k_for_param(param)
                    x = self.avg_df["R/H"].values
                    y = self.avg_df[param].values
                    valid = ~np.isnan(y)
                    x_valid = x[valid]
                    y_valid = y[valid]
                    if len(x_valid) < 3:
                        mask = np.ones(len(y), dtype=bool)
                        self.filter_params[param] = {"coeffs": None, "q1": None, "q3": None, "iqr": None, "k": k,
                                                    "lower_delta": None, "upper_delta": None}
                    else:
                        mask, coeffs, q1, q3, iqr, lower_delta, upper_delta, residuals = filter_outliers_vba(
                            x_valid, y_valid, self.poly_deg, k
                        )
                        self.filter_params[param] = {
                            "coeffs": coeffs,
                            "q1": q1,
                            "q3": q3,
                            "iqr": iqr,
                            "k": k,
                            "lower_delta": lower_delta,
                            "upper_delta": upper_delta,
                            "residuals": residuals,
                            "x": x_valid,
                            "y": y_valid,
                        }
                        full_mask = np.zeros(len(y), dtype=bool)
                        full_mask[valid] = mask
                        mask = full_mask
                    self.filter_masks[param] = mask
                    self.avg_df[f"{param}_flag"] = (~mask).astype(int)
                    all_good &= mask
                self.clean_indices = all_good
                self.clean_avg_df = self.avg_df[all_good].copy()
                if log_callback:
                    log_callback(f"После фильтрации осталось {np.sum(all_good)} блоков из {len(self.avg_df)}.")
            else:
                self.clean_indices = np.ones(len(self.avg_df), dtype=bool)
                self.clean_avg_df = self.avg_df.copy()
                for param in self.params:
                    self.avg_df[f"{param}_flag"] = 0
                if log_callback:
                    log_callback("Фильтрация выключена, используются все блоки.")

            self.corr_params_all = {}
            self.corr_scatter_data_all = {}
            if len(self.avg_df) >= 3:
                x_rh = self.avg_df["R/H"].values
                for param in self.params:
                    y_vals = self.avg_df[param].values
                    valid = ~np.isnan(y_vals)
                    if np.sum(valid) >= 3:
                        r, p = pearsonr(x_rh[valid], y_vals[valid])
                        self.corr_params_all[param.upper()] = {"r": r, "p": p, "n": np.sum(valid)}
                        self.corr_scatter_data_all[param.upper()] = {"x": x_rh[valid], "y": y_vals[valid]}

            self.corr_params_clean = {}
            self.corr_scatter_data_clean = {}
            if len(self.clean_avg_df) >= 3:
                x_rh = self.clean_avg_df["R/H"].values
                for param in self.params:
                    y_vals = self.clean_avg_df[param].values
                    valid = ~np.isnan(y_vals)
                    if np.sum(valid) >= 3:
                        r, p = pearsonr(x_rh[valid], y_vals[valid])
                        self.corr_params_clean[param.upper()] = {"r": r, "p": p, "n": np.sum(valid)}
                        self.corr_scatter_data_clean[param.upper()] = {"x": x_rh[valid], "y": y_vals[valid]}

            rows_simplex = []
            for idx, block in enumerate(self.blocks):
                if not self.clean_indices[idx]:
                    continue
                param_values = {}
                for p in self.params:
                    row = block[block["parameters"].str.lower() == p]
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
                rh = block.iloc[0]["R/H"] if "R/H" in block.columns else np.nan
                row = {"R/H": rh}
                for i, val in enumerate(cyl_simplex):
                    row[f"cyl{i+1}"] = val
                row["AVG"] = avg_simplex
                rows_simplex.append(row)
            self.simplex_df = pd.DataFrame(rows_simplex)
            if log_callback:
                log_callback(f"Симплекс вычислен для {len(self.simplex_df)} блоков.")

            if not self.simplex_df.empty:
                x_sim = self.simplex_df["R/H"].values
                y_sim = self.simplex_df["AVG"].values
                valid = ~np.isnan(y_sim)
                if np.sum(valid) >= 3:
                    r, p = pearsonr(x_sim[valid], y_sim[valid])
                    self.corr_params_all["Simplex AVG"] = {"r": r, "p": p, "n": np.sum(valid)}
                    self.corr_scatter_data_all["Simplex AVG"] = {"x": x_sim[valid], "y": y_sim[valid]}
                    self.corr_params_clean["Simplex AVG"] = {"r": r, "p": p, "n": np.sum(valid)}
                    self.corr_scatter_data_clean["Simplex AVG"] = {"x": x_sim[valid], "y": y_sim[valid]}

            columns = [f"cyl{i}" for i in range(1, self.cylinders + 1)] + ["AVG"]
            for col in columns:
                x = self.simplex_df["R/H"].values
                y = self.simplex_df[col].values
                valid = ~np.isnan(y)
                x_valid = x[valid]
                y_valid = y[valid]
                if len(x_valid) < self.poly_deg + 1:
                    self.poly_results[col] = None
                    self.poly_functions[col] = None
                    continue
                coeffs = polyfit_vba(x_valid, y_valid, self.poly_deg)
                self.poly_results[col] = coeffs
                self.poly_functions[col] = lambda xp, c=coeffs: np.polyval(c[::-1], xp)
            if log_callback:
                log_callback("Полиномиальная аппроксимация выполнена.")

            for col in columns:
                x = self.simplex_df["R/H"].values
                y = self.simplex_df[col].values
                valid = ~np.isnan(y)
                x_clean = x[valid]
                y_clean = y[valid]
                if len(x_clean) < 3:
                    self.corr_results[col] = {"n": len(x_clean), "r": np.nan, "p": np.nan}
                else:
                    r, p = pearsonr(x_clean, y_clean)
                    self.corr_results[col] = {"n": len(x_clean), "r": r, "p": p}
            if log_callback:
                log_callback("Корреляции симплекса вычислены.")

            idx_col = None
            for col in self.avg_df.columns:
                if col.lower() == "index":
                    idx_col = col
                    break
            if idx_col is not None:
                x_rh = self.avg_df.loc[self.clean_indices, "R/H"].values
                x_index = self.avg_df.loc[self.clean_indices, idx_col].values
                for col in columns:
                    y = self.simplex_df[col].values
                    rh_clean, idx_clean, y_clean = [], [], []
                    for i in range(len(y)):
                        if not np.isnan(y[i]) and not np.isnan(x_index[i]) and not np.isnan(x_rh[i]):
                            rh_clean.append(x_rh[i])
                            idx_clean.append(x_index[i])
                            y_clean.append(y[i])
                    if len(rh_clean) < 4:
                        self.partial_corr[col] = {"n": len(rh_clean), "r": np.nan, "p": np.nan}
                        continue
                    slope, intercept = np.polyfit(idx_clean, y_clean, 1)
                    residuals = y_clean - (slope * np.array(idx_clean) + intercept)
                    r, p = pearsonr(rh_clean, residuals)
                    self.partial_corr[col] = {"n": len(rh_clean), "r": r, "p": p}
                if log_callback:
                    log_callback("Частные корреляции вычислены.")
            else:
                if log_callback:
                    log_callback("Предупреждение: столбец Index не найден, частная корреляция пропущена.")
                self.partial_corr = {}

            os.makedirs(self.plot_dir, exist_ok=True)
            with pd.ExcelWriter(self.output_excel, engine="openpyxl") as writer:
                df_avg = self.avg_df.copy()
                header_map_avg = {
                    "R/H": self._translate_header("R/H"),
                    "DATE": self._translate_header("Date"),
                }
                for param in self.params:
                    header_map_avg[param] = param.upper()
                    header_map_avg[f"{param}_flag"] = self._translate_header(f"{param.upper()} Flag")
                df_avg.rename(columns=header_map_avg, inplace=True)
                df_avg.to_excel(writer, sheet_name="Averages", index=False)

                if not self.simplex_df.empty:
                    df_sim = self.simplex_df.copy()
                    header_map_sim = {
                        "R/H": self._translate_header("R/H"),
                        "AVG": self._translate_header("Average"),
                    }
                    for i in range(1, self.cylinders + 1):
                        header_map_sim[f"cyl{i}"] = self._translate_header(f"Cylinder {i}")
                    df_sim.rename(columns=header_map_sim, inplace=True)
                    df_sim.to_excel(writer, sheet_name="Simplex", index=False)

                poly_rows = []
                for col, coeffs in self.poly_results.items():
                    if coeffs is not None:
                        row = {"Cylinder": self._translate_header(col)}
                        for i, c in enumerate(coeffs[::-1]):
                            row[f"a{i}"] = c
                        poly_rows.append(row)
                if poly_rows:
                    df_poly = pd.DataFrame(poly_rows)
                    df_poly.rename(columns={"Cylinder": self._translate_header("Cylinder")}, inplace=True)
                    df_poly.to_excel(writer, sheet_name="Polynomials", index=False)

                corr_rows = []
                for col, res in self.corr_results.items():
                    corr_rows.append({
                        "Cylinder": self._translate_header(col),
                        "n": res["n"],
                        "r": res["r"],
                        "p": res["p"],
                    })
                if corr_rows:
                    df_corr = pd.DataFrame(corr_rows)
                    header_map_corr = {
                        "Cylinder": self._translate_header("Cylinder"),
                        "n": self._translate_header("n"),
                        "r": self._translate_header("r"),
                        "p": self._translate_header("p-value"),
                    }
                    df_corr.rename(columns=header_map_corr, inplace=True)
                    df_corr.to_excel(writer, sheet_name="Correlations", index=False)

                pcorr_rows = []
                for col, res in self.partial_corr.items():
                    pcorr_rows.append({
                        "Cylinder": self._translate_header(col),
                        "n": res["n"],
                        "r": res["r"],
                        "p": res["p"],
                    })
                if pcorr_rows:
                    df_pcorr = pd.DataFrame(pcorr_rows)
                    header_map_pcorr = {
                        "Cylinder": self._translate_header("Cylinder"),
                        "n": self._translate_header("n"),
                        "r": self._translate_header("r (partial)"),
                        "p": self._translate_header("p-value"),
                    }
                    df_pcorr.rename(columns=header_map_pcorr, inplace=True)
                    df_pcorr.to_excel(writer, sheet_name="PartialCorr", index=False)

            self._save_plots()
            if log_callback:
                log_callback("Результаты сохранены в results.xlsx и plots")
                log_callback("Анализ завершён успешно.")
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"ОШИБКА: {str(e)}")
            return False

    def _save_plots(self):
        def translate(text):
            if self.translate_func is not None:
                return self.translate_func(text, self.lang)
            return text
        labels = {
            "normal": "Нормальные",
            "outlier": "Выбросы",
            "fit": "Аппроксимация",
            "lower": "Нижняя граница",
            "upper": "Верхняя граница",
            "filter_title": "Фильтрация",
            "trend_title": "Тренды симплекса",
            "xlabel": "R/H",
            "ylabel": "Симплекс",
        }
        translated = {k: translate(v) for k, v in labels.items()}
        for param in self.params:
            if param not in self.avg_df.columns:
                continue
            x = self.avg_df["R/H"].values
            y = self.avg_df[param].values
            mask = self.filter_masks.get(param, np.ones(len(x), dtype=bool))
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.scatter(
                x[mask],
                y[mask],
                color="blue",
                s=60,
                alpha=0.7,
                label=f'{translated["normal"]} (n={np.sum(mask)})',
            )
            ax.scatter(
                x[~mask],
                y[~mask],
                color="red",
                s=80,
                alpha=0.8,
                label=f'{translated["outlier"]} (n={np.sum(~mask)})',
            )
            params = self.filter_params.get(param)
            if params is not None and params["coeffs"] is not None:
                coeffs = params["coeffs"]
                lower_delta = params["lower_delta"]
                upper_delta = params["upper_delta"]
                x_sorted = np.sort(x)
                y_fit = np.polyval(coeffs[::-1], x_sorted)
                lower = y_fit + lower_delta
                upper = y_fit + upper_delta
                ax.plot(x_sorted, y_fit, "gray", linewidth=2, label=translated["fit"])
                ax.plot(x_sorted, lower, "r--", linewidth=1.5, label=translated["lower"])
                ax.plot(x_sorted, upper, "r--", linewidth=1.5, label=translated["upper"])
            ax.set_xlabel(translated["xlabel"], fontsize=12)
            ax.set_ylabel(param, fontsize=12)
            ax.set_title(
                f'{translated["filter_title"]} {param} (k={self._get_k_for_param(param)})', fontsize=14
            )
            ax.grid(True, linestyle="--", alpha=0.6)
            ax.legend(fontsize=10)
            plt.tight_layout()
            plt.savefig(os.path.join(self.plot_dir, f"filter_{param}.png"), dpi=150)
            plt.close()
        fig, ax = plt.subplots(figsize=(12, 7))
        columns = [f"cyl{i}" for i in range(1, self.cylinders + 1)] + ["AVG"]
        colors = plt.cm.tab10(np.linspace(0, 1, len(columns)))
        for idx, col in enumerate(columns):
            if self.poly_functions.get(col) is not None:
                func = self.poly_functions[col]
                x = self.simplex_df["R/H"].values
                y = self.simplex_df[col].values
                valid = ~np.isnan(y)
                n_points = np.sum(valid)
                if n_points == 0:
                    continue
                x_plot = np.linspace(min(x[valid]), max(x[valid]), 100)
                y_plot = func(x_plot)
                ax.plot(
                    x_plot,
                    y_plot,
                    color=colors[idx],
                    linewidth=2.5,
                    label=f"{col} (n={n_points})",
                )
        ax.set_xlabel(translated["xlabel"], fontsize=12)
        ax.set_ylabel(translated["ylabel"], fontsize=12)
        ax.set_title(
            f'{translated["trend_title"]} ({self.numerator}/{self.denominator})', fontsize=14
        )
        ax.grid(True, linestyle="--", alpha=0.6)
        ax.legend(fontsize=10)
        plt.tight_layout()
        plt.savefig(os.path.join(self.plot_dir, "simplex_trends.png"), dpi=150)
        plt.close()
