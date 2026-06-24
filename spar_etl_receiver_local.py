"""
SPAR ETL RECEIVER - LOCAL VERSION
Complete API with Products, Sales, Purchase Orders, and Goods Receiving
"""

from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import pyodbc
import pandas as pd
import logging
import os
import random
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spar_etl_receiver.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================
# SQL SERVER CONNECTION
# ============================================
def get_sql_connection():
    try:
        conn = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=(local);"
            "DATABASE=SPAR_ETL;"
            "Trusted_Connection=yes;"
        )
        return conn
    except Exception as e:
        logger.error(f"SQL Server connection error: {e}")
        return None

def execute_query(query, params=None):
    conn = get_sql_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        if params:
            return pd.read_sql(query, conn, params=params)
        else:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Query error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def execute_command(query, params=None):
    conn = get_sql_connection()
    if conn is None:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        conn.commit()
        cursor.close()
        return True, "Success"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

# ============================================
# CLOUDFLARE ENDPOINTS - FOR RENDER INTEGRATION
# ============================================

@app.route('/execute-query', methods=['POST'])
def execute_query_remote():
    try:
        data = request.json
        query = data.get('query')
        params = data.get('params', [])
        
        logger.info(f"📊 Executing remote query: {query[:100]}...")
        
        conn = get_sql_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        columns = [column[0] for column in cursor.description]
        rows = []
        for row in cursor.fetchall():
            rows.append(dict(zip(columns, row)))
        
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Query returned {len(rows)} rows")
        return jsonify(rows), 200
    except Exception as e:
        logger.error(f"Query execution error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/execute-command', methods=['POST'])
def execute_command_remote():
    try:
        data = request.json
        query = data.get('query')
        params = data.get('params', [])
        
        logger.info(f"📝 Executing remote command: {query[:100]}...")
        
        conn = get_sql_connection()
        if conn is None:
            return jsonify({"success": False, "error": "Database connection failed"}), 500
        
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        try:
            cursor.execute("SELECT SCOPE_IDENTITY()")
            row_id = cursor.fetchone()[0]
        except:
            row_id = None
        
        conn.commit()
        cursor.close()
        conn.close()
        
        logger.info(f"✅ Command executed successfully, ID: {row_id}")
        return jsonify({
            "success": True,
            "id": row_id
        }), 200
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================
# HEALTH ENDPOINT
# ============================================

@app.route('/health', methods=['GET'])
def health():
    try:
        conn = get_sql_connection()
        db_status = "connected" if conn else "disconnected"
        if conn:
            conn.close()
    except:
        db_status = "error"
    
    return jsonify({
        "status": "healthy",
        "database": db_status,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "SPAR ETL Receiver - Local",
        "status": "running",
        "database": "SPAR_ETL",
        "endpoints": {
            "health": "GET /health",
            "execute-query": "POST /execute-query",
            "execute-command": "POST /execute-command"
        }
    })

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

if __name__ == '__main__':
    print("=" * 70)
    print("🛒 SPAR ETL RECEIVER - LOCAL VERSION")
    print("=" * 70)
    print(f"\n🚀 Starting server on port 8000...")
    print(f"\n📍 Local URL: http://localhost:8000")
    print(f"📍 Health: http://localhost:8000/health")
    print(f"📍 Execute-query: POST /execute-query")
    print(f"📍 Execute-command: POST /execute-command")
    print("\n✅ Connected to SPAR_ETL database with erp_ tables")
    print("\nPress Ctrl+C to stop")
    print("=" * 70)
    
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)
