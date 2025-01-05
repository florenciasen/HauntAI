from flask import Flask, jsonify, request

from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.route('/')
def home():
    return 'Hello, Flask!'

if __name__ == '__main__':
    print("Starting Flask app...")  # Debugging print statement
    app.run(debug=True, host='0.0.0.0', port=5000)
