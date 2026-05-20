import json
import csv
import os
from datetime import datetime

def is_timestamp_line(line):
    # Only check if line starts with a digit (year)
    return line and line[0].isdigit()

class CsvExportingTimedRotatingFileHandler:
    def __init__(self, baseFilename, suffix):
        self.baseFilename = baseFilename
        self.suffix = suffix

    def export_csv(self, rotated_filename):
        if os.path.exists(rotated_filename):
            csv_filename = rotated_filename + ".csv"
            try:
                rows = []
                fieldnames = set()
                entry_lines = []
                timestamp = None
                with open(rotated_filename, 'r', encoding='utf-8') as logf:
                    for line in logf:
                        if is_timestamp_line(line):
                            if entry_lines and timestamp:
                                entry_json = ''.join(entry_lines)
                                try:
                                    data = json.loads(entry_json)
                                    if 'events' in data and isinstance(data['events'], list):
                                        for event in data['events']:
                                            row = {'timestamp': timestamp}
                                            for k, v in event.items():
                                                if k == 'authorized_expiring_time':
                                                    # Convert float timestamp to human readable
                                                    try:
                                                        v = datetime.fromtimestamp(float(v)).strftime('%Y-%m-%d %H:%M:%S')
                                                    except Exception:
                                                        pass
                                                if k == 'authorized_time':
                                                    try:
                                                        v = datetime.fromtimestamp(int(v)).strftime('%Y-%m-%d %H:%M:%S')
                                                    except Exception:
                                                        pass
                                                row[k] = v
                                                fieldnames.add(k)
                                            rows.append(row)
                                except Exception:
                                    pass
                                entry_lines = []
                            # Start new entry
                            timestamp = line.split(' ', 1)[0] if ' ' in line else line.strip()
                            entry_lines = [line[line.find('{'):]]
                        else:
                            if entry_lines is not None:
                                entry_lines.append(line)
                    # Process last entry
                    if entry_lines and timestamp:
                        entry_json = ''.join(entry_lines)
                        try:
                            data = json.loads(entry_json)
                            if 'events' in data and isinstance(data['events'], list):
                                for event in data['events']:
                                    row = {'timestamp': timestamp}
                                    for k, v in event.items():
                                        if k == 'authorized_expiring_time':
                                            try:
                                                v = datetime.fromtimestamp(float(v)).strftime('%Y-%m-%d %H:%M:%S')
                                            except Exception:
                                                pass
                                        if k == 'authorized_time':
                                            try:
                                                v = datetime.fromtimestamp(int(v)).strftime('%Y-%m-%d %H:%M:%S')
                                            except Exception:
                                                pass
                                        row[k] = v
                                        fieldnames.add(k)
                                    rows.append(row)
                        except Exception:
                            pass
                fieldnames = ['timestamp'] + sorted(fieldnames)
                with open(csv_filename, 'w', newline='', encoding='utf-8') as csvf:
                    writer = csv.DictWriter(csvf, fieldnames=fieldnames)
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(row)
                print(f"CSV export complete: {csv_filename}")
            except Exception as e:
                print(f"Failed to export CSV: {e}")
        else:
            print(f"Log file not found: {rotated_filename}")

if __name__ == "__main__":
    log_filename = "guest_authorizations.log.2025-07-15"
    suffix = "%Y-%m-%d"
    handler = CsvExportingTimedRotatingFileHandler(baseFilename=log_filename.split('.')[0], suffix=suffix)
    handler.export_csv(log_filename)
