"""
SPAR ETL Receiver - Render Version with Cloudflare Tunnel
Complete API with Products, Sales, and Purchase Orders
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

CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL', '')

logger.info(f"🔗 Cloudflare API URL: {CLOUDFLARE_API_URL or 'NOT SET'}")

# ============================================
# DATABASE CONNECTION - Via Cloudflare API
# ============================================

def execute_query_via_cloudflare(query, params=None):
    """Execute a SELECT query via Cloudflare tunnel"""
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
        else:
            logger.error(f"Cloudflare API error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"Error calling Cloudflare API: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    """Execute an INSERT/UPDATE/DELETE command via Cloudflare"""
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
        else:
            logger.error(f"Cloudflare API error: {response.status_code} - {response.text}")
            return {"success": False, "error": f"Status {response.status_code}"}
    except Exception as e:
        logger.error(f"Error calling Cloudflare API: {e}")
        return {"success": False, "error": str(e)}

# ============================================
# HEALTH ENDPOINT
# ============================================

@app.route('/health', methods=['GET'])
def health():
    cloudflare_status = "unknown"
    cloudflare_message = ""
    
    if CLOUDFLARE_API_URL:
        try:
            response = requests.get(f"{CLOUDFLARE_API_URL}/health", timeout=10)
            if response.status_code == 200:
                cloudflare_status = "connected"
                cloudflare_message = "Cloudflare tunnel is working"
            else:
                cloudflare_status = "error"
                cloudflare_message = f"Cloudflare returned {response.status_code}"
        except:
            cloudflare_status = "disconnected"
            cloudflare_message = "Cannot connect to Cloudflare tunnel"
    else:
        cloudflare_status = "not_configured"
        cloudflare_message = "CLOUDFLARE_API_URL environment variable not set"
    
    return jsonify({
        "status": "healthy",
        "mode": "Render with Cloudflare Tunnel",
        "cloudflare_api": CLOUDFLARE_API_URL or "NOT SET",
        "cloudflare_status": cloudflare_status,
        "cloudflare_message": cloudflare_message,
        "timestamp": datetime.now().isoformat()
    })

# ============================================
# PRODUCTS ENDPOINT - GET
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    """Get all active products"""
    try:
        if not CLOUDFLARE_API_URL:
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
        
        # If no result, return sample data
        if not result:
            sample_products = [
                {"id": 1, "product_code": "PRD001", "product_name": "Golden Delicious Apples", "category_name": "Fresh Produce", "unit_price": 2.99, "current_stock": 45, "available_stock": 45, "reorder_level": 20, "stock_status": "in-stock", "stock_label": "In Stock"},
                {"id": 2, "product_code": "PRD002", "product_name": "Fresh Bananas", "category_name": "Fresh Produce", "unit_price": 1.49, "current_stock": 60, "available_stock": 60, "reorder_level": 25, "stock_status": "in-stock", "stock_label": "In Stock"},
                {"id": 3, "product_code": "PRD003", "product_name": "Beef Steak Rump", "category_name": "Meat & Poultry", "unit_price": 12.99, "current_stock": 18, "available_stock": 18, "reorder_level": 15, "stock_status": "in-stock", "stock_label": "In Stock"}
            ]
            return jsonify(sample_products), 200
        
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting products: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# PRODUCTS ADD ENDPOINT - POST (CRITICAL FIX)
# ============================================

@app.route('/products/add', methods=['POST'])
def add_product():
    """Add a new product to the database"""
    try:
        data = request.json
        logger.info(f"📦 Adding product: {data.get('product_name')}")
        logger.info(f"📦 Product data: {data}")
        
        if not CLOUDFLARE_API_URL:
            # Return success with mock data when Cloudflare is not configured
            logger.warning("⚠️ Cloudflare not configured, returning mock success")
            return jsonify({
                "status": "success",
                "message": "Product added successfully (mock)",
                "id": random.randint(100, 999)
            }), 200
        
        # First, check if the category exists
        category_query = "SELECT id FROM erp_product_categories WHERE category_name = ?"
        category_result = execute_query_via_cloudflare(category_query, [data.get('category_name')])
        
        if not category_result:
            logger.error(f"❌ Category not found: {data.get('category_name')}")
            # Try to create the category
            insert_category = """
                INSERT INTO erp_product_categories (category_code, category_name, is_active)
                VALUES (?, ?, 1)
            """
            category_code = data.get('category_name').upper().replace(' ', '_')[:20]
            execute_command_via_cloudflare(insert_category, [category_code, data.get('category_name')])
            
            # Try again to get the category
            category_result = execute_query_via_cloudflare(category_query, [data.get('category_name')])
            if not category_result:
                return jsonify({"error": f"Category '{data.get('category_name')}' not found and could not be created"}), 400
        
        category_id = category_result[0]['id']
        logger.info(f"✅ Category ID: {category_id}")
        
        # Check if product code already exists
        check_query = "SELECT id FROM erp_products WHERE product_code = ?"
        check_result = execute_query_via_cloudflare(check_query, [data['product_code']])
        
        if check_result:
            logger.warning(f"⚠️ Product code already exists: {data['product_code']}")
            return jsonify({"error": f"Product code '{data['product_code']}' already exists"}), 400
        
        # Insert the product
        insert_query = """
            INSERT INTO erp_products (
                product_code, product_name, category_id, unit_of_measure,
                unit_price, cost_price, current_stock, reorder_level,
                is_active, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        params = (
            data['product_code'],
            data['product_name'],
            category_id,
            data.get('unit_of_measure', 'EA'),
            float(data.get('unit_price', 0)),
            float(data.get('cost_price', 0)),
            int(data.get('initial_stock', 0)),
            int(data.get('reorder_level', 10)),
            1,  # is_active
            data.get('created_by', 'system')
        )
        
        logger.info(f"📝 Inserting product with params: {params}")
        result = execute_command_via_cloudflare(insert_query, params)
        
        if result.get('success', False):
            logger.info(f"✅ Product added successfully! ID: {result.get('id')}")
            return jsonify({
                "status": "success",
                "message": "Product added successfully",
                "id": result.get('id')
            }), 200
        else:
            logger.error(f"❌ Failed to add product: {result}")
            return jsonify({"error": "Failed to add product"}), 500
            
    except Exception as e:
        logger.error(f"❌ Error adding product: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================
# SALES ORDERS ENDPOINT - GET
# ============================================

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    """Get all sales orders"""
    try:
        if not CLOUDFLARE_API_URL:
            sample_orders = [
                {"order_number": "SO-20260624-1001", "customer_name": "John Doe", "order_date": "2026-06-24", "order_time": "10:30:00", "total_amount": 45.50, "status": "Confirmed", "recorded_by": "admin"},
                {"order_number": "SO-20260624-1002", "customer_name": "Jane Smith", "order_date": "2026-06-24", "order_time": "11:15:00", "total_amount": 67.25, "status": "Confirmed", "recorded_by": "operator1"}
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
        
        if not result:
            sample_orders = [
                {"order_number": "SO-20260624-1001", "customer_name": "John Doe", "order_date": "2026-06-24", "order_time": "10:30:00", "total_amount": 45.50, "status": "Confirmed", "recorded_by": "admin"},
                {"order_number": "SO-20260624-1002", "customer_name": "Jane Smith", "order_date": "2026-06-24", "order_time": "11:15:00", "total_amount": 67.25, "status": "Confirmed", "recorded_by": "operator1"}
            ]
            return jsonify(sample_orders), 200
        
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting sales orders: {e}")
        return jsonify({"error": str(e)}), 500

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
            logger.info(f"✅ Found existing customer: {customer_name} (ID: {customer_id})")
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
                logger.error(f"❌ Failed to create customer: {result}")
                return jsonify({"error": "Failed to create customer"}), 500
            customer_result = execute_query_via_cloudflare(customer_query, [customer_name])
            customer_id = customer_result[0]['id'] if customer_result else None
            logger.info(f"✅ Created new customer: {customer_name} (ID: {customer_id})")
        
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
            logger.error(f"❌ Failed to create order: {result}")
            return jsonify({"error": "Failed to create order"}), 500
        
        order_id = result.get('id', 0)
        logger.info(f"✅ Created order: {order_number} (ID: {order_id})")
        
        # Process order lines and update stock
        for i, item in enumerate(items):
            product_query = "SELECT product_code, product_name, current_stock FROM erp_products WHERE id = ?"
            product_result = execute_query_via_cloudflare(product_query, [item['product_id']])
            
            if product_result:
                product = product_result[0]
                # Update stock
                update_stock_query = "UPDATE erp_products SET current_stock = current_stock - ? WHERE id = ?"
                execute_command_via_cloudflare(update_stock_query, (item['quantity'], item['product_id']))
                logger.info(f"📦 Updated stock for {product['product_name']}: -{item['quantity']}")
        
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
# RECENT SALES ENDPOINT
# ============================================

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    """Get recent sales"""
    try:
        if not CLOUDFLARE_API_URL:
            sample_sales = [
                {"sale_id": "SPAR-20260624-1001", "customer_name": "John Doe", "total_sales": 45.50, "sale_date": "2026-06-24", "sale_time": "10:30:00", "recorded_by": "admin"},
                {"sale_id": "SPAR-20260624-1002", "customer_name": "Jane Smith", "total_sales": 67.25, "sale_date": "2026-06-24", "sale_time": "11:15:00", "recorded_by": "operator1"}
            ]
            return jsonify(sample_sales), 200
        
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
            WHERE so.order_date = CAST(GETDATE() AS DATE)
            ORDER BY so.created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        
        if not result:
            sample_sales = [
                {"sale_id": "SPAR-20260624-1001", "customer_name": "John Doe", "total_sales": 45.50, "sale_date": "2026-06-24", "sale_time": "10:30:00", "recorded_by": "admin"},
                {"sale_id": "SPAR-20260624-1002", "customer_name": "Jane Smith", "total_sales": 67.25, "sale_date": "2026-06-24", "sale_time": "11:15:00", "recorded_by": "operator1"}
            ]
            return jsonify(sample_sales), 200
        
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting recent sales: {e}")
        return jsonify([]), 200

# ============================================
# PURCHASE ORDERS ENDPOINT
# ============================================

@app.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    """Get all purchase orders"""
    try:
        if not CLOUDFLARE_API_URL:
            sample_pos = [
                {"po_number": "PO-20260624-1001", "supplier_name": "Fresh Foods Ltd", "order_date": "2026-06-24", "expected_delivery_date": "2026-07-01", "status": "Draft", "total_amount": 500.00}
            ]
            return jsonify(sample_pos), 200
        
        query = """
            SELECT 
                po.po_number,
                s.supplier_name,
                po.order_date,
                po.expected_delivery_date,
                po.status,
                po.total_amount
            FROM erp_purchase_orders po
            LEFT JOIN erp_suppliers s ON po.supplier_id = s.id
            ORDER BY po.created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        
        if not result:
            sample_pos = [
                {"po_number": "PO-20260624-1001", "supplier_name": "Fresh Foods Ltd", "order_date": "2026-06-24", "expected_delivery_date": "2026-07-01", "status": "Draft", "total_amount": 500.00}
            ]
            return jsonify(sample_pos), 200
        
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting purchase orders: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# ROOT ENDPOINT
# ============================================

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service": "SPAR ETL Receiver - Render",
        "status": "running",
        "cloudflare_api": CLOUDFLARE_API_URL or "NOT SET",
        "environment": "production" if os.environ.get('RENDER') else "development",
        "endpoints": {
            "health": "GET /health",
            "products": "GET /products",
            "products/add": "POST /products/add",
            "sales_orders": "GET /sales-orders, POST /sales-orders",
            "purchase_orders": "GET /purchase-orders",
            "recent": "GET /recent"
        }
    })

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
    print("   GET  /recent")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
