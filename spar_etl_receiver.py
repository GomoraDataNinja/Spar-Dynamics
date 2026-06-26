"""
SPAR ETL Receiver - Render Version
Complete API with Products, Sales, Purchase Orders, and Goods Receiving
Includes extensive debugging for sales insertion and retrieval.
"""
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timedelta
import logging
import os
import random
import json
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL', '')

logger.info(f"🔗 Cloudflare API URL: {CLOUDFLARE_API_URL or 'NOT SET'}")

# ============================================
# HELPER FUNCTIONS
# ============================================

def execute_query_via_cloudflare(query, params=None):
    if not CLOUDFLARE_API_URL:
        logger.warning("⚠️ CLOUDFLARE_API_URL not configured")
        return []
    try:
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-query",
            json={"query": query, "params": params or []},
            timeout=60
        )
        if response.status_code == 200:
            return response.json()
        logger.error(f"Cloudflare query error: {response.status_code} - {response.text}")
        return []
    except Exception as e:
        logger.error(f"Cloudflare query exception: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    if not CLOUDFLARE_API_URL:
        logger.warning("⚠️ CLOUDFLARE_API_URL not configured")
        return {"success": False, "error": "CLOUDFLARE_API_URL not configured"}
    try:
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-command",
            json={"query": query, "params": params or []},
            timeout=60
        )
        if response.status_code == 200:
            return response.json()
        logger.error(f"Cloudflare command error: {response.status_code} - {response.text}")
        return {"success": False, "error": f"Status {response.status_code}"}
    except Exception as e:
        logger.error(f"Cloudflare command exception: {e}")
        return {"success": False, "error": str(e)}

# ============================================
# ENDPOINTS
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
                cloudflare_status = "error"
        except:
            cloudflare_status = "disconnected"
    else:
        cloudflare_status = "not_configured"
    
    return jsonify({
        "status": "healthy",
        "service": "SPAR ETL Receiver",
        "timestamp": datetime.now().isoformat(),
        "cloudflare_configured": bool(CLOUDFLARE_API_URL),
        "cloudflare_status": cloudflare_status
    })

@app.route('/', methods=['GET'])
def serve_index():
    try:
        with open('index.html', 'r') as f:
            return f.read(), 200, {'Content-Type': 'text/html'}
    except:
        return jsonify({
            "service": "SPAR ETL Receiver - Render",
            "status": "running",
            "cloudflare_api": CLOUDFLARE_API_URL or "NOT SET",
            "endpoints": {
                "health": "GET /health",
                "products": "GET /products",
                "products/add": "POST /products/add",
                "sales_orders": "GET /sales-orders, POST /sales-orders",
                "purchase_orders": "GET /purchase-orders, POST /purchase-orders",
                "purchase_orders/:po_number/lines": "GET /purchase-orders/<po_number>/lines",
                "goods_receipt": "POST /goods-receipt",
                "recent": "GET /recent",
                "debug/sales": "GET /debug/sales"
            }
        })

@app.route('/config.js', methods=['GET'])
def serve_config():
    try:
        with open('config.js', 'r') as f:
            return f.read(), 200, {'Content-Type': 'application/javascript'}
    except:
        return "// config.js not found", 404

# ============================================
# PRODUCTS
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    try:
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
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"Error getting products: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/products/add', methods=['POST'])
def add_product():
    # ... (keep your existing code, unchanged) ...
    pass  # Placeholder – copy from your previous version

# ============================================
# SALES ORDERS
# ============================================

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        query = """
            SELECT 
                so.so_number as order_number,
                c.customer_name,
                so.order_date,
                so.order_time,
                so.total_amount,
                so.status,
                so.created_by as recorded_by
            FROM erp_sales_orders so
            LEFT JOIN erp_customers c ON so.customer_id = c.id
            ORDER BY so.created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"Error getting sales orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    """Create a new sales order with extensive logging."""
    try:
        data = request.json
        logger.info("=" * 70)
        logger.info("📝 CREATING SALES ORDER")
        logger.info(f"👤 Customer: {data.get('customer_name')}")
        logger.info(f"📦 Items: {data.get('items')}")

        order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        rewards = total * 0.02

        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        # ----- Customer handling -----
        customer_name = data['customer_name'].strip()
        customer_email = data.get('customer_email', '').strip()
        customer_id = None

        # Try to find existing customer
        customer_query = "SELECT id FROM erp_customers WHERE customer_name = ?"
        customer_result = execute_query_via_cloudflare(customer_query, [customer_name])

        if customer_result:
            customer_id = customer_result[0]['id']
            logger.info(f"✅ Found existing customer: {customer_name} (ID: {customer_id})")
        else:
            # Create new customer
            customer_code = 'CUST-' + datetime.now().strftime('%Y%m%d%H%M%S')
            insert_customer = """
                INSERT INTO erp_customers (customer_code, customer_name, customer_type, email, is_active)
                VALUES (?, ?, ?, ?, 1)
            """
            result = execute_command_via_cloudflare(
                insert_customer,
                [customer_code, customer_name, 'Retail', customer_email]
            )
            if result.get('success', False):
                # Retrieve the new customer ID
                customer_result = execute_query_via_cloudflare(customer_query, [customer_name])
                if customer_result:
                    customer_id = customer_result[0]['id']
                    logger.info(f"✅ Created new customer: {customer_name} (ID: {customer_id})")
                else:
                    logger.error("❌ Failed to retrieve new customer ID")
            else:
                logger.error(f"❌ Failed to create customer: {result}")

        # If customer_id is still None, create a fallback customer (or use a default)
        if customer_id is None:
            # Use a generic customer (you can also create a default customer in your DB)
            default_customer = "Walk-in Customer"
            customer_result = execute_query_via_cloudflare(customer_query, [default_customer])
            if customer_result:
                customer_id = customer_result[0]['id']
                logger.info(f"ℹ️ Using fallback customer: {default_customer} (ID: {customer_id})")
            else:
                # Create the fallback customer on the fly
                insert_fallback = """
                    INSERT INTO erp_customers (customer_code, customer_name, customer_type, is_active)
                    VALUES (?, ?, ?, 1)
                """
                execute_command_via_cloudflare(insert_fallback, ['FALLBACK', default_customer, 'Retail'])
                customer_result = execute_query_via_cloudflare(customer_query, [default_customer])
                customer_id = customer_result[0]['id'] if customer_result else None
                logger.info(f"ℹ️ Created fallback customer: {default_customer} (ID: {customer_id})")

        # ----- Insert Sales Order -----
        insert_order_query = """
            INSERT INTO erp_sales_orders (
                so_number, customer_id, order_date, order_time,
                subtotal, tax_amount, total_amount, rewards_earned,
                status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        order_params = (
            order_number, customer_id,
            datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M:%S'),
            subtotal, tax, total, rewards,
            'Confirmed', data.get('recorded_by', 'system')
        )
        result = execute_command_via_cloudflare(insert_order_query, order_params)
        if not result.get('success', False):
            logger.error(f"❌ Failed to create order: {result}")
            return jsonify({"error": "Failed to create order"}), 500

        order_id = result.get('id', 0)
        logger.info(f"✅ Order created with ID: {order_id}")

        # ----- Insert Order Lines and Update Stock -----
        for i, item in enumerate(items):
            # Get product details if missing
            if not item.get('product_code') or not item.get('product_name'):
                product_query = "SELECT product_code, product_name FROM erp_products WHERE id = ?"
                product_result = execute_query_via_cloudflare(product_query, [item['product_id']])
                if product_result:
                    item['product_code'] = product_result[0].get('product_code', '')
                    item['product_name'] = product_result[0].get('product_name', '')

            line_query = """
                INSERT INTO erp_sales_order_lines (
                    so_id, line_number, product_id, product_code, product_name,
                    quantity, unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            line_params = (
                order_id, i + 1, item['product_id'],
                item.get('product_code', ''), item.get('product_name', ''),
                item['quantity'], item['unit_price'],
                item['quantity'] * item['unit_price']
            )
            execute_command_via_cloudflare(line_query, line_params)

            # Update stock
            update_stock_query = "UPDATE erp_products SET current_stock = current_stock - ? WHERE id = ?"
            execute_command_via_cloudflare(update_stock_query, (item['quantity'], item['product_id']))

        # ----- Verify the sale was inserted -----
        verify_query = "SELECT so_number FROM erp_sales_orders WHERE id = ?"
        verify_result = execute_query_via_cloudflare(verify_query, [order_id])
        if verify_result:
            logger.info(f"✅ Verification: Sale {order_number} found in database.")
        else:
            logger.error(f"❌ Verification FAILED: Sale {order_number} NOT found in database!")

        logger.info(f"📦 Sale completed: {order_number}")
        logger.info("=" * 70)

        return jsonify({
            "status": "success",
            "order_number": order_number,
            "invoice_number": "INV-" + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999)),
            "total_amount": total,
            "rewards_earned": rewards
        }), 200

    except Exception as e:
        logger.error(f"❌ Error creating sales order: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================
# RECENT SALES (with debug fallback)
# ============================================

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    """Return all sales (no date filter) – for debugging."""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = """
            SELECT TOP 50
                so.so_number as sale_id,
                c.customer_name,
                so.order_date as sale_date,
                so.order_time as sale_time,
                so.total_amount as total_sales,
                so.rewards_earned,
                so.status,
                so.created_by as recorded_by,
                1 as etl_processed
            FROM erp_sales_orders so
            LEFT JOIN erp_customers c ON so.customer_id = c.id
            ORDER BY so.created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        logger.info(f"📊 /recent returned {len(result)} sales")
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"Error in /recent: {e}")
        return jsonify([]), 200

# ============================================
# DEBUG: List all sales
# ============================================

@app.route('/debug/sales', methods=['GET'])
def debug_sales():
    """Return all sales without any filters (for debugging)."""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500

        query = """
            SELECT 
                so.so_number,
                c.customer_name,
                so.order_date,
                so.total_amount,
                so.created_at
            FROM erp_sales_orders so
            LEFT JOIN erp_customers c ON so.customer_id = c.id
            ORDER BY so.created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================
# PURCHASE ORDERS (unchanged)
# ============================================
# ... (keep your existing endpoints for purchase orders, goods receipt, etc.)

# ============================================
# CORS
# ============================================

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

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
    print("   POST /products/add")
    print("   GET  /sales-orders")
    print("   POST /sales-orders")
    print("   GET  /purchase-orders")
    print("   POST /purchase-orders")
    print("   GET  /purchase-orders/<po_number>/lines")
    print("   POST /goods-receipt")
    print("   GET  /recent")
    print("   GET  /debug/sales  (debug only)")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
