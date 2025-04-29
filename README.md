# HauntAI - Sensitive Data Detection Tool

HauntAI is a tool that uses AI to detect sensitive data inside a single file or entire folder. It comes with both a **web-based interface** and a **command-line interface (CLI)** to fit different workflows.

---

## 🌐 Web Version

### 🔧 Installation

1. From the root directory, install dependencies for both frontend and backend:
   ```bash
   cd client && npm install
   cd ../server && npm install
   cd ..
2. Make sure you are back in the root directory, then start the application:
  ```bash
   npm start
  ```
3. Once running, open your browser and go to:
   http://localhost:3000
4. Upload a file or folder through the web interface to start the analysis.

### 📂 Analysis Output
- The analysis result will be displayed directly in the terminal where the server is running.
- Check the terminal output for details about sensitive data detection.


## 🖥️ CLI Version

### 🔧 Installation
1. Navigate to the cli/ directory:
   ```bash
   cd cli
2. Run the CLI tool:
   ```bash
   python cli.py <path-to-your-file-or-folder>
   ```

### 📂 Analysis Output
- The analysis result will be displayed directly in the terminal where the server is running.
- Check the terminal output for details about sensitive data detection.


⚙️ Requirements
- Node.js (v14 or newer)
- Python 3.7 or higher
- Internet connection (for AI detection using external API)

💡 Features
- AI-based detection of secrets, credentials, API keys, passwords, and sensitive configuration
- Analyze single files or folders
- Ignore pattern filtering to reduce false positives
- Web interface and CLI support
