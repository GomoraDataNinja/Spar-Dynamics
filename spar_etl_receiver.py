"""
SPAR ETL Receiver - Render Version
"""
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime
import logging
import os
import random
import json
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL', '')

# ============================================
# HEALTH CHECK
# ============================================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "SPAR ETL Receiver",
        "timestamp": datetime.now().isoformat(),
        "cloudflare_configured": bool(CLOUDFLARE_API_URL)
    })

# ============================================
# SERVE FRONTEND FILES
# ============================================

@app.route('/', methods=['GET'])
def serve_index():
    try:
        with open('index.html', 'r') as f:
            return f.read(), 200, {'Content-Type': 'text/html'}
    except:
        return jsonify({"message": "SPAR ETL Receiver is running"})

@app.route('/config.js', methods=['GET'])
def serve_config():
    try:
        with open('config.js', 'r') as f:
            return f.read(), 200, {'Content-Type': 'application/javascript'}
    except:
        return "// config.js not found", 404

# ============================================
# CLOUDFLARE PROXY ENDPOINTS
# ============================================

def execute_query_via_cloudflare(query, params=None):
    if not CLOUDFLARE_API_URL:
        return []
    try:
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-query",
            json={"query": query, "params": params or []},
            timeout=30
        )
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def execute_command_via_cloudflare(query, params=None):
    if not CLOUDFLARE_API_URL:
        return {"success": False}
    try:
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-command",
            json={"query": query, "params": params or []},
            timeout=30
        )
        if response.status_code == 200:
            return response.json()
        return {"success": False}
    except:
        return {"success": False}

# ============================================
# PRODUCTS ENDPOINT
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    sample_products = [
        {"id": 1, "product_code": "PRD001", "product_name": "Golden Delicious Apples", "category_name": "Fresh Produce", "unit_price": 2.99, "current_stock": 45, "stock_status": "in-stock"},
        {"id": 2, "product_code": "PRD002", "product_name": "Fresh Bananas", "category_name": "Fresh Produce", "unit_price": 1.49, "current_stock": 60, "stock_status": "in-stock"},
        {"id": 3, "product_code": "PRD003", "product_name": "Beef Steak Rump", "category_name": "Meat & Poultry", "unit_price": 12.99, "current_stock": 18, "stock_status": "in-stock"}
    ]
    if not CLOUDFLARE_API_URL:
        return jsonify(sample_products), 200
    
    query = """
        SELECT id, product_code, product_name, category_name, unit_price, current_stock,
               'in-stock' as stock_status
        FROM erp_products
        WHERE is_active = 1
    """
    result = execute_query_via_cloudflare(query)
    return jsonify(result if result else sample_products), 200

# ============================================
# SALES ORDERS ENDPOINT
# ============================================

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    sample_orders = [
        {"order_number": "SO-20260623-1001", "customer_name": "John Doe", "total_amount": 45.50, "status": "Confirmed"},
        {"order_number": "SO-20260623-1002", "customer_name": "Jane Smith", "total_amount": 67.25, "status": "Confirmed"}
    ]
    if not CLOUDFLARE_API_URL:
        return jsonify(sample_orders), 200
    
    query = """
        SELECT so_number as order_number, customer_name, total_amount, status
        FROM erp_sales_orders
        ORDER BY created_at DESC
    """
    result = execute_query_via_cloudflare(query)
    return jsonify(result if result else sample_orders), 200

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    data = request.json
    order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
    
    if not CLOUDFLARE_API_URL:
        return jsonify({
            "status": "success",
            "order_number": order_number,
            "total_amount": 100.00
        }), 200
    
    return jsonify({
        "status": "success",
        "order_number": order_number,
        "total_amount": 100.00
    }), 200

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    sample_sales = [
        {"sale_id": "SPAR-20260623-1001", "customer_name": "John Doe", "total_sales": 45.50},
        {"sale_id": "SPAR-20260623-1002", "customer_name": "Jane Smith", "total_sales": 67.25}
    ]
    return jsonify(sample_sales), 200

@app.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    sample_pos = [
        {"po_number": "PO-20260623-1001", "supplier_name": "Fresh Foods Ltd", "total_amount": 500.00, "status": "Draft"}
    ]
    return jsonify(sample_pos), 200

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"🚀 Starting SPAR ETL Receiver on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
