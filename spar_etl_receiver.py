"""
SPAR ETL Receiver - Render Version (COMPLETE)
All endpoints proxied to local database via Cloudflare tunnel
"""

from flask import Flask, request, jsonify, send_file
from datetime import datetime
import logging
import os
import requests
import traceback
from io import BytesIO

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
    """Execute a query on the local database via Cloudflare tunnel."""
    if not CLOUDFLARE_API_URL:
        logger.error("❌ CLOUDFLARE_API_URL not configured")
        return []

    try:
        url = f"{CLOUDFLARE_API_URL}/execute-query"
        logger.info(f"📡 Calling: {url}")
        logger.info(f"📝 Query: {query[:100]}...")
        
        response = requests.post(
            url,
            json={"query": query, "params": params or []},
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"📥 Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Query returned {len(result) if result else 0} rows")
            return result if result else []
        else:
            logger.error(f"❌ Query failed with status {response.status_code}: {response.text[:200]}")
            return []
            
    except requests.exceptions.Timeout:
        logger.error("❌ Query timeout - tunnel may be slow")
        return []
    except requests.exceptions.ConnectionError:
        logger.error("❌ Connection error - tunnel may be down")
        return []
    except Exception as e:
        logger.error(f"❌ Query exception: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    """Execute a command (INSERT/UPDATE/DELETE) via Cloudflare tunnel."""
    if not CLOUDFLARE_API_URL:
        logger.error("❌ CLOUDFLARE_API_URL not configured")
        return {"success": False, "error": "CLOUDFLARE_API_URL not configured"}

    try:
        url = f"{CLOUDFLARE_API_URL}/execute-command"
        response = requests.post(
            url,
            json={"query": query, "params": params or []},
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"❌ Command failed: {response.status_code} - {response.text[:200]}")
            return {"success": False, "error": f"Status {response.status_code}"}
            
    except Exception as e:
        logger.error(f"❌ Command exception: {e}")
        return {"success": False, "error": str(e)}

def proxy_get_request(endpoint):
    """Generic GET proxy."""
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/{endpoint.lstrip('/')}"
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            return jsonify(response.json()), 200
        return jsonify({"error": f"Failed: {response.status_code}"}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def proxy_post_request(endpoint):
    """Generic POST proxy."""
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/{endpoint.lstrip('/')}"
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
# HEALTH CHECK
# ============================================

@app.route('/health', methods=['GET'])
def health():
    cloudflare_status = "unknown"
    cloudflare_url = CLOUDFLARE_API_URL or "NOT SET"
    
    if CLOUDFLARE_API_URL:
        try:
            response = requests.get(f"{CLOUDFLARE_API_URL}/health", timeout=10)
            if response.status_code == 200:
                cloudflare_status = "connected"
            else:
                cloudflare_status = f"error_{response.status_code}"
        except requests.exceptions.Timeout:
            cloudflare_status = "timeout"
        except requests.exceptions.ConnectionError:
            cloudflare_status = "connection_error"
        except Exception as e:
            cloudflare_status = f"error: {str(e)[:30]}"

    return jsonify({
        "status": "healthy" if cloudflare_status == "connected" else "degraded",
        "service": "SPAR ETL Receiver - Render",
        "timestamp": datetime.now().isoformat(),
        "cloudflare_configured": bool(CLOUDFLARE_API_URL),
        "cloudflare_status": cloudflare_status,
        "cloudflare_url": cloudflare_url
    })

# ============================================
# TEST ENDPOINT
# ============================================

@app.route('/test', methods=['GET'])
def test():
    return jsonify({
        "status": "ok",
        "message": "Render server is running!",
        "cloudflare_configured": bool(CLOUDFLARE_API_URL),
        "cloudflare_url": CLOUDFLARE_API_URL or "NOT SET"
    })

# ============================================
# DEBUG ENDPOINT
# ============================================

@app.route('/debug', methods=['GET'])
def debug():
    return jsonify({
        "service": "SPAR ETL Receiver - Render",
        "status": "running",
        "cloudflare_configured": bool(CLOUDFLARE_API_URL),
        "cloudflare_url": CLOUDFLARE_API_URL or "NOT SET",
        "timestamp": datetime.now().isoformat(),
        "endpoints_available": [
            "/", "/health", "/test", "/debug",
            "/products", "/sales-orders", "/purchase-orders",
            "/recent", "/dynamic-cash-balance", "/customers",
            "/bank-accounts", "/bank-balance",
            "/overdue-pos", "/incoming-documents", 
            "/pending-approvals", "/unprocessed-payments",
            "/receipt/<order_number>"
        ]
    })

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
            "test": "GET /test",
            "debug": "GET /debug",
            "products": "GET /products",
            "products/add": "POST /products/add",
            "sales_orders": "GET /sales-orders, POST /sales-orders",
            "purchase_orders": "GET /purchase-orders, POST /purchase-orders",
            "purchase_orders/lines": "GET /purchase-orders/<po_number>/lines",
            "purchase_orders/<po_number>/approve": "POST",
            "purchase_orders/<po_number>/reject": "POST",
            "purchase_orders/<po_number>": "DELETE",
            "goods_receipt": "POST /goods-receipt",
            "recent": "GET /recent",
            "bank_accounts": "GET /bank-accounts",
            "bank_balance": "GET /bank-balance",
            "dynamic_cash_balance": "GET /dynamic-cash-balance",
            "customers": "GET /customers",
            "receipt/<order_number>": "GET /receipt/<order_number>",
            "overdue_pos": "GET /overdue-pos",
            "incoming_documents": "GET /incoming-documents",
            "pending_approvals": "GET /pending-approvals",
            "unprocessed_payments": "GET /unprocessed-payments"
        }
    })

# ============================================
# PRODUCTS
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured", "data": []}), 500

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

@app.route('/products/add', methods=['POST'])
def add_product_proxy():
    return proxy_post_request('products/add')

# ============================================
# SALES ORDERS
# ============================================

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

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

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    return proxy_post_request('sales-orders')

# ============================================
# RECENT SALES
# ============================================

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

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
        return jsonify({"error": "Cloudflare not configured"}), 500

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

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    return proxy_post_request('purchase-orders')

# ============================================
# PURCHASE ORDER LINES
# ============================================

@app.route('/purchase-orders/<po_number>/lines', methods=['GET'])
def get_purchase_order_lines(po_number):
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

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
# GOODS RECEIPT
# ============================================

@app.route('/goods-receipt', methods=['POST'])
def receive_goods():
    return proxy_post_request('goods-receipt')

# ============================================
# DYNAMIC CASH BALANCE
# ============================================

@app.route('/dynamic-cash-balance', methods=['GET'])
def get_dynamic_cash_balance_proxy():
    return proxy_get_request('dynamic-cash-balance')

# ============================================
# BANK BALANCE
# ============================================

@app.route('/bank-balance', methods=['GET'])
def get_bank_balance_proxy():
    return proxy_get_request('bank-balance')

# ============================================
# BANK ACCOUNTS
# ============================================

@app.route('/bank-accounts', methods=['GET'])
def get_bank_accounts_proxy():
    return proxy_get_request('bank-accounts')

# ============================================
# CUSTOMERS
# ============================================

@app.route('/customers', methods=['GET'])
def get_customers_proxy():
    return proxy_get_request('customers')

# ============================================
# OVERDUE POS
# ============================================

@app.route('/overdue-pos', methods=['GET'])
def get_overdue_pos_proxy():
    return proxy_get_request('overdue-pos')

# ============================================
# INCOMING DOCUMENTS
# ============================================

@app.route('/incoming-documents', methods=['GET'])
def get_incoming_documents_proxy():
    return proxy_get_request('incoming-documents')

# ============================================
# PENDING APPROVALS
# ============================================

@app.route('/pending-approvals', methods=['GET'])
def get_pending_approvals_proxy():
    return proxy_get_request('pending-approvals')

# ============================================
# UNPROCESSED PAYMENTS
# ============================================

@app.route('/unprocessed-payments', methods=['GET'])
def get_unprocessed_payments_proxy():
    return proxy_get_request('unprocessed-payments')

# ============================================
# RECEIPT
# ============================================

@app.route('/receipt/<order_number>', methods=['GET'])
def get_receipt_proxy(order_number):
    if not CLOUDFLARE_API_URL:
        return jsonify({"error": "Cloudflare not configured"}), 500

    try:
        url = f"{CLOUDFLARE_API_URL}/receipt/{order_number}"
        response = requests.get(url, timeout=60)
        
        if response.status_code == 200:
            # Check if response is PDF
            if 'application/pdf' in response.headers.get('content-type', ''):
                return send_file(
                    BytesIO(response.content),
                    as_attachment=True,
                    download_name=f'receipt_{order_number}.pdf',
                    mimetype='application/pdf'
                )
            return jsonify(response.json()), 200
        return jsonify({"error": "Failed to generate receipt"}), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# APPROVE/REJECT/DELETE PO
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
# MAIN
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print("=" * 70)
    print("🛒 SPAR ETL RECEIVER - Render Version (COMPLETE)")
    print("=" * 70)
    print(f"\n🚀 Starting server on port {port}...")
    print(f"🔗 Cloudflare API: {CLOUDFLARE_API_URL or 'NOT SET'}")
    print("\n📋 Available Endpoints:")
    print("   GET  /health")
    print("   GET  /test")
    print("   GET  /debug")
    print("   GET  /products")
    print("   POST /products/add")
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
    print("   GET  /bank-balance")
    print("   GET  /dynamic-cash-balance")
    print("   GET  /customers")
    print("   GET  /receipt/<order_number>")
    print("   GET  /overdue-pos")
    print("   GET  /incoming-documents")
    print("   GET  /pending-approvals")
    print("   GET  /unprocessed-payments")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
