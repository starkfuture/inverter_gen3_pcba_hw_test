import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt
import re
from datetime import datetime

# Channels name list
channel_names = {
    1: "I_PH_U",
    2: "I_PH_V",
    3: "I_PH_W",
    4: "DC_LINK",
}

# Log file selection
root = tk.Tk()
root.withdraw()
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
plt.ylabel("Temperature (°C)")
plt.ylim(20, 120)
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()