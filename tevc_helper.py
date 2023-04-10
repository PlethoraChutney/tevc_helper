#!/usr/bin/env python
import pyabf
import sys
import os
import pandas as pd
import re
import altair as alt
from glob import glob
from flask import Flask, render_template, send_from_directory


try:
    working_dir = sys.argv[1]
    if not os.path.exists(working_dir):
        print(f'{working_dir} does not exist.')
        sys.exit(1)
except IndexError:
    print('Provide dir with .abf files as argument.')
    sys.exit(1)

script_location = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
if not os.path.exists(processed_html_dir := os.path.join(working_dir, 'processed_html')):
        os.mkdir(os.path.join(working_dir, 'processed_html'))


abf_files = [os.path.abspath(os.path.realpath(x)) for x in glob(os.path.join(working_dir, '*.abf'))]
dfs = {}

def abf_to_df(
    filename:str,
    current_channel:int = 0,
    voltage_channel:int = 1
    # barrel_channel:int = 3
) -> pd.DataFrame:
    abf = pyabf.ABF(filename)

    time = []
    sweep_column = []
    recordings = {
        'Current': [],
        'Voltage': [],
        'Barrel': []
    }
    current_label = None
    voltage_label = None

    for i in range(len(abf.sweepList)):
        sweep = abf.sweepList[i]
        try:
            abf.setSweep(sweep, channel = current_channel)
            time.extend(abf.sweepX)
            sweep_column.extend([i] * len(abf.sweepX))
            recordings['Current'].extend(abf.sweepY)
            current_label = abf.sweepLabelY
        except ValueError:
            print(f'Warning: failed to access given channel for current in {filename}, sweep {sweep}')
        try:
            abf.setSweep(sweep, channel = voltage_channel)
            recordings['Voltage'].extend(abf.sweepY)
            voltage_label = abf.sweepLabelY
        except ValueError:
            print(f'Warning: failed to access given channel for voltage in {filename}, sweep {sweep}')
        # try:
        #     abf.setSweep(sweep, channel = barrel_channel)
        #     recordings['Barrel'].extend(abf.sweepY)
        # except ValueError:
        #     print(f'Warning: failed to access given channel for barrel in {filename}, sweep {sweep}')



    df = pd.DataFrame({
        'Time': time,
        'Sweep': sweep_column
    })

    for channel, values in recordings.items():
        if len(values) == len(df.Time):
            df[channel] = values

    df['Voltage_Label'] = re.search('\((.{2})\)', voltage_label).group(1)
    df['Current_Label'] = re.search('\((.{2})\)', current_label).group(1)
    df['Filename'] =os.path.basename(filename)

    return df

print("""   ***
Hey just so you know, the web viewer reduces the
temporal resolution of your data by 1/10. That is, it
only keeps every 10th point. Keeps things snappy. The
CSV files still have the full resolution.
   ***""")

for filename in abf_files:
    csv_outname = filename.replace('.abf', '.csv')
    df = abf_to_df(filename)
    df.to_csv(csv_outname, index=False)
    dfs[os.path.basename(filename)] = df

# -------------------------------
# Server
# -------------------------------

app = Flask(
    __name__,
    template_folder='templates'
)

def plot_abf(filename:str):
    trace_selection = alt.selection_interval(encodings = ['x'])

    df = dfs[filename][::10]
    amps = df['Current_Label'][0]

    # full trace

    chart = alt.Chart(df, width = 800, height = 600).mark_line(
    ).encode(
        x = 'Time',
        y = alt.Y('Current', title = f'Current ({amps})'),
        color = 'Sweep:N'
    ).add_selection(
        trace_selection
    ).properties(
        title = 'Decimated traces'
    )

    # mean value

    mean_points = alt.Chart(df, width = 400, height = 600).mark_errorbar(
        extent = 'iqr'
    ).encode(
        x = alt.X('Sweep:N', title = 'Sweep Number'),
        y = alt.Y('Current:Q', title = f'Mean Current ({amps})')
    ).transform_filter(
        trace_selection
    ) + alt.Chart(df).mark_point(
        size = 100,
        filled = True
    ).encode(
        x = alt.X('Sweep:N', title = 'Sweep Number'),
        y = alt.Y('mean(Current)', title = f'Mean Current ({amps})', scale = alt.Scale(zero = False)),
        color = 'Sweep:N',
        tooltip = alt.Tooltip(['Sweep', 'min(Current)', 'mean(Current)', 'max(Current)'], format = ',.2f')
    ).transform_filter(
        trace_selection
    ).properties(
        title = 'Mean and IQR'
    ) + alt.Chart(df).mark_text(
        align='left', dx = 10
    ).encode(
        x = alt.X('Sweep:N', title = 'Sweep Number'),
        y = alt.Y('mean(Current)', title = f'Mean Current ({amps})', scale = alt.Scale(zero = False)),
        text = alt.Text('mean(Current)', format = ',.0f')
    ).transform_filter(
        trace_selection
    )

    outfile_name = os.path.join(
        processed_html_dir,
        filename.replace('.abf', '.html')
    )
    alt.hconcat(chart, mean_points).save(outfile_name)

@app.route('/', methods = ['GET'])
def index():
    return render_template('index.html', filenames = dfs.keys())

@app.route('/process/<filename>', methods = ['GET'])
def process(filename):
    plot_abf(filename)
    return send_from_directory(
        processed_html_dir,
        filename.replace('abf', 'html')
    )

if __name__ == '__main__':
    app.run(host = 'localhost', port = '8080')
