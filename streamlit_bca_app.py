import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
import tempfile

st.set_page_config(page_title='BCA Plate Analysis', layout='wide')

# Reimplemented minimal version of the core analysis without interactive plt.show()
def analyze_bca_plate_stream(absorbance_path: str, config_path: str, std_cols: list = None):
    df = pd.read_excel(absorbance_path, header=None)

    # Defaults
    conc_list = [2000, 1750, 1500, 1250, 1000, 750, 500, 250, 0]
    sample_names = []
    dilution_factor = 8.0
    loading_protein = 30.0
    loading_volume = 40.0

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
    # Read candidate BC standards and DE cell using base
    standards_BC = df.iloc[base:base+8, std_cols].mean(axis=1).values
    standard_DE = df.iloc[base, [3, 4]].mean()

    # Heuristic: if standard_DE looks like a numeric header (large integer) while BC values are small,
    # then assume base was wrong and shift base by +1
    try:
        avg_bc = np.nanmean(standards_BC)
        if (standard_DE > 1.0 and avg_bc < 1.0 and abs(round(standard_DE) - standard_DE) < 0.01):
            base = base + 1
            standards_BC = df.iloc[base:base+8, [1, 2]].mean(axis=1).values
            standard_DE = df.iloc[base, [3, 4]].mean()
    except Exception:
        pass

    standards = np.concatenate([standards_BC, [standard_DE]])

    # Basic validation
    if len(standards) != len(conc_list) or np.isnan(standards).any():
        raise ValueError('Standards length mismatch or NaNs detected. Check the absorbance and config files.')

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

    # Compute linear fit with numpy.polyfit for robustness and calculate R^2 explicitly
    coeffs = np.polyfit(conc_sorted, std_sorted, 1)
    slope = float(coeffs[0])
    intercept = float(coeffs[1])
    preds_full = slope * conc_sorted + intercept
    ss_res = np.sum((std_sorted - preds_full) ** 2)
    ss_tot = np.sum((std_sorted - np.mean(std_sorted)) ** 2)
    r_squared = float(1.0 - ss_res / ss_tot) if ss_tot != 0 else 0.0

    # default arrays used for plotting (can be changed later if filtering applied)
    plot_conc = conc_sorted
    plot_std = std_sorted

    # Create figure using sorted data
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.scatter(conc_sorted, std_sorted, color='blue', label='Standards')
    x_line = np.linspace(min(conc_sorted), max(conc_sorted), 100)
    y_line = slope * x_line + intercept
    ax.plot(x_line, y_line, '--r', label=f'y = {slope:.6f}x + {intercept:.6f}\nR² = {r_squared:.4f}')
    # Annotate each plotted standard point with its concentration for clarity
    for xc, yc in zip(plot_conc, plot_std):
        try:
            lbl = f"{int(xc)}"
        except Exception:
            lbl = str(xc)
        ax.annotate(lbl, (xc, yc), textcoords='offset points', xytext=(4, 4), fontsize=8, color='black')
    ax.set_xlabel('Concentration (µg/ml)')
    ax.set_ylabel('Absorbance')
    ax.set_title('BCA Standard Curve')
    ax.legend()
    ax.grid(True, alpha=0.3)

    def calc_concentration(abs_value):
        return (abs_value - intercept) / slope

    sample_sets = [
        (df.iloc[1:8, [3, 4]], "Set 1 (D-E)"),
        (df.iloc[0:7, [5, 6]], "Set 2 (F-G)"),
        (df.iloc[0:7, [7, 8]], "Set 3 (H-I)"),
        (df.iloc[0:7, [9, 10]], "Set 4 (J-K)")
    ]

    results = []
    sample_index = 0

    for sample_data, set_name in sample_sets:
        averages = sample_data.mean(axis=1)
        concentrations = calc_concentration(averages)
        start_num = 3 if set_name == "Set 1 (D-E)" else 2
        for i, (abs_val, conc) in enumerate(zip(averages, concentrations)):
            if sample_names and sample_index < len(sample_names):
                sample_name = sample_names[sample_index]
            else:
                sample_name = f"{set_name[5]}{i+start_num}"
            conc_with_dilution = conc * dilution_factor
            ug_per_ul = conc_with_dilution / 1000
            if ug_per_ul < 1.5:
                sample_vol = min(20, loading_volume)
            else:
                sample_vol = min(loading_protein / ug_per_ul, loading_volume)
            vol_2x = 2 * sample_vol
            buffer_vol = loading_volume - sample_vol
            results.append({
                'Sample': sample_name,
                'Absorbance': round(float(abs_val), 3),
                'Concentration (µg/ml)': round(float(conc), 2),
                'µg/ml (with dilution)': round(float(conc_with_dilution), 2),
                'µg/µl': round(float(ug_per_ul), 2),
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
    stats_out = {
        'slope': slope,
        'intercept': intercept,
        'r_squared': r_squared,
        'conc_sorted': conc_sorted.tolist(),
        'std_sorted': std_sorted.tolist(),
        'plot_conc': plot_conc.tolist(),
        'plot_std': plot_std.tolist(),
    }
    return results_df, stats_out, fig


st.title('BCA Plate Analysis')
st.write('Upload an absorbance Excel file and a config Excel (optional).')
abs_upl = st.file_uploader('Absorbance Excel file (.xlsx)', type=['xlsx'])
cfg_upl = st.file_uploader('Config Excel file (.xlsx) (optional)', type=['xlsx'])

# Allow user to choose which columns to average for standards
std_choice = st.selectbox('Standards replicate columns to use',
                         ('B & C (default)', 'C only', 'B, C & D (triplicate)'))

def std_choice_to_cols(choice):
    if choice == 'B & C (default)':
        return [1, 2]
    if choice == 'C only':
        return [2]
    if choice == 'B, C & D (triplicate)':
        return [1, 2, 3]
    return [1, 2]

if st.button('Run analysis'):
    if not abs_upl:
        st.error('Please upload an absorbance file')
    else:
        # Save uploaded files to temp paths
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as t_abs:
            t_abs.write(abs_upl.read())
            abs_path = t_abs.name
        if cfg_upl:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as t_cfg:
                t_cfg.write(cfg_upl.read())
                cfg_path = t_cfg.name
        else:
            cfg_path = abs_path  # pass same file so defaults apply

        try:
            cols = std_choice_to_cols(std_choice)
            results_df, stats_out, fig = analyze_bca_plate_stream(abs_path, cfg_path, std_cols=cols)
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
    st.metric('Slope', f"{stats_out['slope']:.6f}")
    st.pyplot(fig)
    st.dataframe(results_df)

    csv = results_df.to_csv(index=False).encode('utf-8')
    st.download_button('Download results CSV', csv, file_name='bca_results.csv', mime='text/csv')

    if st.checkbox('Show raw standard arrays and input slice'):
        st.write('Concentrations used (sorted):')
        st.write(stats_out.get('conc_sorted'))
        st.write('Absorbances used (sorted):')
        st.write(stats_out.get('std_sorted'))
        # Show the raw DataFrame and the exact cells used for standards
        try:
            raw_df = pd.read_excel(st.session_state['abs_path'], header=None)
            st.write('Raw absorbance DataFrame (first 10 rows):')
            st.dataframe(raw_df.head(10))
            st.write('Wells used for standards (B2-B9 & C2-C9):')
            st.dataframe(raw_df.iloc[0:8, [1, 2]])
            st.write('Wells used for 9th standard (D2 & E2):')
            st.dataframe(pd.DataFrame([raw_df.iloc[0, [3, 4]]]))
        except Exception as e:
            st.write('Could not read raw file for debug display:', e)
