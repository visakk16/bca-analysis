import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import tempfile

st.set_page_config(page_title='BCA Plate Analysis', layout='wide')

# Reimplemented minimal version of the core analysis without interactive plt.show()
def analyze_bca_plate_stream(absorbance_path: str, config_path: str = None, std_cols: list = None, exclude_option: str = 'none', dilution_override: float = None, total_volume_override: float = None, round_digits: int = 6, target_ug_override: float = None, sample_names_override: list = None):
    df = pd.read_excel(absorbance_path, header=None)

    # Defaults (9-point standard series including zero)
    conc_list = [2000, 1500, 1000, 750, 500, 250, 125, 25, 0]
    sample_names = []
    import streamlit as st
    import pandas as pd
    import numpy as np
    import matplotlib.pyplot as plt
    from scipy import stats
    import tempfile

    st.set_page_config(page_title='BCA Plate Analysis', layout='wide')

    # Reimplemented minimal version of the core analysis without interactive plt.show()
    def analyze_bca_plate_stream(absorbance_path: str, config_path: str = None, std_cols: list = None, exclude_option: str = 'none', dilution_override: float = None, total_volume_override: float = None, round_digits: int = 6, target_ug_override: float = None, sample_names_override: list = None):
        df = pd.read_excel(absorbance_path, header=None)

        # Defaults (9-point standard series including zero)
        conc_list = [2000, 1500, 1000, 750, 500, 250, 125, 25, 0]
        sample_names = []
        dilution_factor = 8.0
        loading_protein = 30.0
        loading_volume = 40.0

        # If a config path is provided attempt to read it, otherwise use defaults and UI values
        if config_path:
            try:
                config_df = pd.read_excel(config_path)
                if 'Standard Concentration (µg/ml)' in config_df.columns:
                    temp_conc = config_df['Standard Concentration (µg/ml)'].dropna().tolist()
                    if temp_conc:
                        conc_list = temp_conc
                if 'Sample Names' in config_df.columns:
                    temp_names = config_df['Sample Names'].dropna().tolist()
                    if temp_names:
                        sample_names = temp_names
                params_df = None
                if 'Parameter' in config_df.columns and 'Value' in config_df.columns:
                    params_df = config_df[config_df['Parameter'].isin(['dilution_factor', 'loading_protein', 'loading_volume'])]
                    if not params_df.empty:
                        for _, row in params_df.iterrows():
                            if row['Parameter'] == 'dilution_factor':
                                dilution_factor = float(row['Value'])
                            elif row['Parameter'] == 'loading_protein':
                                loading_protein = float(row['Value'])
                            elif row['Parameter'] == 'loading_volume':
                                loading_volume = float(row['Value'])
            except Exception:
                # keep defaults if config fails
                pass

        # If a dilution override was provided from the UI, use it (user-entered value takes precedence)
        if dilution_override is not None:
            try:
                dilution_factor = float(dilution_override)
            except Exception:
                pass

        # If a total volume override was provided from the UI, use it (user-entered value takes precedence)
        if total_volume_override is not None:
            try:
                loading_volume = float(total_volume_override)
            except Exception:
                pass

        # Robust detection if first row is a numeric header like 1,2,3,... (some plate exports include it)
        header_like = False
        try:
            first_row_vals = df.iloc[0, 1:20].values.tolist()
            tokens = []
            for v in first_row_vals:
                s = str(v).strip()
                tokens.append(s)
            # count tokens that look like small integers (e.g., '1', '2', '3' or '1.0')
            import re
            int_like = 0
            for t in tokens:
                if re.match(r'^\s*\d+(?:\.0+)?\s*$', t):
                    int_like += 1
            if int_like >= max(3, int(0.6 * len(tokens))):
                header_like = True
        except Exception:
            header_like = False

        # also check if row 1 column 0 contains row labels A..H — then row 0 is header
        try:
            first_data_label = str(df.iloc[1, 0]).strip()
            if len(first_data_label) == 1 and first_data_label.isalpha():
                header_like = True
        except Exception:
            pass

        base = 1 if header_like else 0

        # Determine which columns to use for standards (default B & C -> indices 1 and 2)
        if std_cols is None:
            std_cols = [1, 2]

        # Read exactly as many standard rows as concentrations specified in conc_list.
        # This avoids the fragile "9th standard" hack and ensures the code matches the plate layout.
        n_stds = len(conc_list)

        # Read standards robustly. If the standard series contains 9 points (including 0),
        # the plate provides 8 values in B&C (rows A..H) and the 0 standard sits in D&E of the base row.
        try:
            if n_stds >= 9:
                # read exactly 8 plate rows from B&C (A..H)
                std_block = df.iloc[base: base + 8, std_cols]
                physical_std_count = std_block.dropna(how='all').shape[0]
                standards = std_block.mean(axis=1).values
                # Always attempt to read the 9th (zero) standard from D&E at the base row
                if df.shape[1] > 4:
                    try:
                        de_vals = pd.to_numeric(pd.Series(df.iloc[base, [3, 4]].values), errors='coerce').dropna()
                        de_val = float(de_vals.mean()) if not de_vals.empty else np.nan
                    except Exception:
                        de_val = np.nan
                    if not np.isnan(de_val):
                        standards = np.concatenate([standards, [de_val]])
                    else:
                        # append NaN so length stays consistent; we'll try per-row fills below
                        standards = np.concatenate([standards, [np.nan]])
            else:
                std_block = df.iloc[base: base + n_stds, std_cols]
                physical_std_count = std_block.dropna(how='all').shape[0]
                standards = std_block.mean(axis=1).values

            # If any of the standards are NaN (e.g. missing in B/C), try to fill per-row from D&E
            nan_idx = np.where(np.isnan(standards))[0]
            if nan_idx.size > 0 and df.shape[1] > 4:
                for idx in nan_idx:
                    row = base + int(idx) if idx < 8 else base  # for idx==8 (9th), read from base row D&E
                    try:
                        de_vals = df.iloc[row, [3, 4]].values
                        # convert to numeric where possible
                        de_numeric = pd.to_numeric(pd.Series(de_vals), errors='coerce')
                        if not de_numeric.dropna().empty:
                            standards[idx] = float(de_numeric.mean())
                    except Exception:
                        pass
        except Exception as e:
            raise ValueError(f'Failed reading standard block: {e}')

        # Ensure physical_std_count is defined (fallback to n_stds)
        try:
            physical_std_count
        except NameError:
            physical_std_count = n_stds

        # After attempting to fill missing values, ensure we have all standards
        if len(standards) != n_stds or np.isnan(standards).any():
            # give a helpful error listing which indices are missing
            missing = [i for i, v in enumerate(standards) if (v is None or (isinstance(v, float) and np.isnan(v)))]
            raise ValueError(f'Expected {n_stds} standards, got {len([s for s in standards if not (isinstance(s,float) and np.isnan(s))])}. Missing indices: {missing}. Check the absorbance and config files and the chosen standard columns.')

        # Basic validation: ensure we read exactly the number of standards we expect
        if len(standards) != len(conc_list) or np.isnan(standards).any():
            raise ValueError(f'Expected {len(conc_list)} standards, got {len(standards)}. Check the absorbance and config files and the chosen standard columns.')

        # Ensure concentration and standards are paired correctly
        conc_arr = np.array(conc_list, dtype=float)
        std_arr = np.array(standards, dtype=float)
        if conc_arr.shape != std_arr.shape:
            raise ValueError('Standards length mismatch or NaNs detected. Check the absorbance and config files.')

            # Check whether conc_list ordering matches std_arr ordering or needs reversing.
            # Compute Pearson r for current and reversed concentration orders and pick the best match.
            def pearsonr(a, b):
                a = np.asarray(a, dtype=float)
                b = np.asarray(b, dtype=float)
                if a.size < 2:
                    return 0.0
                a_mean = a.mean(); b_mean = b.mean()
                num = ((a - a_mean) * (b - b_mean)).sum()
                den = np.sqrt(((a - a_mean) ** 2).sum() * ((b - b_mean) ** 2).sum())
                return num / den if den != 0 else 0.0

            r_normal = pearsonr(conc_arr, std_arr)
            r_reversed = pearsonr(conc_arr[::-1], std_arr)
            # choose orientation with higher absolute correlation
            if abs(r_reversed) > abs(r_normal):
                conc_arr = conc_arr[::-1]

            # Now sort by concentration for plotting clarity
        order = np.argsort(conc_arr)
        conc_sorted = conc_arr[order]
        std_sorted = std_arr[order]

        # Optionally exclude end-point standards: 'none', 'exclude_0', 'exclude_2000', 'exclude_both'
        used_conc = conc_sorted
        used_std = std_sorted
        if exclude_option != 'none':
            # Build a boolean mask over the sorted arrays and exclude by index (lowest/highest)
            mask = np.ones_like(conc_sorted, dtype=bool)
            # conc_sorted is sorted ascending; index 0 is the lowest, index -1 the highest
            if exclude_option in ('exclude_0', 'exclude_both'):
                if mask.size > 0:
                    mask[0] = False
            if exclude_option in ('exclude_2000', 'exclude_both'):
                if mask.size > 0:
                    mask[-1] = False
            used_conc = conc_sorted[mask]
            used_std = std_sorted[mask]

        # Compute linear fit with numpy.polyfit for robustness and calculate R^2 explicitly
        # Need at least 2 points to fit
        if used_conc.size < 2:
            raise ValueError('Not enough standards remaining after exclusion to perform a linear fit (need at least 2).')

        coeffs = np.polyfit(used_conc, used_std, 1)
        slope = float(coeffs[0])
        intercept = float(coeffs[1])
        # Apply rounding as requested by the user - these rounded values will be used to compute concentrations
        try:
            rd = int(round_digits)
            slope_rounded = float(round(slope, rd))
            intercept_rounded = float(round(intercept, rd))
        except Exception:
            slope_rounded = slope
            intercept_rounded = intercept
        preds_full = slope * used_conc + intercept
        ss_res = np.sum((used_std - preds_full) ** 2)
        ss_tot = np.sum((used_std - np.mean(used_std)) ** 2)
        r_squared = float(1.0 - ss_res / ss_tot) if ss_tot != 0 else 0.0

        # default arrays used for plotting (can be changed later if filtering applied)
        plot_conc = used_conc
        plot_std = used_std

        # Create figure using the used (possibly filtered) data so plot matches the fit
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.scatter(used_conc, used_std, color='blue', label='Standards')
        # Plot regression line across the used-concentration range
        x_min = float(np.min(used_conc))
        x_max = float(np.max(used_conc))
        x_line = np.linspace(x_min, x_max, 100)
        # Use rounded slope/intercept for the plotted regression line and label
        y_line = slope_rounded * x_line + intercept_rounded
        ax.plot(x_line, y_line, '--r', label=f'y = {slope_rounded:.{rd}f}x + {intercept_rounded:.{rd}f}\nR² = {r_squared:.4f}')
        # Annotate each plotted standard point with its concentration for clarity
        for xc, yc in zip(used_conc, used_std):
            try:
                lbl = f"{int(xc)}"
            except Exception:
                lbl = str(xc)
            ax.annotate(lbl, (xc, yc), textcoords='offset points', xytext=(4, 4), fontsize=8, color='black')
        # Ensure axes reflect the used range (small padding)
        x_padding = max(1.0, (x_max - x_min) * 0.03)
        ax.set_xlim(x_min - x_padding, x_max + x_padding)
        ax.set_xlabel('Concentration (µg/ml)')
        ax.set_ylabel('Absorbance')
        ax.set_title('BCA Standard Curve')
        ax.legend()
        ax.grid(True, alpha=0.3)

        def calc_concentration(abs_value):
            # concentration in µg/ml from the rounded fitted line (for the diluted sample measured)
            return (abs_value - intercept_rounded) / slope_rounded

        # Determine sample rows: for typical plates samples start on the second data row (D3/E3 in your sheet)
        # Use base + 1 so we read rows corresponding to plate rows B..H (Excel rows 3..9) for sample columns
        sample_start = base + 1

        # helper to convert 0-based column index to Excel-style letter (0->A, 1->B...)
        def col_letter(idx: int) -> str:
            idx0 = int(idx)
            letters = ''
            while idx0 >= 0:
                letters = chr(ord('A') + (idx0 % 26)) + letters
                idx0 = idx0 // 26 - 1
            return letters

        # Columns for sample sets (pairs): D-E, F-G, H-I, J-K -> indices 3..10
        sample_col_pairs = [(3, 4), (5, 6), (7, 8), (9, 10)]

        results = []
        sample_index = 0
        names_provided = bool(sample_names_override)

        # iterate over columns and take a fixed set of plate rows starting from sample_start
        for pair_idx, (c1, c2) in enumerate(sample_col_pairs):
            # If the user supplied a list of sample names, stop once we've consumed them all
            if names_provided and sample_index >= len(sample_names_override):
                break
            # ensure the DataFrame has these columns
            if df.shape[1] <= max(c1, c2):
                continue
            # read up to 8 plate rows (A..H) starting from sample_start; this targets D3/E3, D4/E4, ...
            sample_data = df.iloc[sample_start: sample_start + 8, [c1, c2]]
            # drop rows where both replicates are na
            sample_data = sample_data.dropna(how='all')
            if sample_data.empty:
                continue

                # Horizontal averaging: treat each row as one sample and average across the two columns (D+E, F+G, etc.)
            for row_idx, row_vals in sample_data.iterrows():
                vals = pd.to_numeric(pd.Series(row_vals.values), errors='coerce').dropna().values
                if vals.size == 0:
                    continue
                abs_mean = float(np.mean(vals))

                # compute concentration from the fitted line and then apply dilution factor
                conc = calc_concentration(abs_mean)
                conc_with_dilution = conc * dilution_factor

                # convert µg/ml -> µg/µl by dividing by 1000
                ug_per_ul = conc_with_dilution / 1000.0 if conc_with_dilution is not None else float('nan')

                # compute sample volume (µl) required to obtain the requested target mass (µg): V = target_ug / (µg/µl)
                # prefer user-specified target_ug_override from UI; fall back to loading_protein
                target_ug = loading_protein if target_ug_override is None else float(target_ug_override)
                if ug_per_ul and not np.isnan(ug_per_ul) and ug_per_ul > 0:
                    sample_vol = float(target_ug) / ug_per_ul
                else:
                    # If we cannot compute sample concentration, default sample volume to the full loading volume
                    sample_vol = float(loading_volume)

                # Ensure sample volume does not exceed the total loading volume; buffer will absorb the remainder
                if sample_vol > float(loading_volume):
                    sample_vol = float(loading_volume)

                vol_2x = 2.0 * sample_vol
                buffer_vol = float(loading_volume) - sample_vol
                if buffer_vol < 0:
                    buffer_vol = 0.0

                # If the user provided sample names via the UI, use them (sequentially).
                # If the provided name is blank/empty, skip this sample (do not append a row).
                if sample_names_override and sample_index < len(sample_names_override):
                    candidate_name = sample_names_override[sample_index].strip()
                    if candidate_name == '':
                        # skip this sample but still advance the index so positions map
                        sample_index += 1
                        continue
                    sample_name = candidate_name
                elif sample_names and sample_index < len(sample_names):
                    sample_name = sample_names[sample_index]
                else:
                    sample_name = f"{col_letter(c1)}{int(row_idx) + 1}"

                # Build results row and include the target mass column between 'µg/µl' and 'Sample Volume (µl)'
                target_label = None
                try:
                    if target_ug_override is not None:
                        tu = float(target_ug_override)
                    else:
                        tu = float(loading_protein)
                    target_label = f"{int(tu) if float(tu).is_integer() else tu} µg"
                except Exception:
                    target_label = f"{float(loading_protein)} µg"

                results.append({
                    'Sample': sample_name,
                    'Absorbance': round(abs_mean, 3),
                    'Concentration (µg/ml)': round(float(conc) if not pd.isna(conc) else float('nan'), 2),
                    'µg/ml (with dilution)': round(float(conc_with_dilution) if not pd.isna(conc_with_dilution) else float('nan'), 2),
                    'µg/µl': round(float(ug_per_ul) if not pd.isna(ug_per_ul) else float('nan'), 4),
                    target_label: round(float(target_ug) if 'target_ug' in locals() else float(loading_protein), 3),
                    'Sample Volume (µl)': round(float(sample_vol), 2),
                    '2X Sample Volume (µl)': round(float(vol_2x), 2),
                    'Buffer Volume (µl)': round(float(buffer_vol), 2)
                })
                sample_index += 1

        # Ensure plot arrays exist
        if 'plot_conc' not in locals():
            plot_conc = conc_sorted
        if 'plot_std' not in locals():
            plot_std = std_sorted

        results_df = pd.DataFrame(results)
        # If the user provided sample names via the UI, only keep rows matching non-empty provided names.
        if sample_names_override:
            provided_nonempty = [s.strip() for s in sample_names_override if s and s.strip()]
            if provided_nonempty:
                # preserve order of provided names
                keep_set = set(provided_nonempty)
                results_df = results_df[results_df['Sample'].isin(keep_set)].copy()
        stats_out = {
            'slope': slope,
            'intercept': intercept,
            'slope_rounded': slope_rounded,
            'intercept_rounded': intercept_rounded,
            'r_squared': r_squared,
            'conc_sorted': conc_sorted.tolist(),
            'std_sorted': std_sorted.tolist(),
            'used_conc': used_conc.tolist(),
            'used_std': used_std.tolist(),
            'plot_conc': plot_conc.tolist(),
            'plot_std': plot_std.tolist(),
            'physical_std_count': int(physical_std_count),
            'base': int(base),
            'total_volume': float(loading_volume),
            'loading_protein': float(loading_protein),
        }
        return results_df, stats_out, fig


    st.title('BCA Plate Analysis')
    st.write('Upload an absorbance Excel file (.xlsx).')
    abs_upl = st.file_uploader('Absorbance Excel file (.xlsx)', type=['xlsx'])

    # Allow user to override dilution factor manually
    st.write('Optional: enter dilution factor if your samples were diluted (e.g., enter 5 for a 1:5 dilution)')
    dilution_input = st.number_input('Dilution Factor:', min_value=1.0, value=5.0, step=1.0)

    st.write('Optional: enter total loading volume (µl). This is the sum of sample + buffer. The sample volume is computed to deliver the target protein amount; the buffer volume will be adjusted accordingly.')
    total_volume_input = st.number_input('Total loading volume (µl):', min_value=1.0, value=40.0, step=1.0)

    # Allow user to choose rounding precision for slope/intercept used to compute concentrations
    st.write('Optional: choose decimal places to round slope and intercept (these rounded values will be used to compute concentrations)')
    round_digits = st.number_input('Decimal places for slope/intercept:', min_value=0, max_value=10, value=6, step=1)

    # Allow user to choose how much protein (µg) to load per lane; this controls sample volume calculation
    st.write('Optional: enter target protein mass to load (µg). This will be divided by the sample concentration to compute the required sample volume.')
    target_ug_input = st.number_input('Target protein to load (µg):', min_value=0.1, value=20.0, step=0.1)

    # Optional: allow user to paste or type sample names (one per line). These will be used in order to name samples.
    st.write('Optional: paste sample names (one per line) to label samples instead of default well names (D3, D4, ...).')
    sample_names_text = st.text_area('Sample names (one per line):', value='')
    # Preserve blank lines: an empty line means "skip this sample". Do not drop blank lines so positions map.
    sample_names_list = sample_names_text.splitlines()

    # Standard columns are fixed to B & C (indices 1 and 2) and always averaged
    exclude_option = st.selectbox('Exclude endpoints from fit', ('none', 'exclude_0', 'exclude_2000', 'exclude_both'))
    std_cols = [1, 2]

    if st.button('Run analysis'):
        if not abs_upl:
            st.error('Please upload an absorbance file')
        else:
            # Save uploaded files to temp paths
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as t_abs:
                t_abs.write(abs_upl.read())
                abs_path = t_abs.name
            cfg_path = None

            try:
                results_df, stats_out, fig = analyze_bca_plate_stream(abs_path, cfg_path, std_cols=std_cols, exclude_option=exclude_option, dilution_override=dilution_input, total_volume_override=total_volume_input, round_digits=round_digits, target_ug_override=target_ug_input, sample_names_override=sample_names_list)
                # store results in session state so UI controls outside the button can interact
                st.session_state['results_df'] = results_df
                st.session_state['stats_out'] = stats_out
                st.session_state['fig'] = fig
                st.session_state['abs_path'] = abs_path
                st.session_state['cfg_path'] = cfg_path
            except Exception as e:
                st.error(f'Analysis failed: {e}')
    # If results exist in session state, render them and the interactive debug checkbox
    if 'results_df' in st.session_state:
        results_df = st.session_state['results_df']
        stats_out = st.session_state['stats_out']
        fig = st.session_state['fig']

        st.metric('R²', f"{stats_out['r_squared']:.4f}")
        # show both raw and rounded slope/intercept for transparency
        st.metric('Slope (rounded)', f"{stats_out.get('slope_rounded', stats_out['slope']):.{int(round_digits)}f}")
        st.metric('Intercept (rounded)', f"{stats_out.get('intercept_rounded', stats_out['intercept']):.{int(round_digits)}f}")
        st.pyplot(fig)
        st.dataframe(results_df)

        csv = results_df.to_csv(index=False).encode('utf-8')
        st.download_button('Download results CSV', csv, file_name='bca_results.csv', mime='text/csv')

        if st.checkbox('Show raw standard arrays and input slice'):
            st.write('Concentrations used (sorted):')
            st.write(stats_out.get('conc_sorted'))
            st.write('Absorbances used (sorted):')
            st.write(stats_out.get('std_sorted'))
            st.write('Points actually used for fitting (after exclude filter):')
            st.write('Concentrations used for fit:')
            st.write(stats_out.get('used_conc'))
            st.write('Absorbances used for fit:')
            st.write(stats_out.get('used_std'))
            # Show the raw DataFrame and the exact cells used for standards
            try:
                raw_df = pd.read_excel(st.session_state['abs_path'], header=None)
                st.write('Raw absorbance DataFrame (first 10 rows):')
                st.dataframe(raw_df.head(10))
                st.write('Wells used for standards (B2-B9 & C2-C9):')
                st.dataframe(raw_df.iloc[0:8, [1, 2]])
                st.write('Wells used for 9th standard (D2 & E2):')
                st.dataframe(pd.DataFrame([raw_df.iloc[0, [3, 4]]]))
                # Show the sample slice we are using (starts immediately after the standards block)
                # Use the same base detection used during analysis for consistency
                base_local = int(stats_out.get('base', 1))
                physical_std_count_local = int(stats_out.get('physical_std_count', len(stats_out.get('conc_sorted', []))))
                sample_start_local = base_local + physical_std_count_local
                st.write(f'Sample data slice start row (0-based index): {sample_start_local} - this corresponds to Excel row {sample_start_local+1}')
                # show first 20 rows of sample area across D..K
                cols_to_show = [3,4,5,6,7,8,9,10]
                cols_to_show = [c for c in cols_to_show if c < raw_df.shape[1]]
                st.write('Sample area (D:K) starting at sample start:')
                if cols_to_show:
                    st.dataframe(raw_df.iloc[sample_start_local:sample_start_local+20, cols_to_show])
                else:
                    st.write('No sample columns found in the raw file')
            except Exception as e:
                st.write('Could not read raw file for debug display:', e)

        # Allow downloading the exact standard points used for the regression
        try:
            std_df = pd.DataFrame({
                'Concentration_used_for_fit': stats_out.get('used_conc'),
                'Absorbance_used_for_fit': stats_out.get('used_std')
            })
            csv_std = std_df.to_csv(index=False).encode('utf-8')
            st.download_button('Download standards used for fit (CSV)', csv_std, file_name='standards_for_fit.csv', mime='text/csv')
        except Exception:
            pass
                    # Allow downloading the exact standard points used for the regression
