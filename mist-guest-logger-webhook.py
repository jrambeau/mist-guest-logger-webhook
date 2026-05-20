import sys
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import csv

# Force stdout to be unbuffered
sys.stdout.reconfigure(line_buffering=True)

app = Flask(__name__)

# Set up logging with daily rotation
log_dir = 'app-logs'
guest_log_dir = 'guest-logs'

# Create directories
try:
    os.makedirs(log_dir, exist_ok=True)
    os.makedirs(guest_log_dir, exist_ok=True)
    print(f"Directories created: {log_dir}, {guest_log_dir}", flush=True)
except Exception as e:
    print(f"Error creating directories: {e}", flush=True)

log_file = os.path.join(log_dir, 'guest_authorizations.log')
client_info_log_file = os.path.join(log_dir, 'client_info.log')
app_log_file = os.path.join(log_dir, 'app.log')
guest_csv_base = os.path.join(guest_log_dir, 'guest_authorizations.log')
client_info_csv_base = os.path.join(guest_log_dir, 'client_info.log')

# Create formatter
log_formatter = logging.Formatter('%(asctime)s %(process)d %(levelname)s %(message)s')

def setup_logging():
    # Reset root logger
    root = logging.getLogger()
    if root.handlers:
        for handler in root.handlers:
            root.removeHandler(handler)
    
    # Configure root logger to output to stdout
    root.setLevel(logging.INFO)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    root.addHandler(console_handler)
    
    # Set up app logger with both file and console output
    app_logger = logging.getLogger('mist_guest_app_logger')
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = True  # Allow propagation to root logger for console output
    
    # Add rotating file handler for app.log
    try:
        file_handler = TimedRotatingFileHandler(
            app_log_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        file_handler.setFormatter(log_formatter)
        app_logger.addHandler(file_handler)
        print(f"App log handler created: {app_log_file}", flush=True)
    except Exception as e:
        print(f"Error creating app log handler: {e}", flush=True)
    
    # Set up timed rotating file handlers for guest logs
    try:
        guest_auth_handler = TimedRotatingFileHandler(
            log_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        guest_auth_handler.setFormatter(log_formatter)
        print(f"Guest auth log handler created: {log_file}", flush=True)
    except Exception as e:
        print(f"Error creating guest auth log handler: {e}", flush=True)
        guest_auth_handler = None
    
    try:
        client_info_handler_log = TimedRotatingFileHandler(
            client_info_log_file,
            when='midnight',
            interval=1,
            backupCount=30,
            encoding='utf-8'
        )
        client_info_handler_log.setFormatter(log_formatter)
        print(f"Client info log handler created: {client_info_log_file}", flush=True)
    except Exception as e:
        print(f"Error creating client info log handler: {e}", flush=True)
        client_info_handler_log = None
    
    return app_logger, guest_auth_handler, client_info_handler_log

# Initialize logger and handlers
app_logger, guest_auth_handler, client_info_handler_log = setup_logging()

# Set to track authorized client MAC addresses
guest_clients = set()

# Timestamp of last guest_clients flush
last_flush_date = datetime.now().date()

def flush_guest_clients_if_needed():
    """Flush guest_clients set daily to prevent memory issues"""
    global last_flush_date
    current_date = datetime.now().date()
    if current_date > last_flush_date:
        guest_count = len(guest_clients)
        guest_clients.clear()
        last_flush_date = current_date
        app_logger.info(f"Daily flush: Cleared {guest_count} guest clients from memory")

class CsvExportingTimedRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.csv_fieldnames = set()

    def write_event_to_csv(self, timestamp, event):
        # Format fields
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
            if k == 'timestamp':
                try:
                    v = datetime.fromtimestamp(int(v)).strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    pass
            row[k] = v
            self.csv_fieldnames.add(k)
        # Determine today's CSV filename
        today = datetime.now().strftime(self.suffix)
        csv_filename = f"{self.baseFilename}.{today}.csv"
        # Write or append to CSV
        file_exists = os.path.exists(csv_filename)
        fieldnames = ['timestamp'] + sorted(self.csv_fieldnames)
        with open(csv_filename, 'a', newline='', encoding='utf-8') as csvf:
            writer = csv.DictWriter(csvf, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    def doRollover(self):
        super().doRollover()
        # Optionally clear fieldnames for new day
        self.csv_fieldnames.clear()

# Use the custom handler for guest-authorizations
handler = CsvExportingTimedRotatingFileHandler(guest_csv_base, when='midnight', interval=1, backupCount=365, encoding='utf-8')
handler.suffix = "%Y-%m-%d"
formatter = logging.Formatter('%(asctime)s %(message)s')
handler.setFormatter(formatter)

# Use the custom handler for client-info
client_info_handler = CsvExportingTimedRotatingFileHandler(client_info_csv_base, when='midnight', interval=1, backupCount=365, encoding='utf-8')
client_info_handler.suffix = "%Y-%m-%d"
client_info_handler.setFormatter(formatter)

@app.route('/mist-guest-auth', methods=['POST'])
def mist_webhook():
    data = request.get_json()
    if not data:
        app_logger.warning('Invalid payload received')
        return jsonify({'error': 'Invalid payload'}), 400

    # Check if we need to flush guest_clients (daily)
    flush_guest_clients_if_needed()

    topic = data.get('topic', 'unknown')
    app_logger.info(f"New event received at {datetime.now().isoformat()} for topic: {topic}")

    if topic == 'guest-authorizations':
        # Write raw event to dedicated file with rotation
        raw_event = json.dumps(data, ensure_ascii=False) + '\n'
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(raw_event)
        guest_auth_handler.doRollover()
        
        events = data.get('events', [])
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for event in events:
            # Add event_date (current timestamp when event is received)
            event['event_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Add authorized_time_utc from authorized_time value
            try:
                authorized_time = int(event.get('authorized_time', 0))
                event['authorized_time_utc'] = datetime.utcfromtimestamp(authorized_time).strftime('%Y-%m-%d %H:%M:%S')
            except Exception as e:
                app_logger.warning(f"Failed to convert authorized_time: {e}")
                event['authorized_time_utc'] = 'N/A'
            
            handler.write_event_to_csv(timestamp, event)
            # Track guest clients MAC addresses
            client_mac = event.get('client')
            if client_mac:
                guest_clients.add(client_mac)
                app_logger.info(f"Added client {client_mac} to guest clients list")
        app_logger.info("Event data written to guest_authorizations.log and CSV.")
    elif topic == 'client-info':
        # Write raw event to dedicated file with rotation
        raw_event = json.dumps(data, ensure_ascii=False) + '\n'
        with open(client_info_log_file, 'a', encoding='utf-8') as f:
            f.write(raw_event)
        client_info_handler_log.doRollover()
        
        events = data.get('events', [])
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        app_logger.info(f"Processing client-info: Found {len(events)} events, {len(guest_clients)} guests in memory")
        
        for event in events:
            client_mac = event.get('mac')
            app_logger.info(f"Processing event with MAC: {client_mac}")
            if client_mac and client_mac in guest_clients:
                # Only log client-info for guest clients
                client_info_handler.write_event_to_csv(timestamp, event)
                app_logger.info(f"Logging client-info for guest client {client_mac}")
            elif client_mac:
                app_logger.info(f"Skipping client-info for non-guest client {client_mac} (not in {guest_clients})")
        app_logger.info("Client-info event data processed.")
    else:
        app_logger.info(f"Unknown topic: {topic}")

    return jsonify({'status': 'received'}), 200

if __name__ == '__main__':
    # Log startup
    app_logger.info('Mist Guest Logger is starting...')
    # Ensure all output is flushed immediately
    sys.stdout.flush()
    sys.stderr.flush()
    app.run(host='0.0.0.0', port=3000)
