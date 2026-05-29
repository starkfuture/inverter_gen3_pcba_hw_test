import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt
import re
from datetime import datetime
import argparse

# Channels name list
default_channel_names = {
    15: "5V_RAIL",
    22: "PCB_TEMP0",
    23: "PCB_TEMP1",
    24: "POWER_MODULE_U_TEMP",
    25: "POWER_MODULE_V_TEMP",
    26: "POWER_MODULE_W_TEMP"
}

def create_plots_list(channels_anlg, channels_legend) -> {}:
    # if channels_anlg is None or channels_legend is None:
    #     print('ERROR - Channels and legends should be specified')
    #     return None
    # elif isinstance(channels_anlg, list) and isinstance(channels_legend, list):
    #     if len(channels_anlg) == 1:
    #         original_value = [channels_anlg] * expected_items
    #     elif len(original_value) != expected_items:
    #         print('ERROR - ' + str(parameter_name) + ' should be specified for each file (size mismatch)')
    #         exit(ERR_INVALID_PARAMETERS)
    # elif expected_items != 1:
    #     print('ERROR - ' + str(parameter_name) + ' should be specified for each file')
    #     exit(ERR_INVALID_PARAMETERS)
    # else:
    #     original_value = [original_value]

    return default_channel_names


def plot_analog_channels(file_path, channel_names, min_scale, max_scale, title):
    # Log file selection
    root = tk.Tk()
    root.withdraw()

    if not file_path:
        file_path = filedialog.askopenfilename(title="Select log file")

        if not file_path:
            print("No file was selected.")
            exit()

    # Compile regular expressions
    timestamp_pattern = re.compile(r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})")
    analog_pattern = re.compile(r"ANLG\[(\d+)\]:\s*(-?\d+\.\d+)")

    # Temporal dictionary to store last timestamp
    latest_by_timestamp = {}

    with open(file_path, 'r') as f:
        for line in f:
            ts_match = timestamp_pattern.search(line)
            if ts_match:
                timestamp_str = ts_match.group(1)
                latest_by_timestamp[timestamp_str] = line  # it is overwritten if there was already a previous timestamp

    # Now only last timestamp is processed
    sorted_timestamps = sorted(latest_by_timestamp.keys(), key=lambda x: datetime.strptime(x, "%Y/%m/%d %H:%M:%S"))
    timestamps = []
    data = {ch: [] for ch in channel_names.keys()}

    for ts in sorted_timestamps:
        line = latest_by_timestamp[ts]
        matches = analog_pattern.findall(line)
        values = {int(ch): float(val) for ch, val in matches}
        for ch in data:
            data[ch].append(values.get(ch, float('nan')))  # in case channel is left
        timestamps.append(datetime.strptime(ts, "%Y/%m/%d %H:%M:%S"))

    # Creates X axis in seconds from the first timestamp
    t0 = timestamps[0]
    x = [(t - t0).total_seconds() for t in timestamps]

    # Plotting
    plt.figure(figsize=(10, 6))
    for ch in sorted(data.keys()):
        plt.plot(x, data[ch], label=channel_names[ch])

    plt.xlabel("Time (s)")
    plt.ylabel(title)
    plt.ylim(min_scale, max_scale)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    # Initialize arguments' parser
    parser = argparse.ArgumentParser()

    # Adding optional argument
    parser.add_argument("-g", "--anlg", nargs='*',
                        help="Configures the analog channels to be plotted. NOTE: more than one channel can be specified.")
    parser.add_argument("-n", "--min_scale",
                        help="Configures the minimum scale on the plot.")
    parser.add_argument("-x", "--max_scale",
                        help="Configures the maximum scale on the plot.")
    parser.add_argument("-l", "--legend", nargs='*',
                        help="Configures the legend to be shown for each trace on the plot. Do not use spaces on names")
    parser.add_argument("-f", "--FileData",
                        help="File to process with the analog measurements.")
    parser.add_argument("-t", "--Title",
                        help="Plot title.")

    # Default values
    main_anlg = None
    main_min_scale = 20.0
    main_max_scale = 120.0
    main_legend = None
    main_file = None
    main_title = "Analog"

    args = parser.parse_args()

    # Updates values specified
    if args.anlg:
        main_anlg = args.anlg
    if args.min_scale:
        main_min_scale = float(args.min_scale)
    if args.max_scale:
        main_max_scale = float(args.max_scale)
    if args.FileData:
        main_file = args.FileData
    if args.Title:
        main_title = args.Title
    if args.legend:
        main_legend = args.legend

    main_anlg = create_plots_list(main_anlg, main_legend)
    if main_anlg:
        plot_analog_channels(main_file, main_anlg, main_min_scale, main_max_scale, main_title)