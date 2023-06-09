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
    working_dir = os.path.abspath(sys.argv[1])
    if not os.path.exists(working_dir):
        print(f'{working_dir} does not exist.')
        sys.exit(1)
except IndexError:
    print('Provide dir with .abf files as argument.')
    sys.exit(1)

script_location = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
if not os.path.exists(processed_html_dir := os.path.join(working_dir, 'processed_html')):
    os.mkdir(os.path.join(working_dir, 'processed_html'))

tag_comment_pattern = re.compile(r'=> ([0-9]) x')

def abf_to_df(
    filename:str,
    current_channel:int = 1,
    voltage_channel:int = 0
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

    if len(abf.sweepList) != 1:
        tags = None
        # only gap-free recordings have a single sweep
        print(f'{os.path.basename(filename)} is a voltage sweep file. Saving IV CSV...')
        df = df[df['Time'].between(0.6, 0.85)]
        agg_df = df[['Sweep', 'Current', 'Voltage']].groupby('Sweep')
        agg_df = agg_df.aggregate(['min', 'mean', 'max'])
        agg_df.columns = agg_df.columns.to_flat_index().str.join('_')
        agg_df['filename'] = os.path.basename(filename)
        agg_df = agg_df.reset_index()
        agg_df = agg_df[['filename', 'Sweep', 'Voltage_min', 'Voltage_mean', 'Voltage_max', 'Current_min', 'Current_mean', 'Current_max']]
    else:
        print(f'{os.path.basename(filename)} is gap-free. Processing tags...')
        agg_df = None
        tags = [
            {
                'Time': abf.tagTimesSec[x],
                'Selection': re.search(tag_comment_pattern, abf.tagComments[x]).group(1)
            } for x, _ in enumerate(abf.tagTimesSec)
        ]
        tags = pd.DataFrame(tags)
        print(tags)

    return df, agg_df, tags

print("""   ***
Hey just so you know, the web viewer reduces the
temporal resolution of your data by 1/10. That is, it
only keeps every 10th point. Keeps things snappy. The
CSV files still have the full resolution.
   ***""")


abf_files = [os.path.abspath(os.path.realpath(x)) for x in glob(os.path.join(working_dir, '*.abf'))]
dfs = {}
tags = {}

aggregate_dfs = []
for filename in abf_files:
    csv_outname = filename.replace('.abf', '.csv')
    df, agg_df, abf_tags = abf_to_df(filename)
    df.to_csv(csv_outname, index=False)
    if agg_df is not None:
        aggregate_dfs.append(agg_df)
        agg_path = os.path.join(os.path.dirname(filename), 'aggregated')
        if not os.path.exists(agg_path):
            os.mkdir(agg_path)
            agg_df.to_csv(os.path.join(agg_path, os.path.basename(filename).replace('.abf', '_aggregated.csv')), index = False)
    # export tags for gap-free
    else:
        tags[os.path.basename(filename)] = abf_tags
        
    dfs[os.path.basename(filename)] = df

if aggregate_dfs:
    big_df = pd.concat(*[aggregate_dfs])
    big_df.to_csv(os.path.join(agg_path, 'combined_aggregates.csv'), index = False)

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
    abf_tags = tags[filename]
    amps = df['Current_Label'].iloc[0]

    # full trace

    chart = alt.Chart(df, width = 1200, height = 600).mark_line(
    ).encode(
        x = alt.X('Time', axis = alt.Axis(grid = False)),
        y = alt.Y('Current', title = f'Current ({amps})', axis = alt.Axis(grid = False)),
        color = 'Sweep:N'
    ).add_selection(
        trace_selection
    ).properties(
        title = 'Decimated traces'
    )

    if abf_tags is not None:
        chart = chart + alt.Chart(
            abf_tags
        ).mark_rule(
            strokeDash = [1,2]
        ).encode(
            x = alt.X('Time')
        ) + alt.Chart(
            abf_tags
        ).mark_text(
            fontSize = 20
        ).encode(
            x = alt.X('Time'),
            y = alt.value(25),
            text = 'Selection'
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
