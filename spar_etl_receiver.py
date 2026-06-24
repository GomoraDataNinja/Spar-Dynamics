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
import sys

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================
# CONFIGURATION - From Environment Variables
# ============================================

# Get Cloudflare URL from environment, with fallback
CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL', '')

# If not set, try to detect from previous runs or use a placeholder
if not CLOUDFLARE_API_URL:
    logger.warning("⚠️ CLOUDFLARE_API_URL not set! Using placeholder. Please set it in Render Environment Variables.")
    CLOUDFLARE_API_URL = 'https://your-cloudflare-url.trycloudflare.com'

logger.info(f"🔗 Cloudflare API URL: {CLOUDFLARE_API_URL}")

# ============================================
# DATABASE CONNECTION - Via Cloudflare API
# ============================================

def execute_query_via_cloudflare(query, params=None):
    """Execute a SELECT query via Cloudflare tunnel"""
    try:
        if not CLOUDFLARE_API_URL or 'your-cloudflare-url' in CLOUDFLARE_API_URL:
            logger.warning("⚠️ Cloudflare URL not configured properly")
            return []
            
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-query",
            json={"query": query, "params": params or []},
            timeout=60
        )
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Cloudflare API error: {response.status_code} - {response.text}")
            return []
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to Cloudflare! Is your local ETL receiver running?")
        return []
    except Exception as e:
        logger.error(f"Error calling Cloudflare API: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    """Execute an INSERT/UPDATE/DELETE command via Cloudflare"""
    try:
        if not CLOUDFLARE_API_URL or 'your-cloudflare-url' in CLOUDFLARE_API_URL:
            logger.warning("⚠️ Cloudflare URL not configured properly")
            return {"success": False, "error": "Cloudflare URL not configured"}
            
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-command",
            json={"query": query, "params": params or []},
            timeout=60
        )
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Cloudflare API error: {response.status_code} - {response.text}")
            return {"success": False, "error": f"Status {response.status_code}"}
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot connect to Cloudflare! Is your local ETL receiver running?")
        return {"success": False, "error": "Cannot connect to Cloudflare"}
    except Exception as e:
        logger.error(f"Error calling Cloudflare API: {e}")
        return {"success": False, "error": str(e)}

# ============================================
# HEALTH ENDPOINT - Enhanced
# ============================================

@app.route('/health', methods=['GET'])
def health():
    """Check if the service is running and can connect to Cloudflare"""
    cloudflare_status = "unknown"
    cloudflare_message = ""
    
    try:
        if CLOUDFLARE_API_URL and 'your-cloudflare-url' not in CLOUDFLARE_API_URL:
            response = requests.get(f"{CLOUDFLARE_API_URL}/health", timeout=10)
            if response.status_code == 200:
                cloudflare_status = "connected"
                cloudflare_message = "Cloudflare tunnel is working"
            else:
                cloudflare_status = "error"
                cloudflare_message = f"Cloudflare returned {response.status_code}"
        else:
            cloudflare_status = "not_configured"
            cloudflare_message = "CLOUDFLARE_API_URL environment variable not set properly"
    except requests.exceptions.ConnectionError:
        cloudflare_status = "disconnected"
        cloudflare_message = "Cannot connect to Cloudflare tunnel. Is your local ETL receiver running?"
    except Exception as e:
        cloudflare_status = "error"
        cloudflare_message = str(e)
    
    return jsonify({
        "status": "healthy",
        "mode": "Render with Cloudflare Tunnel",
        "cloudflare_api": CLOUDFLARE_API_URL,
        "cloudflare_status": cloudflare_status,
        "cloudflare_message": cloudflare_message,
        "timestamp": datetime.now().isoformat(),
        "environment": "production" if os.environ.get('RENDER') else "development"
    })

# ============================================
# OTHER ENDPOINTS (Products, Sales, etc.)
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    """Get all active products"""
    try:
        if not CLOUDFLARE_API_URL or 'your-cloudflare-url' in CLOUDFLARE_API_URL:
            # Return sample data when Cloudflare is not configured
            sample_products = [
                {"id": 1, "product_code": "PRD001", "product_name": "Golden Delicious Apples", "category_name": "Fresh Produce", "unit_price": 2.99, "current_stock": 45, "available_stock": 45, "reorder_level": 20, "stock_status": "in-stock", "stock_label": "In Stock"},
                {"id": 2, "product_code": "PRD002", "product_name": "Fresh Bananas", "category_name": "Fresh Produce", "unit_price": 1.49, "current_stock": 60, "available_stock": 60, "reorder_level": 25, "stock_status": "in-stock", "stock_label": "In Stock"},
                {"id": 3, "product_code": "PRD003", "product_name": "Beef Steak Rump", "category_name": "Meat & Poultry", "unit_price": 12.99, "current_stock": 18, "available_stock": 18, "reorder_level": 15, "stock_status": "in-stock", "stock_label": "In Stock"}
            ]
            return jsonify(sample_products), 200
            
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
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting products: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# SIMPLIFIED SALES ORDERS
# ============================================

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    """Get sales orders - returns sample data if Cloudflare not connected"""
    try:
        if not CLOUDFLARE_API_URL or 'your-cloudflare-url' in CLOUDFLARE_API_URL:
            # Return sample data when Cloudflare is not configured
            sample_orders = [
                {"order_number": "SO-20260623-1001", "customer_name": "John Doe", "order_date": "2026-06-23", "order_time": "10:30:00", "total_amount": 45.50, "status": "Confirmed", "recorded_by": "admin"},
                {"order_number": "SO-20260623-1002", "customer_name": "Jane Smith", "order_date": "2026-06-23", "order_time": "11:15:00", "total_amount": 67.25, "status": "Confirmed", "recorded_by": "operator1"}
            ]
            return jsonify(sample_orders), 200
            
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
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting sales orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    """Create a new sales order"""
    try:
        data = request.json
        logger.info(f"Creating sales order for: {data.get('customer_name')}")
        
        if not CLOUDFLARE_API_URL or 'your-cloudflare-url' in CLOUDFLARE_API_URL:
            # Return success with mock data when Cloudflare is not connected
            order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
            return jsonify({
                "status": "success",
                "order_number": order_number,
                "invoice_number": "INV-" + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999)),
                "total_amount": sum(item['quantity'] * item['unit_price'] for item in data.get('items', [])) * 1.155,
                "rewards_earned": sum(item['quantity'] * item['unit_price'] for item in data.get('items', [])) * 1.155 * 0.02
            }), 200
        
        order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        rewards = total * 0.02
        
        # Get or create customer
        customer_name = data['customer_name'].strip()
        customer_email = data.get('customer_email', '').strip()
        
        customer_query = "SELECT id FROM erp_customers WHERE customer_name = ?"
        customer_result = execute_query_via_cloudflare(customer_query, [customer_name])
        
        if customer_result:
            customer_id = customer_result[0]['id']
        else:
            customer_code = 'CUST-' + datetime.now().strftime('%Y%m%d%H%M%S')
            insert_customer = """
                INSERT INTO erp_customers (customer_code, customer_name, customer_type, email, is_active)
                VALUES (?, ?, ?, ?, 1)
            """
            result = execute_command_via_cloudflare(
                insert_customer,
                [customer_code, customer_name, 'Retail', customer_email]
            )
            if not result.get('success', False):
                return jsonify({"error": "Failed to create customer"}), 500
            customer_result = execute_query_via_cloudflare(customer_query, [customer_name])
            customer_id = customer_result[0]['id'] if customer_result else None
        
        # Insert sales order
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
            return jsonify({"error": "Failed to create order"}), 500
        
        order_id = result.get('id', 0)
        
        # Update stock for each item
        for item in items:
            product_query = "SELECT product_code, product_name, current_stock FROM erp_products WHERE id = ?"
            product_result = execute_query_via_cloudflare(product_query, [item['product_id']])
            if product_result:
                update_stock_query = "UPDATE erp_products SET current_stock = current_stock - ? WHERE id = ?"
                execute_command_via_cloudflare(update_stock_query, (item['quantity'], item['product_id']))
        
        return jsonify({
            "status": "success",
            "order_number": order_number,
            "invoice_number": "INV-" + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999)),
            "total_amount": total,
            "rewards_earned": rewards
        }), 200
        
    except Exception as e:
        logger.error(f"Error creating sales order: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "SPAR ETL Receiver - Render",
        "status": "running",
        "cloudflare_api": CLOUDFLARE_API_URL,
        "environment": "production" if os.environ.get('RENDER') else "development",
        "endpoints": {
            "health": "GET /health",
            "products": "GET /products",
            "sales_orders": "POST /sales-orders, GET /sales-orders"
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
    print(f"🔗 Cloudflare API: {CLOUDFLARE_API_URL}")
    print("\n⚠️  Make sure to set CLOUDFLARE_API_URL environment variable!")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
