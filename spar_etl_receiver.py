"""
SPAR ETL Receiver - Render Version with Cloudflare Tunnel
No pandas/pyodbc required - uses requests only
"""
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import logging
import os
import random
import requests
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================
# CONFIGURATION - From Environment Variables
# ============================================

# Your Cloudflare URL that exposes your local SQL Server API
CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL', 'https://cope-visitors-flow-becoming.trycloudflare.com')

# ============================================
# DATABASE CONNECTION - Via Cloudflare API
# ============================================

def execute_query_via_cloudflare(query, params=None):
    """
    Execute a SELECT query by forwarding to your local SQL Server via Cloudflare
    """
    try:
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-query",
            json={
                "query": query,
                "params": params or []
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Cloudflare API error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Error calling Cloudflare API: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    """
    Execute an INSERT/UPDATE/DELETE command via Cloudflare
    """
    try:
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-command",
            json={
                "query": query,
                "params": params or []
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Cloudflare API error: {response.status_code} - {response.text}")
            return {"success": False, "error": f"Status {response.status_code}"}
    except Exception as e:
        logger.error(f"Error calling Cloudflare API: {e}")
        return {"success": False, "error": str(e)}

# ============================================
# API ENDPOINTS
# ============================================

@app.route('/health', methods=['GET'])
def health():
    try:
        response = requests.get(f"{CLOUDFLARE_API_URL}/health", timeout=10)
        cloudflare_status = "connected" if response.status_code == 200 else "error"
    except:
        cloudflare_status = "disconnected"
    
    return jsonify({
        "status": "healthy",
        "mode": "Render with Cloudflare Tunnel",
        "cloudflare_api": CLOUDFLARE_API_URL,
        "cloudflare_status": cloudflare_status,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/products', methods=['GET'])
def get_products():
    try:
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
                (ISNULL(p.current_stock, 0) - ISNULL(p.reserved_stock, 0)) AS available_stock,
                CASE 
                    WHEN (ISNULL(p.current_stock, 0) - ISNULL(p.reserved_stock, 0)) <= 0 THEN 'out-of-stock'
                    WHEN (ISNULL(p.current_stock, 0) - ISNULL(p.reserved_stock, 0)) <= p.reorder_level THEN 'low-stock'
                    ELSE 'in-stock'
                END AS stock_status,
                CASE 
                    WHEN (ISNULL(p.current_stock, 0) - ISNULL(p.reserved_stock, 0)) <= 0 THEN 'Out of Stock'
                    WHEN (ISNULL(p.current_stock, 0) - ISNULL(p.reserved_stock, 0)) <= p.reorder_level THEN 'Low Stock'
                    ELSE 'In Stock'
                END AS stock_label
            FROM products p
            LEFT JOIN product_categories pc ON p.category_id = pc.id
            WHERE p.is_active = 1
            ORDER BY pc.category_name, p.product_name
        """
        
        result = execute_query_via_cloudflare(query)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting products: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    try:
        data = request.json
        order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        rewards = total * 0.02
        
        insert_order_query = """
            INSERT INTO sales_orders (
                order_number, customer_name, customer_email, order_date, order_time,
                subtotal, tax_amount, total_amount, rewards_earned,
                status, recorded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        order_params = (
            order_number, data['customer_name'], data.get('customer_email', ''),
            datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M:%S'),
            subtotal, tax, total, rewards,
            'Confirmed', data.get('recorded_by', 'system')
        )
        
        result = execute_command_via_cloudflare(insert_order_query, order_params)
        
        if not result.get('success', False):
            return jsonify({"error": "Failed to create order"}), 500
        
        order_id = result.get('id', 0)
        
        for i, item in enumerate(items):
            product_query = """
                SELECT product_code, product_name, category_name, current_stock
                FROM products p
                LEFT JOIN product_categories pc ON p.category_id = pc.id
                WHERE p.id = ?
            """
            product_result = execute_query_via_cloudflare(product_query, [item['product_id']])
            
            if not product_result:
                continue
            
            product = product_result[0]
            
            line_query = """
                INSERT INTO sales_order_lines (
                    order_id, line_number, product_id, product_code, product_name,
                    product_category, quantity, unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            line_params = (
                order_id, i + 1, item['product_id'], product.get('product_code', ''),
                product.get('product_name', ''), product.get('category_name', ''),
                item['quantity'], item['unit_price'],
                item['quantity'] * item['unit_price']
            )
            execute_command_via_cloudflare(line_query, line_params)
            
            update_stock_query = """
                UPDATE products SET current_stock = current_stock - ? WHERE id = ?
            """
            execute_command_via_cloudflare(update_stock_query, (item['quantity'], item['product_id']))
        
        invoice_number = 'INV-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        invoice_query = """
            INSERT INTO sales_invoices (
                invoice_number, order_id, customer_name, customer_email,
                invoice_date, due_date, subtotal, tax_amount, total_amount,
                recorded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        invoice_params = (
            invoice_number, order_id, data['customer_name'], data.get('customer_email', ''),
            datetime.now().strftime('%Y-%m-%d'), (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            subtotal, tax, total, data.get('recorded_by', 'system')
        )
        execute_command_via_cloudflare(invoice_query, invoice_params)
        
        return jsonify({
            "status": "success",
            "order_number": order_number,
            "invoice_number": invoice_number,
            "total_amount": total,
            "rewards_earned": rewards
        }), 200
        
    except Exception as e:
        logger.error(f"Error creating sales order: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    try:
        query = """
            SELECT 
                so.order_number, so.customer_name, so.order_date, so.order_time,
                so.total_amount, so.rewards_earned, so.status,
                so.recorded_by
            FROM sales_orders so
            ORDER BY so.order_date DESC, so.order_time DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting sales orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    try:
        data = request.json
        po_number = 'PO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        
        insert_po_query = """
            INSERT INTO purchase_orders (
                po_number, supplier_name, supplier_email, order_date,
                expected_delivery_date, subtotal, tax_amount, total_amount,
                status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        po_params = (
            po_number, data['supplier_name'], data.get('supplier_email', ''),
            datetime.now().strftime('%Y-%m-%d'), data.get('expected_delivery_date'),
            subtotal, tax, total, 'Draft', data.get('created_by', 'system')
        )
        
        result = execute_command_via_cloudflare(insert_po_query, po_params)
        
        if not result.get('success', False):
            return jsonify({"error": "Failed to create PO"}), 500
        
        po_id = result.get('id', 0)
        
        for i, item in enumerate(items):
            line_query = """
                INSERT INTO purchase_order_lines (
                    po_id, line_number, product_id, product_code, product_name,
                    quantity, unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            line_params = (
                po_id, i + 1, item['product_id'], item.get('product_code', ''),
                item.get('product_name', ''), item['quantity'], 
                item['unit_price'], item['quantity'] * item['unit_price']
            )
            execute_command_via_cloudflare(line_query, line_params)
        
        return jsonify({
            "status": "success",
            "po_number": po_number,
            "total_amount": total
        }), 200
        
    except Exception as e:
        logger.error(f"Error creating purchase order: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    try:
        query = """
            SELECT po_number, supplier_name, order_date, expected_delivery_date,
                   status, total_amount
            FROM purchase_orders 
            ORDER BY order_date DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting purchase orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    try:
        query = """
            SELECT TOP 50
                order_number as sale_id, customer_name, order_date as sale_date,
                order_time as sale_time, total_amount as total_sales,
                rewards_earned, status, recorded_by,
                1 as etl_processed
            FROM sales_orders 
            WHERE order_date = CAST(GETDATE() AS DATE)
            ORDER BY order_date DESC, order_time DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting recent sales: {e}")
        return jsonify([]), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        logger.info(f"Received sale from: {data.get('customer_name')}")
        
        insert_query = """
            INSERT INTO sales_orders (
                order_number, customer_name, customer_email, order_date, order_time,
                total_amount, rewards_earned, status, recorded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get('sale_id', 'WEB-' + datetime.now().strftime('%Y%m%d%H%M%S')),
            data.get('customer_name', 'Webhook Customer'),
            data.get('customer_email', ''),
            data.get('sale_date', datetime.now().strftime('%Y-%m-%d')),
            data.get('sale_time', datetime.now().strftime('%H:%M:%S')),
            data.get('total_sales', 0),
            data.get('rewards_earned', 0),
            'Confirmed',
            data.get('recorded_by', 'webhook')
        )
        
        result = execute_command_via_cloudflare(insert_query, params)
        
        if result.get('success', False):
            return jsonify({"status": "success", "message": "Sale received"}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to save"}), 500
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/my-sales', methods=['GET'])
def get_my_sales():
    try:
        recorded_by = request.args.get('recorded_by', '')
        if not recorded_by:
            return jsonify({"error": "recorded_by parameter required"}), 400
        
        query = """
            SELECT TOP 50 
                order_number as sale_id, customer_name, order_date as sale_date,
                order_time as sale_time, total_amount as total_sales,
                rewards_earned, status, recorded_by
            FROM sales_orders 
            WHERE recorded_by = ?
            AND order_date = CAST(GETDATE() AS DATE)
            ORDER BY order_date DESC, order_time DESC
        """
        result = execute_query_via_cloudflare(query, [recorded_by])
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting user sales: {e}")
        return jsonify([]), 200

@app.route('/sales/stats', methods=['GET'])
def get_sales_stats():
    try:
        query = """
            SELECT 
                COUNT(*) as total_orders,
                SUM(total_amount) as total_revenue,
                AVG(total_amount) as avg_order_value,
                SUM(rewards_earned) as total_rewards
            FROM sales_orders
            WHERE order_date = CAST(GETDATE() AS DATE)
        """
        result = execute_query_via_cloudflare(query)
        
        stats = result[0] if result else {}
        
        return jsonify({
            'today_sales': stats.get('total_revenue', 0),
            'today_orders': stats.get('total_orders', 0),
            'avg_order_value': stats.get('avg_order_value', 0),
            'total_rewards': stats.get('total_rewards', 0)
        }), 200
    except Exception as e:
        logger.error(f"Error getting sales stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "SPAR ETL Receiver - Render",
        "status": "running",
        "cloudflare_api": CLOUDFLARE_API_URL,
        "endpoints": {
            "health": "GET /health",
            "products": "GET /products",
            "sales_orders": "POST /sales-orders, GET /sales-orders",
            "purchase_orders": "POST /purchase-orders, GET /purchase-orders",
            "recent": "GET /recent",
            "webhook": "POST /webhook",
            "my_sales": "GET /my-sales?recorded_by=username",
            "sales/stats": "GET /sales/stats"
        }
    })

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print("=" * 70)
    print("🛒 SPAR ETL RECEIVER - Render Version")
    print("=" * 70)
    print(f"\n🚀 Starting server on port {port}...")
    print(f"\n📍 API URL: http://localhost:{port}")
    print(f"🔗 Cloudflare API: {CLOUDFLARE_API_URL}")
    print("\nPress Ctrl+C to stop")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
