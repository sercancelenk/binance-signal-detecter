from flask import Flask, jsonify
from pump_detector import detected_signals, batch_processor
import threading

# Initialize Flask App
app = Flask(__name__)

# Start Batch Processor in a Thread
thread = threading.Thread(target=batch_processor)
thread.daemon = True
thread.start()

# Get Detected Signals
@app.route("/signals", methods=["GET"])
def get_signals():
    return jsonify({"detected_signals": detected_signals})

if __name__ == "__main__":
    app.run(debug=True, port=5000)