"""
SPAR ETL Receiver - Render Version
Complete API with Products, Sales, Purchase Orders, and Goods Receiving
Connects to local SQL Server via Cloudflare tunnel
"""

from flask import Flask, request, jsonify, send_file
from datetime import datetime
import logging
import os
import random
import requests
import traceback
import time
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
# CLOUDFLARE PROXY FUNCTIONS
# ============================================

def execute_query_via_cloudflare(query, params=None):
    """Execute a SELECT query via Cloudflare tunnel"""
    if not CLOUDFLARE_API_URL:
        logger.error("❌ CLOUDFLARE_API_URL not configured")
        return []

    try:
        url = f"{CLOUDFLARE_API_URL}/execute-query"
        logger.info(f"📊 Forwarding query to: {url}")

        response = requests.post(
            url,
            json={"query": query, "params": params or []},
            timeout=30,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Query returned {len(result) if isinstance(result, list) else '?'} rows")
            return result
        else:
            logger.error(f"❌ Cloudflare query error: {response.status_code} - {response.text[:200]}")
            return []
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ Connection error to Cloudflare: {e}")
        return []
    except requests.exceptions.Timeout:
        logger.error("❌ Cloudflare query timeout")
        return []
    except Exception as e:
        logger.error(f"❌ Cloudflare query exception: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    """Execute an INSERT/UPDATE/DELETE command via Cloudflare"""
    if not CLOUDFLARE_API_URL:
        logger.error("❌ CLOUDFLARE_API_URL not configured")
        return {"success": False, "error": "CLOUDFLARE_API_URL not configured"}

    try:
        url = f"{CLOUDFLARE_API_URL}/execute-command"
        logger.info(f"📝 Forwarding command to: {url}")

        response = requests.post(
            url,
            json={"query": query, "params": params or []},
            timeout=30,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Command executed: {result}")
            return result
        else:
            logger.error(f"❌ Cloudflare command error: {response.status_code} - {response.text[:200]}")
            return {"success": False, "error": f"Status {response.status_code}"}
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ Connection error to Cloudflare: {e}")
        return {"success": False, "error": f"Connection error: {str(e)}"}
    except requests.exceptions.Timeout:
        logger.error("❌ Cloudflare command timeout")
        return {"success": False, "error": "Timeout"}
    except Exception as e:
        logger.error(f"❌ Cloudflare command exception: {e}")
        return {"success": False, "error": str(e)}

# ============================================
# HEALTH CHECK
# ============================================

@app.route('/health', methods=['GET'])
def health():
    cloudflare_status = "unknown"
    cloudflare_details = {}

    if CLOUDFLARE_API_URL:
        try:
            health_url = f"{CLOUDFLARE_API_URL}/health"
            logger.info(f"🔄 Checking Cloudflare tunnel at: {health_url}")
            response = requests.get(health_url, timeout=10)

            if response.status_code == 200:
                try:
                    data = response.json()
                    cloudflare_status = "connected"
                    cloudflare_details = {
                        "local_db_status": data.get("database", "unknown"),
                        "local_product_count": data.get("product_count", 0)
                    }
                    logger.info(f"✅ Cloudflare tunnel connected. Details: {cloudflare_details}")
                except:
                    cloudflare_status = "connected (response not JSON)"
            else:
                cloudflare_status = f"error_{response.status_code}"
                logger.error(f"❌ Cloudflare health check failed: {response.status_code}")
        except requests.exceptions.Timeout:
            cloudflare_status = "disconnected (timeout)"
            logger.error("❌ Cloudflare tunnel timeout")
        except requests.exceptions.ConnectionError:
            cloudflare_status = "disconnected (connection refused)"
            logger.error("❌ Cannot reach Cloudflare tunnel")
        except Exception as e:
            cloudflare_status = f"error: {str(e)[:50]}"
            logger.error(f"❌ Error checking Cloudflare: {e}")
    else:
        cloudflare_status = "not_configured"

    return jsonify({
        "status": "healthy" if cloudflare_status == "connected" else "degraded",
        "service": "SPAR ETL Receiver - Render",
        "timestamp": datetime.now().isoformat(),
        "cloudflare_configured": bool(CLOUDFLARE_API_URL),
        "cloudflare_status": cloudflare_status,
        "cloudflare_url": CLOUDFLARE_API_URL,
        "cloudflare_details": cloudflare_details
    })

# ============================================
# PRODUCTS ENDPOINT - GET
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    """Get all active products from database"""
    try:
        logger.info("📦 Fetching products...")

        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = """
            SELECT 
                p.id,
                p.product_code,
                p.product_name,
                pc.category_name,
                p.unit_of_measure,
                p.unit_price,
                p.cost_price,
                p.current_stock,
                p.reorder_level,
                p.current_stock AS available_stock,
                CASE 
                    WHEN p.current_stock <= 0 THEN 'out-of-stock'
                    WHEN p.current_stock <= p.reorder_level THEN 'low-stock'
                    ELSE 'in-stock'
                END AS stock_status,
                CASE 
                    WHEN p.current_stock <= 0 THEN 'Out of Stock'
                    WHEN p.current_stock <= p.reorder_level THEN 'Low Stock'
                    ELSE 'In Stock'
                END AS stock_label,
                p.is_active
            FROM erp_products p
            LEFT JOIN erp_product_categories pc ON p.category_id = pc.id
            WHERE p.is_active = 1
            ORDER BY pc.category_name, p.product_name
        """
        result = execute_query_via_cloudflare(query)

        if result is None:
            return jsonify([]), 200

        return jsonify(result), 200
    except Exception as e:
        logger.error(f"❌ Error getting products: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# SALES ORDERS ENDPOINT - GET
# ============================================

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    """Get all sales orders from database"""
    try:
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
                so.rewards_earned,
                c.rewards_balance
            FROM erp_sales_orders so
            LEFT JOIN erp_customers c ON so.customer_id = c.id
            ORDER BY so.created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting sales orders: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# RECENT SALES ENDPOINT - GET
# ============================================

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    """Get recent sales from database"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = """
            SELECT TOP 50
                so.so_number as sale_id,
                c.customer_name,
                so.order_date as sale_date,
                CONVERT(VARCHAR, so.order_time, 108) as sale_time,
                so.total_amount as total_sales,
                so.rewards_earned,
                so.status,
                so.approval_status,
                so.created_by as recorded_by,
                c.rewards_balance,
                1 as etl_processed
            FROM erp_sales_orders so
            LEFT JOIN erp_customers c ON so.customer_id = c.id
            ORDER BY so.created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting recent sales: {e}")
        return jsonify([]), 200

# ============================================
# PURCHASE ORDERS ENDPOINT - GET
# ============================================

@app.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    """Get all purchase orders from database"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = """
            SELECT 
                po.id,
                po.po_number,
                s.supplier_name,
                po.order_date,
                po.expected_delivery_date,
                po.status,
                po.approval_status,
                po.total_amount
            FROM erp_purchase_orders po
            LEFT JOIN erp_suppliers s ON po.supplier_id = s.id
            ORDER BY po.created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting purchase orders: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# PURCHASE ORDER LINES ENDPOINT - GET
# ============================================

@app.route('/purchase-orders/<po_number>/lines', methods=['GET'])
def get_purchase_order_lines(po_number):
    """Get lines for a specific purchase order"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = """
            SELECT 
                pol.id,
                pol.product_id,
                pol.product_code,
                pol.product_name,
                pol.quantity,
                pol.unit_price,
                pol.line_total
            FROM erp_purchase_order_lines pol
            INNER JOIN erp_purchase_orders po ON pol.po_id = po.id
            WHERE po.po_number = ?
            ORDER BY pol.line_number
        """
        result = execute_query_via_cloudflare(query, [po_number])
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting PO lines: {e}")
        return jsonify([]), 200

# ============================================
# SALES ORDERS ENDPOINT - POST
# ============================================

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    """Create a new sales order"""
    try:
        data = request.json
        logger.info(f"📝 Creating sales order for: {data.get('customer_name')}")

        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        # Forward to local server
        url = f"{CLOUDFLARE_API_URL}/sales-orders"
        response = requests.post(
            url,
            json=data,
            timeout=60,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": f"Error from local server: {response.status_code}"}), response.status_code

    except Exception as e:
        logger.error(f"❌ Error creating sales order: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# PURCHASE ORDERS ENDPOINT - POST
# ============================================

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    """Create a new purchase order"""
    try:
        data = request.json
        logger.info(f"📦 Creating purchase order for: {data.get('supplier_name')}")

        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        url = f"{CLOUDFLARE_API_URL}/purchase-orders"
        response = requests.post(
            url,
            json=data,
            timeout=60,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": f"Error from local server: {response.status_code}"}), response.status_code

    except Exception as e:
        logger.error(f"❌ Error creating purchase order: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# GOODS RECEIPT ENDPOINT - POST
# ============================================

@app.route('/goods-receipt', methods=['POST'])
def receive_goods():
    """Receive goods and update stock"""
    try:
        data = request.json
        logger.info(f"📥 Receiving goods for PO: {data.get('po_number')}")

        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        url = f"{CLOUDFLARE_API_URL}/goods-receipt"
        response = requests.post(
            url,
            json=data,
            timeout=60,
            headers={"Content-Type": "application/json"}
        )

        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": f"Error from local server: {response.status_code}"}), response.status_code

    except Exception as e:
        logger.error(f"❌ Error receiving goods: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: BANK ACCOUNTS PROXY - GET
# ============================================

@app.route('/bank-accounts', methods=['GET'])
def get_bank_accounts_proxy():
    """Proxy to get bank accounts"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = "SELECT id, account_name, account_number, bank_name, balance, cash_balance, currency, is_active FROM erp_bank_accounts WHERE is_active = 1 ORDER BY account_name"
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting bank accounts: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: DYNAMIC CASH BALANCE PROXY - GET
# ============================================

@app.route('/dynamic-cash-balance', methods=['GET'])
def get_dynamic_cash_balance_proxy():
    """Proxy to get dynamic cash balance"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        # Get cash balance from bank accounts
        result = execute_query_via_cloudflare("SELECT ISNULL(SUM(cash_balance), 0) as cash_balance FROM erp_bank_accounts")
        cash_balance = result[0]['cash_balance'] if result and len(result) > 0 else 0

        # Get transaction total
        result2 = execute_query_via_cloudflare("SELECT ISNULL(SUM(amount * transaction_sign), 0) as transaction_total FROM erp_cash_transactions")
        transaction_total = result2[0]['transaction_total'] if result2 and len(result2) > 0 else 0

        # Get pending purchases
        result3 = execute_query_via_cloudflare("SELECT ISNULL(SUM(total_amount), 0) as pending_purchases FROM erp_purchase_orders WHERE status NOT IN ('Received', 'Cancelled')")
        pending_purchases = result3[0]['pending_purchases'] if result3 and len(result3) > 0 else 0

        # Get pending payments
        result4 = execute_query_via_cloudflare("SELECT ISNULL(SUM(amount), 0) as pending_payments FROM erp_payments WHERE status = 'Pending'")
        pending_payments = result4[0]['pending_payments'] if result4 and len(result4) > 0 else 0

        return jsonify({
            "cash_balance": float(cash_balance),
            "transaction_total": float(transaction_total),
            "pending_purchases": float(pending_purchases),
            "pending_payments": float(pending_payments),
            "available_cash": float(cash_balance) - float(pending_purchases) - float(pending_payments)
        }), 200

    except Exception as e:
        logger.error(f"❌ Error getting dynamic cash balance: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: CASH TRANSACTIONS PROXY - GET
# ============================================

@app.route('/cash-transactions', methods=['GET'])
def get_cash_transactions_proxy():
    """Proxy to get cash transactions"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = """
            SELECT 
                id,
                transaction_date,
                transaction_type,
                reference_number,
                amount,
                transaction_sign,
                description,
                created_by
            FROM erp_cash_transactions
            ORDER BY created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting cash transactions: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: CUSTOMERS PROXY - GET
# ============================================

@app.route('/customers', methods=['GET'])
def get_customers_proxy():
    """Proxy to get customers with rewards"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = """
            SELECT 
                id,
                customer_code,
                customer_name,
                customer_type,
                email,
                phone,
                rewards_balance,
                is_active
            FROM erp_customers
            WHERE is_active = 1
            ORDER BY customer_name
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting customers: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: RECEIPT PROXY - GET
# ============================================

@app.route('/receipt/<order_number>', methods=['GET'])
def get_receipt_proxy(order_number):
    """Proxy to generate receipt PDF"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        url = f"{CLOUDFLARE_API_URL}/receipt/{order_number}"
        response = requests.get(url, timeout=60)

        if response.status_code == 200:
            return send_file(
                BytesIO(response.content),
                as_attachment=True,
                download_name=f'receipt_{order_number}.pdf',
                mimetype='application/pdf'
            )
        else:
            return jsonify({"error": "Failed to generate receipt"}), response.status_code

    except Exception as e:
        logger.error(f"❌ Error generating receipt: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# APPROVE PURCHASE ORDER PROXY - POST
# ============================================

@app.route('/purchase-orders/<po_number>/approve', methods=['POST'])
def approve_purchase_order_proxy(po_number):
    """Proxy to approve purchase order"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        url = f"{CLOUDFLARE_API_URL}/purchase-orders/{po_number}/approve"
        response = requests.post(url, timeout=30)

        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": f"Error from local server: {response.status_code}"}), response.status_code

    except Exception as e:
        logger.error(f"❌ Error approving PO: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# REJECT PURCHASE ORDER PROXY - POST
# ============================================

@app.route('/purchase-orders/<po_number>/reject', methods=['POST'])
def reject_purchase_order_proxy(po_number):
    """Proxy to reject purchase order"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        url = f"{CLOUDFLARE_API_URL}/purchase-orders/{po_number}/reject"
        response = requests.post(url, timeout=30)

        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": f"Error from local server: {response.status_code}"}), response.status_code

    except Exception as e:
        logger.error(f"❌ Error rejecting PO: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# DELETE EMPTY PURCHASE ORDER PROXY - DELETE
# ============================================

@app.route('/purchase-orders/<po_number>', methods=['DELETE'])
def delete_empty_purchase_order_proxy(po_number):
    """Proxy to delete empty purchase order"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        url = f"{CLOUDFLARE_API_URL}/purchase-orders/{po_number}"
        response = requests.delete(url, timeout=30)

        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            return jsonify({"error": f"Error from local server: {response.status_code}"}), response.status_code

    except Exception as e:
        logger.error(f"❌ Error deleting PO: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# CORS HEADERS
# ============================================

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# ============================================
# ROOT ENDPOINT
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
            "purchase_orders/<po_number>/approve": "POST /purchase-orders/<po_number>/approve",
            "purchase_orders/<po_number>/reject": "POST /purchase-orders/<po_number>/reject",
            "purchase_orders/<po_number>": "DELETE /purchase-orders/<po_number>",
            "goods_receipt": "POST /goods-receipt",
            "recent": "GET /recent",
            "bank-accounts": "GET /bank-accounts",
            "dynamic-cash-balance": "GET /dynamic-cash-balance",
            "cash-transactions": "GET /cash-transactions",
            "customers": "GET /customers",
            "receipt/<order_number>": "GET /receipt/<order_number>"
        }
    })

# ============================================
# MAIN
# ============================================

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
    print("   GET  /cash-transactions")
    print("   GET  /customers")
    print("   GET  /receipt/<order_number>")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
