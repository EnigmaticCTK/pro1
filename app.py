    """
    Greenhouse Monitoring Dashboard — Flask + Socket.IO backend
    Reads Arduino serial data and streams it to the web dashboard in real-time.
    """
    
    import os
    import re
    import csv
    import io
    import math
    import random
    import threading
    import time
    from collections import deque
    from datetime import datetime
    
    from flask import Flask, Response, jsonify, render_template, request
    from flask_socketio import SocketIO
    
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "greenhouse-monitor-secret"
    socketio = SocketIO(app, cors_allowed_origins="*")
    
    # ── Shared state ───────────────────────────────────────────────────────────────
    MAX_HISTORY = 50
    
    state = {
        "running": False,
        "port": "COM7",
        "soil_threshold": 400,
        "temp_threshold": 30.0,
        "latest": None,
        "history": deque(maxlen=MAX_HISTORY),
        "alert": False,
    }
    _lock = threading.Lock()
    _stop_event = threading.Event()
    _serial_thread = None
    
    
    # ── Serial parsing ─────────────────────────────────────────────────────────────
    def parse_block(lines):
        """Parse lines from one Arduino data block into a reading dict."""
        reading = {"timestamp": datetime.now().isoformat(), "alert": False}
        for line in lines:
            line = line.strip()
            m = re.match(r"Soil Moisture:\s*(\d+)", line)
            if m:
                reading["soil"] = int(m.group(1))
            m = re.match(r"Temperature:\s*([\d.]+)", line)
            if m:
                reading["temp"] = float(m.group(1))
            m = re.match(r"Humidity:\s*([\d.]+)", line)
            if m:
                reading["humidity"] = float(m.group(1))
            if "ALERT" in line:
                reading["alert"] = True
        if all(k in reading for k in ("soil", "temp", "humidity")):
            return reading
        return None
    
    
    def _apply_thresholds(reading):
        """Set the alert flag based on current thresholds (call with _lock held)."""
        reading["alert"] = (
            reading["soil"] > state["soil_threshold"]
            or reading["temp"] > state["temp_threshold"]
        )
        return reading
    
    
    # ── Serial reader thread ───────────────────────────────────────────────────────
    def serial_reader(port, baud, stop_event):
        try:
            import serial
            ser = serial.Serial(port, baud, timeout=2)
        except Exception as exc:
            socketio.emit("error", {"message": f"Cannot open {port}: {exc}"})
            with _lock:
                state["running"] = False
            return
    
        block = []
        in_block = False
    
        while not stop_event.is_set():
            try:
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
    
            if "GREENHOUSE DATA" in line:
                in_block = True
                block = []
            elif line.startswith("---") and in_block:
                in_block = False
                reading = parse_block(block)
                if reading:
                    with _lock:
                        _apply_thresholds(reading)
                        state["latest"] = reading
                        state["history"].append(reading)
                        state["alert"] = reading["alert"]
                    socketio.emit("sensor_data", reading)
            elif in_block:
                block.append(line)
    
        ser.close()
        with _lock:
            state["running"] = False
    
    
    # ── Demo mode (no Arduino needed) ─────────────────────────────────────────────
    def demo_reader(stop_event):
        """Generates realistic-looking sensor data for testing without hardware."""
        t = 0
        while not stop_event.is_set():
            t += 1
            soil = int(200 + 350 * abs(math.sin(t * 0.08)) + random.randint(-15, 15))
            temp = round(22 + 10 * abs(math.sin(t * 0.06)) + random.uniform(-0.3, 0.3), 1)
            humidity = round(50 + 20 * math.sin(t * 0.05) + random.uniform(-1, 1), 1)
            humidity = max(0, min(100, humidity))
    
            reading = {
                "timestamp": datetime.now().isoformat(),
                "soil": soil,
                "temp": temp,
                "humidity": humidity,
                "alert": False,
            }
    
            with _lock:
                _apply_thresholds(reading)
                state["latest"] = reading
                state["history"].append(reading)
                state["alert"] = reading["alert"]
    
            socketio.emit("sensor_data", reading)
            time.sleep(2)
    
        with _lock:
            state["running"] = False
    
    
    # ── Routes ─────────────────────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return render_template("index.html")
    
    
    @app.route("/api/start", methods=["POST"])
    def start():
        global _serial_thread, _stop_event
    
        data = request.json or {}
        port = data.get("port", "COM7").strip()
        demo = port.lower() == "demo"
    
        with _lock:
            if state["running"]:
                return jsonify({"ok": False, "message": "Already running"})
            state["running"] = True
            state["port"] = port
    
        _stop_event = threading.Event()
    
        if demo:
            _serial_thread = threading.Thread(
                target=demo_reader, args=(_stop_event,), daemon=True
            )
        else:
            _serial_thread = threading.Thread(
                target=serial_reader, args=(port, 9600, _stop_event), daemon=True
            )
    
        _serial_thread.start()
        return jsonify({"ok": True, "port": port, "demo": demo})
    
    
    @app.route("/api/stop", methods=["POST"])
    def stop():
        _stop_event.set()
        with _lock:
            state["running"] = False
        return jsonify({"ok": True})
    
    
    @app.route("/api/thresholds", methods=["POST"])
    def set_thresholds():
        data = request.json or {}
        with _lock:
            if "soil" in data:
                state["soil_threshold"] = int(data["soil"])
            if "temp" in data:
                state["temp_threshold"] = float(data["temp"])
            soil = state["soil_threshold"]
            temp = state["temp_threshold"]
        return jsonify({"ok": True, "soil": soil, "temp": temp})
    
    
    @app.route("/api/status")
    def status():
        with _lock:
            return jsonify(
                {
                    "running": state["running"],
                    "port": state["port"],
                    "soil_threshold": state["soil_threshold"],
                    "temp_threshold": state["temp_threshold"],
                    "latest": state["latest"],
                    "history": list(state["history"]),
                }
            )
    
    
    @app.route("/api/export")
    def export_csv():
        with _lock:
            history = list(state["history"])
    
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=["timestamp", "soil", "temp", "humidity", "alert"]
        )
        writer.writeheader()
        writer.writerows(history)
    
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=greenhouse_data.csv"
            },
        )
    
    
    # ── Terminal startup prompt ────────────────────────────────────────────────────
    def prompt_for_port():
        """Ask for a COM port in the terminal, test it, and return it."""
        print("\n" + "═" * 50)
        print("  🌿  GREENHOUSE MONITOR")
        print("═" * 50)
        print("  Type a COM port (e.g. COM7, /dev/ttyUSB0)")
        print("  or type 'demo' to run with simulated data.")
        print("═" * 50)
    
        while True:
            try:
                port = input("\n  COM port › ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n  Exiting.")
                raise SystemExit(0)
    
            if not port:
                print("  ✗  Please enter a port.")
                continue
    
            if port.lower() == "demo":
                print("  ✓  Demo mode selected — no hardware needed.\n")
                return "demo"
    
            # Test the connection before proceeding
            print(f"  Testing {port} at 9600 baud...")
            try:
                import serial
                ser = serial.Serial(port, 9600, timeout=2)
                ser.close()
                print(f"  ✓  Connected to {port} successfully.\n")
                return port
            except Exception as exc:
                print(f"  ✗  Could not open {port}: {exc}")
                print("     Check the port name and that the Arduino is plugged in.")
    
    
    # ── Entry point ────────────────────────────────────────────────────────────────
    if __name__ == "__main__":
        # WERKZEUG_RUN_MAIN is set to "true" in the reloader's child process.
        # Only the parent (first run) should prompt; children inherit the port via env.
        is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    
        if not is_reloader_child:
            # ── Parent / first run ──────────────────────────────────────────────
            # Only prompt here. The reloader will spawn a child process
            # (WERKZEUG_RUN_MAIN=true) that actually runs Flask and the reader.
            # Do NOT open the serial port here — the child will do it.
            port = prompt_for_port()
            os.environ["GREENHOUSE_PORT"] = port          # inherited by child
            print("  Dashboard → http://localhost:5000")
            print("  Press Ctrl+C to stop.\n")
        else:
            # ── Reloader child — this is the real Flask process ─────────────────
            # Start the serial reader here, where Flask actually runs.
            port = os.environ.get("GREENHOUSE_PORT", "demo")
    
            state["port"] = port
            state["running"] = True
    
            _stop_event = threading.Event()
            if port == "demo":
                _serial_thread = threading.Thread(
                    target=demo_reader, args=(_stop_event,), daemon=True
                )
            else:
                _serial_thread = threading.Thread(
                    target=serial_reader, args=(port, 9600, _stop_event), daemon=True
                )
            _serial_thread.start()
    
        socketio.run(app, debug=True, use_reloader=True, port=5000)
