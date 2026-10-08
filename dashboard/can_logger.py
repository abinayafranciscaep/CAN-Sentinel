"""
can_logger.py - CAN-Sentinel CSV logger (Sadhamail)

Reads every frame from the virtual CAN bus (vcan0) and saves it as a CSV
file in the agreed 5-column format:
    timestamp, can_id, dlc, data_hex, label

Usage (run from the repo root):
    python3 dashboard/can_logger.py <label> <run_number> (ex: $ python3 dashboard/can_logger.py normal 1)
    -> data/normal_run1_1008.csv

Press Ctrl+C to stop; the file is closed cleanly.
"""
import csv  # used to write the CSV file
import os # used to create the data/ folder
import sys # used to get the command-line arguments
from datetime import datetime # used to get the current timestamp
import can # used to read the CAN bus

# Label and run number come from the command line.
# Defaults: label "normal", run "1".
label = sys.argv[1] if len(sys.argv) > 1 else "normal" 
run = sys.argv[2] if len(sys.argv) > 2 else "1" 

# Create the data/ folder if it doesn't exist.
path = f"data/{label}_run{run}_{datetime.now():%m%d}.csv" 

bus = can.Bus(channel="vcan0", interface="socketcan") # creates the CAN bus
count=0

try:
    with open(path, "w", newline="") as f: # opens the file in write mode
        writer = csv.writer(f) # creates a CSV writer
        writer.writerow(["timestamp", "can_id", "dlc", "data_hex", "label"]) # writes the header row of the CSV file 
        while True:
            msg = bus.recv(timeout=1.0) # receives a CAN frame
            if msg is None:
                continue # continues to the next iteration if no frame is received
            writer.writerow([
                f"{msg.timestamp:.6f}", # Unix time
                f"0x{msg.arbitration_id:03X}", # ID 
                msg.dlc, # number of data bytes 
                msg.data.hex().upper(), # payload as uppercase hex
                label, # same label for the whole run
            ]) # writes the frame to the CSV file
            count += 1 # increments the counter
except KeyboardInterrupt:
    pass # catches the keyboard interrupt
finally:
    bus.shutdown() # shuts down the CAN bus
    print(f"Saved {count} frames to {path}") # prints the number of frames saved
