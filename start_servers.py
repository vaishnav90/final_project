#!/usr/bin/env python3
"""
Startup script to run both Flask and FastAPI servers concurrently.
This allows the messaging system to work with real-time updates.
"""

import subprocess
import sys
import time
import os
from pathlib import Path

def start_flask_app():
    """Start the Flask application"""
    print("Starting Flask application...")
    flask_process = subprocess.Popen([
        sys.executable, "main.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return flask_process

def start_fastapi_server():
    """Start the FastAPI WebSocket server"""
    print("Starting FastAPI WebSocket server...")
    fastapi_process = subprocess.Popen([
        sys.executable, "fastapi_messaging_server.py"
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return fastapi_process

def main():
    print("🚀 Starting ReThread messaging system...")
    print("=" * 50)
    
    # Check if required files exist
    if not Path("main.py").exists():
        print("❌ Error: main.py not found!")
        return
    
    if not Path("fastapi_messaging_server.py").exists():
        print("❌ Error: fastapi_messaging_server.py not found!")
        return
    
    try:
        # Start both servers
        flask_process = start_flask_app()
        time.sleep(2)  # Give Flask time to start
        
        fastapi_process = start_fastapi_server()
        time.sleep(2)  # Give FastAPI time to start
        
        print("✅ Both servers started successfully!")
        print("🌐 Flask app: http://localhost:5000")
        print("🔌 FastAPI WebSocket: ws://localhost:8000")
        print("=" * 50)
        print("Press Ctrl+C to stop both servers...")
        
        # Keep the script running
        try:
            flask_process.wait()
        except KeyboardInterrupt:
            print("\n🛑 Stopping servers...")
            flask_process.terminate()
            fastapi_process.terminate()
            print("✅ Servers stopped.")
            
    except Exception as e:
        print(f"❌ Error starting servers: {e}")
        return

if __name__ == "__main__":
    main()
