"""
SPAR ETL Receiver - Render Version
Complete API with all features
"""

from flask import Flask, request, jsonify
from datetime import datetime
import logging
import os
import random
import requests
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================
# CONFIGURATION
# ============================================

CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL', '').rstrip('/')
logger.info(f"🔗 Cloudflare API URL: {CLOUDFLARE_API_URL or 'NOT SET'}")

# ============================================
# PROXY FUNCTIONS
# ============================================

def execute_query_via_cloudflare(query, params=None):
    if not CLOUDFLARE_API_URL:
        return []

    try:
        url = f"{CLOUDFLARE_API_URL}/execute-query"
        response = requests.post(
            url,
            json={"query": query, "params": params or []},
            timeout=30,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Query error: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"Query exception: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    if not CLOUDFLARE_API_URL:
        return {"success": False, "error": "CLOUDFLARE_API_URL not configured"}

    try:
        url = f"{CLOUDFLARE_API_URL}/execute-command"
        response = requests.post(
            url,
            json={"query": query, "params": params or []},
            timeout=30,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"success": False, "error": f"Status {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================
# HEALTH CHECK
# ============================================

@app.route('/health', methods=['GET'])
def health():
    cloudflare_status = "unknown"
    if CLOUDFLARE_API_URL:
        try:
            response = requests.get(f"{CLOUDFLARE_API_URL}/health", timeout=10)
            if response.status_code == 200:
                cloudflare_status = "connected"
            else:
                cloudflare_status = f"error_{response.status_code}"
        except:
            cloudflare_status = "disconnected"

    return jsonify({
        "status": "healthy" if cloudflare_status == "connected" else "degraded",
        "service": "SPAR ETL Receiver - Render",
        "timestamp": datetime.now().isoformat(),
        "cloudflare_configured": bool(CLOUDFLARE_API_URL),
        "cloudflare_status": cloudflare_status,
        "cloudflare_url": CLOUDFLARE_API_URL
    })

# ============================================
# PRODUCTS
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    if not CLOUDFLARE_API_URL:
        return jsonify([]), 200

    query = """
        SELECT 
            p.id, p.product_code, p.product_name, pc.category_name,
            p.unit_of_measure, p.unit_price, p.cost_price,
            p.current_stock, p.reorder_level,
            p.current_stock AS available_stock,
            CASE 
                WHEN p.current_stock <= 0 THEN 'out-of-stock'
                WHEN p.current_stock <= p.reorder_level THEN 'low-stock'
                ELSE 'in-stock'
            END AS stock_status,
            p.is_active
        FROM erp_products p
        LEFT JOIN erp_product_categories pc ON p.category_id = pc.id
        WHERE p.is_active = 1
        ORDER BY pc.category_name, p.product_name
    """
    result = execute_query_via_cloudflare(query)
    return jsonify(result if result else []), 200

# ============================================
# SALES ORDERS
# ============================================

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    if not CLOUDFLARE_API_URL:
        return jsonify([]), 200

    query = """
        SELECT 
            so.so_number as order_number,
            c.customer_name,
            so.order_date,
            CONVERT(VARCHAR, so.order_time, 108) as order_time,
            so.total_amount,
            so.status,
            so.approval_status,
            so.created_by as recorded_by,
            ISNULL(so.rewards_earned, 0) as rewards_earned
        FROM erp_sales_orders so
        LEFT JOIN erp_customers c ON so.customer_id = c.id
        ORDER BY so.created_at DESC
    """
    result = execute_query_via_cloudflare(query)
    return jsonify(result if result else []), 200

# ============================================
# RECENT SALES
# ============================================

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    if not CLOUDFLARE_API_URL:
        return jsonify([]), 200

    query = """
        SELECT TOP 50
            so.so_number as sale_id,
            c.customer_name,
            so.order_date as sale_date,
            CONVERT(VARCHAR, so.order_time, 108) as sale_time,
            so.total_amount as total_sales,
            ISNULL(so.rewards_earned, 0) as rewards_earned,
            so.status,
            so.approval_status,
            so.created_by as recorded_by,
            1 as etl_processed
        FROM erp_sales_orders so
        LEFT JOIN erp_customers c ON so.customer_id = c.id
        ORDER BY so.created_at DESC
    """
    result = execute_query_via_cloudflare(query)
    return jsonify(result if result else []), 200

# ============================================
# PURCHASE ORDERS
# ============================================

@app.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    if not CLOUDFLARE_API_URL:
        return jsonify([]), 200

    query = """
        SELECT 
            po.id, po.po_number, s.supplier_name,
            po.order_date, po.expected_delivery_date,
            po.status, po.approval_status, po.total_amount
        FROM erp_purchase_orders po
        LEFT JOIN erp_suppliers s ON po.supplier_id = s.id
        ORDER BY po.created_at DESC
    """
    result = execute_query_via_cloudflare(query)
    return jsonify(result if result else []), 200

# ============================================
# PURCHASE ORDER LINES
# ============================================

@app.route('/purchase-orders/<po_number>/lines', methods=['GET'])
def get_purchase_order_lines(po_number):
    if not CLOUDFLARE_API_URL:
        return jsonify([]), 200

    query = """
        SELECT 
            pol.id, pol.product_id, pol.product_code, pol.product_name,
            pol.quantity, pol.unit_price, pol.line_total
        FROM erp_purchase_order_lines pol
        INNER JOIN erp_purchase_orders po ON pol.po_id = po.id
        WHERE po.po_number = ?
        ORDER BY pol.line_number
    """
    result = execute_query_via_cloudflare(query, [po_number])
    return jsonify(result if result else []), 200

# ============================================
# SALES ORDERS - POST
# ============================================

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/sales-orders"
        response = requests.post(
            url,
            json=request.json,
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# PURCHASE ORDERS - POST
# ============================================

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/purchase-orders"
        response = requests.post(
            url,
            json=request.json,
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# GOODS RECEIPT - POST
# ============================================

@app.route('/goods-receipt', methods=['POST'])
def receive_goods():
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/goods-receipt"
        response = requests.post(
            url,
            json=request.json,
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# DYNAMIC CASH BALANCE
# ============================================

@app.route('/dynamic-cash-balance', methods=['GET'])
def get_dynamic_cash_balance_proxy():
    if not CLOUDFLARE_API_URL:
        return jsonify({"cash_balance": 0, "available_cash": 0}), 200

    try:
        url = f"{CLOUDFLARE_API_URL}/dynamic-cash-balance"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return jsonify(response.json()), 200
        return jsonify({"cash_balance": 0, "available_cash": 0}), 200
    except:
        return jsonify({"cash_balance": 0, "available_cash": 0}), 200

# ============================================
# CUSTOMERS
# ============================================

@app.route('/customers', methods=['GET'])
def get_customers_proxy():
    if not CLOUDFLARE_API_URL:
        return jsonify([]), 200

    try:
        url = f"{CLOUDFLARE_API_URL}/customers"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return jsonify(response.json()), 200
        return jsonify([]), 200
    except:
        return jsonify([]), 200

# ============================================
# BANK ACCOUNTS
# ============================================

@app.route('/bank-accounts', methods=['GET'])
def get_bank_accounts_proxy():
    if not CLOUDFLARE_API_URL:
        return jsonify([]), 200

    try:
        url = f"{CLOUDFLARE_API_URL}/bank-accounts"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return jsonify(response.json()), 200
        return jsonify([]), 200
    except:
        return jsonify([]), 200

# ============================================
# RECEIPT - GET
# ============================================

@app.route('/receipt/<order_number>', methods=['GET'])
def get_receipt_proxy(order_number):
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/receipt/{order_number}"
        response = requests.get(url, timeout=60)
        if response.status_code == 200:
            return jsonify(response.json()), 200
        return jsonify({"error": "Failed to generate receipt"}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# APPROVE/REJECT PO
# ============================================

@app.route('/purchase-orders/<po_number>/approve', methods=['POST'])
def approve_purchase_order_proxy(po_number):
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/purchase-orders/{po_number}/approve"
        response = requests.post(url, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/purchase-orders/<po_number>/reject', methods=['POST'])
def reject_purchase_order_proxy(po_number):
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/purchase-orders/{po_number}/reject"
        response = requests.post(url, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/purchase-orders/<po_number>', methods=['DELETE'])
def delete_purchase_order_proxy(po_number):
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/purchase-orders/{po_number}"
        response = requests.delete(url, timeout=30)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# CORS
# ============================================

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
    return response

# ============================================
# ROOT
# ============================================

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "SPAR ETL Receiver - Render",
        "status": "running",
        "cloudflare_api": CLOUDFLARE_API_URL or "NOT SET",
        "endpoints": {
            "health": "GET /health",
            "products": "GET /products",
            "sales_orders": "GET /sales-orders, POST /sales-orders",
            "purchase_orders": "GET /purchase-orders, POST /purchase-orders",
            "purchase_orders/lines": "GET /purchase-orders/<po_number>/lines",
            "purchase_orders/<po_number>/approve": "POST",
            "purchase_orders/<po_number>/reject": "POST",
            "purchase_orders/<po_number>": "DELETE",
            "goods_receipt": "POST /goods-receipt",
            "recent": "GET /recent",
            "bank-accounts": "GET /bank-accounts",
            "dynamic-cash-balance": "GET /dynamic-cash-balance",
            "customers": "GET /customers",
            "receipt/<order_number>": "GET /receipt/<order_number>"
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print("=" * 70)
    print("🛒 SPAR ETL RECEIVER - Render Version")
    print("=" * 70)
    print(f"\n🚀 Starting server on port {port}...")
    print(f"🔗 Cloudflare API: {CLOUDFLARE_API_URL or 'NOT SET'}")
    print("\n📋 Available Endpoints:")
    print("   GET  /health")
    print("   GET  /products")
    print("   GET  /sales-orders")
    print("   POST /sales-orders")
    print("   GET  /purchase-orders")
    print("   POST /purchase-orders")
    print("   GET  /purchase-orders/<po_number>/lines")
    print("   POST /purchase-orders/<po_number>/approve")
    print("   POST /purchase-orders/<po_number>/reject")
    print("   DELETE /purchase-orders/<po_number>")
    print("   POST /goods-receipt")
    print("   GET  /recent")
    print("   GET  /bank-accounts")
    print("   GET  /dynamic-cash-balance")
    print("   GET  /customers")
    print("   GET  /receipt/<order_number>")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
