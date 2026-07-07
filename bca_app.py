import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import tempfile
import re

st.set_page_config(page_title='BCA Plate Analysis', layout='wide')


# ─── Stage 1: Parse the file and pull out raw standard absorbances ───────────

def parse_standards(absorbance_path: str, config_path: str = None, std_cols: list = None):
    """Reads the absorbance file and returns everything needed later, plus the
    raw (sorted) standard concentration/absorbance arrays for the user to edit."""
    df = pd.read_excel(absorbance_path, header=None)

    # --- Defaults ---
    conc_list = [2000, 1500, 1000, 750, 500, 250, 125, 25, 0]
    sample_names = []
    dilution_factor = 8.0
    loading_protein = 30.0
    loading_volume = None  # None = not provided by user

    # --- Optional config file ---
    if config_path:
        try:
            config_df = pd.read_excel(config_path)
            if 'Standard Concentration (\u00b5g/ml)' in config_df.columns:
                temp_conc = config_df['Standard Concentration (\u00b5g/ml)'].dropna().tolist()
                if temp_conc:
                    conc_list = temp_conc
            if 'Sample Names' in config_df.columns:
                temp_names = config_df['Sample Names'].dropna().tolist()
                if temp_names:
                    sample_names = temp_names
            if 'Parameter' in config_df.columns and 'Value' in config_df.columns:
                params_df = config_df[config_df['Parameter'].isin(
                    ['dilution_factor', 'loading_protein', 'loading_volume']
                )]
                for _, row in params_df.iterrows():
                    if row['Parameter'] == 'dilution_factor':
                        dilution_factor = float(row['Value'])
                    elif row['Parameter'] == 'loading_protein':
                        loading_protein = float(row['Value'])
                    elif row['Parameter'] == 'loading_volume':
                        loading_volume = float(row['Value'])
        except Exception:
            pass

    # --- Detect numeric header row ---
    header_like = False
    try:
        first_row_vals = df.iloc[0, 1:20].values.tolist()
        int_like = sum(
            1 for v in first_row_vals
            if re.match(r'^\s*\d+(?:\.0+)?\s*$', str(v).strip())
        )
        if int_like >= max(3, int(0.6 * len(first_row_vals))):
            header_like = True
    except Exception:
        pass

    try:
        first_data_label = str(df.iloc[1, 0]).strip()
        if len(first_data_label) == 1 and first_data_label.isalpha():
            header_like = True
    except Exception:
        pass

    base = 1 if header_like else 0

    if std_cols is None:
        std_cols = [1, 2]

    n_stds = len(conc_list)

    # --- Read standard absorbances ---
    try:
        if n_stds >= 9:
            std_block = df.iloc[base: base + 8, std_cols]
            physical_std_count = std_block.dropna(how='all').shape[0]
            standards = std_block.mean(axis=1).values
            if df.shape[1] > 4:
                try:
                    de_vals = pd.to_numeric(
                        pd.Series(df.iloc[base, [3, 4]].values), errors='coerce'
                    ).dropna()
                    de_val = float(de_vals.mean()) if not de_vals.empty else np.nan
                except Exception:
                    de_val = np.nan
                standards = np.concatenate([standards, [de_val]])
            else:
                standards = np.concatenate([standards, [np.nan]])
        else:
            std_block = df.iloc[base: base + n_stds, std_cols]
            physical_std_count = std_block.dropna(how='all').shape[0]
            standards = std_block.mean(axis=1).values

        nan_idx = np.where(np.isnan(standards))[0]
        if nan_idx.size > 0 and df.shape[1] > 4:
            for idx in nan_idx:
                row = base + int(idx) if idx < 8 else base
                try:
                    de_numeric = pd.to_numeric(
                        pd.Series(df.iloc[row, [3, 4]].values), errors='coerce'
                    )
                    if not de_numeric.dropna().empty:
                        standards[idx] = float(de_numeric.mean())
                except Exception:
                    pass
    except Exception as e:
        raise ValueError(f'Failed reading standard block: {e}')

    if len(standards) != n_stds or np.isnan(standards).any():
        missing = [i for i, v in enumerate(standards) if np.isnan(v)]
        raise ValueError(
            f'Expected {n_stds} standards, got valid values for '
            f'{n_stds - len(missing)}. Missing indices: {missing}. '
            f'Check the absorbance and config files and the chosen standard columns.'
        )

    conc_arr = np.array(conc_list, dtype=float)
    std_arr = np.array(standards, dtype=float)

    order = np.argsort(conc_arr)
    conc_sorted = conc_arr[order]
    std_sorted = std_arr[order]

    return {
        'df': df,
        'base': base,
        'physical_std_count': int(physical_std_count),
        'conc_sorted': conc_sorted,
        'std_sorted': std_sorted,
        'dilution_factor': dilution_factor,
        'loading_protein': loading_protein,
        'loading_volume': loading_volume,
        'sample_names': sample_names,
    }


# ─── Stage 2: Fit the (possibly edited) standards and compute sample volumes ──

def run_analysis(
    df: pd.DataFrame,
    base: int,
    used_conc: np.ndarray,
    used_std: np.ndarray,
    all_conc: np.ndarray,
    all_std: np.ndarray,
    physical_std_count: int,
    dilution_factor: float,
    loading_volume,
    loading_protein: float,
    dilution_override: float = None,
    total_volume_override: float = None,
    round_digits: int = 6,
    target_ug_override: float = None,
    sample_names_override: list = None,
    multiplier: float = 2.0,
):
    # --- UI overrides ---
    if dilution_override is not None:
        try:
            dilution_factor = float(dilution_override)
        except Exception:
            pass

    if total_volume_override is not None:
        try:
            loading_volume = float(total_volume_override)
        except Exception:
            pass

    has_loading_volume = loading_volume is not None

    if used_conc.size < 2:
        raise ValueError('Not enough standards included to fit a line (need >= 2).')

    # --- Linear regression ---
    coeffs = np.polyfit(used_conc, used_std, 1)
    slope = float(coeffs[0])
    intercept = float(coeffs[1])

    rd = int(round_digits)
    slope_rounded = round(slope, rd)
    intercept_rounded = round(intercept, rd)

    preds = slope * used_conc + intercept
    ss_res = np.sum((used_std - preds) ** 2)
    ss_tot = np.sum((used_std - np.mean(used_std)) ** 2)
    r_squared = float(1.0 - ss_res / ss_tot) if ss_tot != 0 else 0.0

    # --- Standard curve figure ---
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(used_conc, used_std, color='blue', label='Standards used in fit')

    # Show excluded points (present in all_conc/all_std but not used_conc/used_std) in grey
    used_pairs = set(zip(np.round(used_conc, 6), np.round(used_std, 6)))
    excluded_mask = np.array([
        (round(c, 6), round(s, 6)) not in used_pairs for c, s in zip(all_conc, all_std)
    ])
    if excluded_mask.any():
        ax.scatter(
            all_conc[excluded_mask], all_std[excluded_mask],
            color='lightgray', label='Excluded points', marker='x'
        )

    x_line = np.linspace(float(np.min(used_conc)), float(np.max(used_conc)), 100)
    y_line = slope_rounded * x_line + intercept_rounded
    ax.plot(
        x_line, y_line, '--r',
        label=f'y = {slope_rounded:.{rd}f}x + {intercept_rounded:.{rd}f}\nR2 = {r_squared:.4f}'
    )
    for xc, yc in zip(all_conc, all_std):
        ax.annotate(
            f"{int(xc)}", (xc, yc),
            textcoords='offset points', xytext=(4, 4), fontsize=8, color='black'
        )
    x_padding = max(1.0, (float(np.max(all_conc)) - float(np.min(all_conc))) * 0.03)
    ax.set_xlim(float(np.min(all_conc)) - x_padding, float(np.max(all_conc)) + x_padding)
    ax.set_xlabel('Concentration (ug/ml)')
    ax.set_ylabel('Absorbance')
    ax.set_title('BCA Standard Curve')
    ax.legend()
    ax.grid(True, alpha=0.3)

    def calc_concentration(abs_value):
        return (abs_value - intercept_rounded) / slope_rounded

    def col_letter(idx: int) -> str:
        idx0 = int(idx)
        letters = ''
        while idx0 >= 0:
            letters = chr(ord('A') + (idx0 % 26)) + letters
            idx0 = idx0 // 26 - 1
        return letters

    # --- Multiplier label ---
    try:
        mx_label = f"{int(multiplier)}X" if float(multiplier).is_integer() else f"{multiplier}X"
    except Exception:
        mx_label = 'NX'

    # --- Read samples ---
    sample_start = base + 1
    sample_col_pairs = [(3, 4), (5, 6), (7, 8), (9, 10)]
    results = []
    sample_index = 0
    names_provided = bool(sample_names_override)

    target_ug = loading_protein if target_ug_override is None else float(target_ug_override)

    for c1, c2 in sample_col_pairs:
        if names_provided and sample_index >= len(sample_names_override):
            break
        if df.shape[1] <= max(c1, c2):
            continue
        sample_data = df.iloc[sample_start: sample_start + 8, [c1, c2]].dropna(how='all')
        if sample_data.empty:
            continue

        for row_idx, row_vals in sample_data.iterrows():
            vals = pd.to_numeric(pd.Series(row_vals.values), errors='coerce').dropna().values
            if vals.size == 0:
                continue

            abs_mean = float(np.mean(vals))
            conc = calc_concentration(abs_mean)
            conc_with_dilution = conc * dilution_factor
            ug_per_ul = conc_with_dilution / 1000.0

            if not np.isnan(ug_per_ul) and ug_per_ul > 0:
                sample_vol = float(target_ug) / ug_per_ul
            else:
                sample_vol = float('nan')

            if has_loading_volume:
                lv = float(loading_volume)
                sv = min(sample_vol, lv) if not np.isnan(sample_vol) else lv
                buffer_vol = max(0.0, lv - sv)
                vol_nx = multiplier * sv
                buffer_vol_nx = multiplier * buffer_vol
                sds_dye = lv / 5.0
                row = {
                    'Sample': None,
                    'Absorbance': round(abs_mean, 3),
                    'Concentration (ug/ml)': round(float(conc) if not np.isnan(conc) else float('nan'), 2),
                    'ug/ml (with dilution)': round(float(conc_with_dilution) if not np.isnan(conc_with_dilution) else float('nan'), 2),
                    'ug/ul': round(float(ug_per_ul) if not np.isnan(ug_per_ul) else float('nan'), 4),
                    'Sample Volume (ul)': round(sv, 2),
                    'Buffer Volume (ul)': round(buffer_vol, 2),
                    f'{mx_label} Sample Volume (ul)': round(vol_nx, 2),
                    f'{mx_label} Buffer Volume (ul)': round(buffer_vol_nx, 2),
                    '6X SDS Loading Dye (ul)': round(sds_dye, 2),
                }
            else:
                sv_display = round(sample_vol, 2) if not np.isnan(sample_vol) else float('nan')
                row = {
                    'Sample': None,
                    'Absorbance': round(abs_mean, 3),
                    'Concentration (ug/ml)': round(float(conc) if not np.isnan(conc) else float('nan'), 2),
                    'ug/ml (with dilution)': round(float(conc_with_dilution) if not np.isnan(conc_with_dilution) else float('nan'), 2),
                    'ug/ul': round(float(ug_per_ul) if not np.isnan(ug_per_ul) else float('nan'), 4),
                    'Sample Volume (ul)': sv_display,
                    'Buffer Volume (ul)': 'N/A',
                    f'{mx_label} Sample Volume (ul)': 'N/A',
                    f'{mx_label} Buffer Volume (ul)': 'N/A',
                    '6X SDS Loading Dye (ul)': 'N/A',
                }

            if sample_names_override and sample_index < len(sample_names_override):
                candidate = sample_names_override[sample_index].strip()
                if candidate == '':
                    sample_index += 1
                    continue
                sample_name = candidate
            elif sample_names_override is None and sample_index < 0:
                sample_name = ''
            else:
                sample_name = f"{col_letter(c1)}{int(row_idx) + 1}"

            row['Sample'] = sample_name
            results.append(row)
            sample_index += 1

    results_df = pd.DataFrame(results)
    if not results_df.empty:
        cols = ['Sample'] + [c for c in results_df.columns if c != 'Sample']
        results_df = results_df[cols]

    if sample_names_override:
        provided_nonempty = [s.strip() for s in sample_names_override if s and s.strip()]
        if provided_nonempty and not results_df.empty:
            results_df = results_df[results_df['Sample'].isin(set(provided_nonempty))].copy()

    stats_out = {
        'slope': slope,
        'intercept': intercept,
        'slope_rounded': slope_rounded,
        'intercept_rounded': intercept_rounded,
        'r_squared': r_squared,
        'conc_sorted': all_conc.tolist(),
        'std_sorted': all_std.tolist(),
        'used_conc': used_conc.tolist(),
        'used_std': used_std.tolist(),
        'physical_std_count': int(physical_std_count),
        'base': int(base),
        'total_volume': float(loading_volume) if has_loading_volume else None,
        'loading_protein': float(loading_protein),
    }

    return results_df, stats_out, fig


# ─── Streamlit UI ────────────────────────────────────────────────────────────

st.title('BCA Plate Analysis')
st.write('Upload an absorbance Excel file (.xlsx).')

abs_upl = st.file_uploader('Absorbance Excel file (.xlsx)', type=['xlsx'])

# Parse standards as soon as a (new) file is uploaded
if abs_upl is not None:
    if st.session_state.get('uploaded_file_name') != abs_upl.name:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as t_abs:
            t_abs.write(abs_upl.read())
            abs_path = t_abs.name

        st.session_state['uploaded_file_name'] = abs_upl.name
        st.session_state['abs_path'] = abs_path

        try:
            parsed = parse_standards(abs_path, config_path=None, std_cols=[1, 2])
            st.session_state['parsed'] = parsed
            st.session_state['std_editor_df'] = pd.DataFrame({
                'Concentration (ug/ml)': parsed['conc_sorted'],
                'Absorbance': parsed['std_sorted'],
                'Include in fit': [True] * len(parsed['conc_sorted']),
            })
            # clear any previous results since we have a new file
            for k in ('results_df', 'stats_out', 'fig'):
                st.session_state.pop(k, None)
        except Exception as e:
            st.error(f'Failed to parse standards: {e}')
            st.session_state.pop('parsed', None)
            st.session_state.pop('std_editor_df', None)

st.write('Optional: enter dilution factor if your samples were diluted (e.g., 5 for a 1:5 dilution).')
dilution_input = st.number_input('Dilution Factor:', min_value=1.0, value=5.0, step=1.0)

st.write(
    'Optional: choose decimal places to round slope and intercept '
    '(these rounded values are used to compute concentrations).'
)
round_digits = st.number_input(
    'Decimal places for slope/intercept:', min_value=0, max_value=10, value=6, step=1
)

st.write(
    'Enter target protein mass (ug). '
    'This is divided by the sample concentration to compute the required sample volume.'
)
target_ug_input = st.number_input('Target protein to load (ug):', min_value=0.1, value=20.0, step=0.1)

use_loading_volume = st.checkbox(
    'I have a total loading volume (required for buffer, scaled volume, and SDS dye columns)',
    value=True
)

if use_loading_volume:
    st.write('Enter total loading volume (ul) — the sum of sample + buffer per lane.')
    total_volume_input = st.number_input('Total loading volume (ul):', min_value=1.0, value=40.0, step=1.0)
else:
    total_volume_input = None
    st.info(
        'No loading volume — only Sample Volume will be calculated. '
        'Buffer, scaled, and SDS dye columns will show N/A.'
    )

st.write(
    'Optional: enter a multiplier for the scaled sample and buffer volume columns '
    '(e.g. 2 for 2X, 3 for 3X, 4 for 4X).'
)
multiplier_input = st.number_input('Volume multiplier:', min_value=1.0, value=2.0, step=1.0)

st.write(
    'Optional: paste sample names (one per line) to label samples instead of default well names. '
    'Leave a line blank to skip that position.'
)
sample_names_text = st.text_area('Sample names (one per line):', value='')
sample_names_list = sample_names_text.splitlines()

# ─── Editable standards table ────────────────────────────────────────────────

if 'std_editor_df' in st.session_state:
    st.subheader('Standard curve points')
    st.write(
        'Edit any concentration or absorbance value below, and check/uncheck any point(s) '
        'to include or exclude them from the linear fit.'
    )
    edited_std_df = st.data_editor(
        st.session_state['std_editor_df'],
        column_config={
            'Concentration (ug/ml)': st.column_config.NumberColumn('Concentration (ug/ml)', format='%.2f'),
            'Absorbance': st.column_config.NumberColumn('Absorbance', format='%.4f'),
            'Include in fit': st.column_config.CheckboxColumn('Include in fit'),
        },
        hide_index=True,
        num_rows='fixed',
        key='std_editor',
        use_container_width=True,
    )
    st.session_state['std_editor_df'] = edited_std_df

if st.button('Run analysis'):
    if 'parsed' not in st.session_state:
        st.error('Please upload an absorbance file first.')
    else:
        parsed = st.session_state['parsed']
        edited_df = st.session_state['std_editor_df']

        all_conc = edited_df['Concentration (ug/ml)'].astype(float).values
        all_std = edited_df['Absorbance'].astype(float).values
        mask = edited_df['Include in fit'].astype(bool).values
        used_conc = all_conc[mask]
        used_std = all_std[mask]

        if used_conc.size < 2:
            st.error('At least 2 standard points must be included to fit a line.')
        else:
            try:
                results_df, stats_out, fig = run_analysis(
                    df=parsed['df'],
                    base=parsed['base'],
                    used_conc=used_conc,
                    used_std=used_std,
                    all_conc=all_conc,
                    all_std=all_std,
                    physical_std_count=parsed['physical_std_count'],
                    dilution_factor=parsed['dilution_factor'],
                    loading_volume=parsed['loading_volume'],
                    loading_protein=parsed['loading_protein'],
                    dilution_override=dilution_input,
                    total_volume_override=total_volume_input,
                    round_digits=round_digits,
                    target_ug_override=target_ug_input,
                    sample_names_override=sample_names_list,
                    multiplier=multiplier_input,
                )
                st.session_state['results_df'] = results_df
                st.session_state['stats_out'] = stats_out
                st.session_state['fig'] = fig
                st.session_state['round_digits'] = round_digits
                st.session_state['multiplier'] = multiplier_input
            except Exception as e:
                st.error(f'Analysis failed: {e}')

# ─── Results ─────────────────────────────────────────────────────────────────

if 'results_df' in st.session_state:
    results_df = st.session_state['results_df']
    stats_out = st.session_state['stats_out']
    fig = st.session_state['fig']
    rd = int(st.session_state.get('round_digits', round_digits))

    st.metric('R2', f"{stats_out['r_squared']:.4f}")
    st.metric('Slope (rounded)', f"{stats_out.get('slope_rounded', stats_out['slope']):.{rd}f}")
    st.metric('Intercept (rounded)', f"{stats_out.get('intercept_rounded', stats_out['intercept']):.{rd}f}")

    st.pyplot(fig)
    st.dataframe(results_df)

    csv = results_df.to_csv(index=False).encode('utf-8')
    st.download_button('Download results CSV', csv, file_name='bca_results.csv', mime='text/csv')

    if st.checkbox('Show raw standard arrays and input slice'):
        st.write('Concentrations (all, sorted):')
        st.write(stats_out.get('conc_sorted'))
        st.write('Absorbances (all, sorted):')
        st.write(stats_out.get('std_sorted'))
        st.write('Concentrations used for fit:')
        st.write(stats_out.get('used_conc'))
        st.write('Absorbances used for fit:')
        st.write(stats_out.get('used_std'))

        try:
            raw_df = pd.read_excel(st.session_state['abs_path'], header=None)
            st.write('Raw absorbance DataFrame (first 10 rows):')
            st.dataframe(raw_df.head(10))
            st.write('Wells used for standards (B&C, rows 0-7):')
            st.dataframe(raw_df.iloc[0:8, [1, 2]])
            st.write('Wells used for 9th standard (D2 & E2):')
            st.dataframe(pd.DataFrame([raw_df.iloc[0, [3, 4]]]))

            base_local = int(stats_out.get('base', 1))
            physical_std_count_local = int(stats_out.get('physical_std_count', len(stats_out.get('conc_sorted', []))))
            sample_start_local = base_local + physical_std_count_local
            st.write(
                f'Sample data slice start row (0-based): {sample_start_local} '
                f'-> Excel row {sample_start_local + 1}'
            )
            cols_to_show = [c for c in [3, 4, 5, 6, 7, 8, 9, 10] if c < raw_df.shape[1]]
            if cols_to_show:
                st.write('Sample area (D:K):')
                st.dataframe(raw_df.iloc[sample_start_local: sample_start_local + 20, cols_to_show])
            else:
                st.write('No sample columns found in the raw file.')
        except Exception as e:
            st.write('Could not read raw file for debug display:', e)

    try:
        std_df = pd.DataFrame({
            'Concentration_used_for_fit': stats_out.get('used_conc'),
            'Absorbance_used_for_fit': stats_out.get('used_std'),
        })
        csv_std = std_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            'Download standards used for fit (CSV)',
            csv_std,
            file_name='standards_for_fit.csv',
            mime='text/csv',
        )
    except Exception:
        pass
