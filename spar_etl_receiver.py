"""
SPAR ETL Receiver - Render Version
Complete API with Products, Sales, Purchase Orders, and Goods Receiving
"""
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import logging
import os
import random
import json
import requests
import traceback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================
# CONFIGURATION
# ============================================

CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL', '')
logger.info(f"🔗 Cloudflare API URL: {CLOUDFLARE_API_URL or 'NOT SET'}")

# ============================================
# CLOUDFLARE PROXY FUNCTIONS
# ============================================

def execute_query_via_cloudflare(query, params=None):
    """Execute a SELECT query via Cloudflare tunnel"""
    if not CLOUDFLARE_API_URL:
        logger.warning("⚠️ CLOUDFLARE_API_URL not configured")
        return []
    
    try:
        logger.info(f"📊 Forwarding query to Cloudflare: {query[:50]}...")
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-query",
            json={"query": query, "params": params or []},
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Query returned {len(result) if isinstance(result, list) else '?'} rows")
            return result
        else:
            logger.error(f"❌ Cloudflare query error: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        logger.error(f"❌ Cloudflare query exception: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    """Execute an INSERT/UPDATE/DELETE command via Cloudflare"""
    if not CLOUDFLARE_API_URL:
        logger.warning("⚠️ CLOUDFLARE_API_URL not configured")
        return {"success": False, "error": "CLOUDFLARE_API_URL not configured"}
    
    try:
        logger.info(f"📝 Forwarding command to Cloudflare: {query[:50]}...")
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-command",
            json={"query": query, "params": params or []},
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Command executed: {result}")
            return result
        else:
            logger.error(f"❌ Cloudflare command error: {response.status_code} - {response.text}")
            return {"success": False, "error": f"Status {response.status_code}"}
    except Exception as e:
        logger.error(f"❌ Cloudflare command exception: {e}")
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
                cloudflare_status = "error"
        except:
            cloudflare_status = "disconnected"
    else:
        cloudflare_status = "not_configured"
    
    return jsonify({
        "status": "healthy",
        "service": "SPAR ETL Receiver - Render",
        "timestamp": datetime.now().isoformat(),
        "cloudflare_configured": bool(CLOUDFLARE_API_URL),
        "cloudflare_status": cloudflare_status,
        "cloudflare_url": CLOUDFLARE_API_URL
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
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting products: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================
# PRODUCTS ADD ENDPOINT - POST
# ============================================

@app.route('/products/add', methods=['POST'])
def add_product():
    """Add a new product to the database"""
    try:
        data = request.json
        logger.info(f"📦 Adding product: {data.get('product_name')}")
        
        if not data.get('product_code'):
            return jsonify({"error": "Product code is required"}), 400
        if not data.get('product_name'):
            return jsonify({"error": "Product name is required"}), 400
        if not data.get('category_name'):
            return jsonify({"error": "Category is required"}), 400
        
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        # Get or create category
        category_query = "SELECT id FROM erp_product_categories WHERE category_name = ?"
        category_result = execute_query_via_cloudflare(category_query, [data['category_name']])
        
        if not category_result:
            insert_category = """
                INSERT INTO erp_product_categories (category_code, category_name, is_active)
                VALUES (?, ?, 1)
            """
            category_code = data['category_name'].upper().replace(' ', '_')[:20]
            execute_command_via_cloudflare(insert_category, [category_code, data['category_name']])
            category_result = execute_query_via_cloudflare(category_query, [data['category_name']])
            if not category_result:
                return jsonify({"error": f"Category '{data['category_name']}' not found"}), 400
        
        category_id = category_result[0]['id']
        
        # Check if product exists
        check_query = "SELECT id FROM erp_products WHERE product_code = ?"
        check_result = execute_query_via_cloudflare(check_query, [data['product_code']])
        
        if check_result:
            return jsonify({"error": f"Product code '{data['product_code']}' already exists"}), 400
        
        # Insert product
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
            1,
            data.get('created_by', 'system')
        )
        
        result = execute_command_via_cloudflare(insert_query, params)
        
        if result.get('success', False):
            return jsonify({
                "status": "success",
                "message": "Product added successfully",
                "id": result.get('id')
            }), 200
        else:
            return jsonify({"error": "Failed to add product"}), 500
            
    except Exception as e:
        logger.error(f"❌ Error adding product: {e}")
        traceback.print_exc()
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
        logger.error(f"❌ Error getting sales orders: {e}")
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
        
        order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        rewards = total * 0.02
        
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        customer_name = data['customer_name'].strip()
        customer_email = data.get('customer_email', '').strip()
        
        # Get or create customer
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
        
        # Insert order
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
        
        # Insert order lines and update stock
        for i, item in enumerate(items):
            # Get product details
            product_query = "SELECT product_code, product_name FROM erp_products WHERE id = ?"
            product_result = execute_query_via_cloudflare(product_query, [item['product_id']])
            product_code = product_result[0]['product_code'] if product_result else ''
            product_name = product_result[0]['product_name'] if product_result else ''
            
            line_query = """
                INSERT INTO erp_sales_order_lines (
                    so_id, line_number, product_id, product_code, product_name,
                    quantity, unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            line_params = (
                order_id, i + 1, item['product_id'], product_code, product_name,
                item['quantity'], item['unit_price'],
                item['quantity'] * item['unit_price']
            )
            execute_command_via_cloudflare(line_query, line_params)
            
            # Update stock
            update_stock_query = "UPDATE erp_products SET current_stock = current_stock - ? WHERE id = ?"
            execute_command_via_cloudflare(update_stock_query, (item['quantity'], item['product_id']))
        
        invoice_number = 'INV-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        return jsonify({
            "status": "success",
            "order_number": order_number,
            "invoice_number": invoice_number,
            "total_amount": total,
            "rewards_earned": rewards
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error creating sales order: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

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
# PURCHASE ORDERS ENDPOINT - POST
# ============================================

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    """Create a new purchase order"""
    try:
        data = request.json
        logger.info(f"📦 Creating purchase order for: {data.get('supplier_name')}")
        
        po_number = 'PO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        supplier_name = data['supplier_name'].strip()
        supplier_email = data.get('supplier_email', '').strip()
        
        # Get or create supplier
        supplier_query = "SELECT id FROM erp_suppliers WHERE supplier_name = ?"
        supplier_result = execute_query_via_cloudflare(supplier_query, [supplier_name])
        
        if supplier_result:
            supplier_id = supplier_result[0]['id']
        else:
            supplier_code = 'SUP-' + datetime.now().strftime('%Y%m%d%H%M%S')
            insert_supplier = """
                INSERT INTO erp_suppliers (supplier_code, supplier_name, email, is_active)
                VALUES (?, ?, ?, 1)
            """
            result = execute_command_via_cloudflare(
                insert_supplier,
                [supplier_code, supplier_name, supplier_email]
            )
            if not result.get('success', False):
                return jsonify({"error": "Failed to create supplier"}), 500
            supplier_result = execute_query_via_cloudflare(supplier_query, [supplier_name])
            supplier_id = supplier_result[0]['id'] if supplier_result else None
        
        # Insert PO
        insert_po_query = """
            INSERT INTO erp_purchase_orders (
                po_number, supplier_id, order_date,
                expected_delivery_date, subtotal, tax_amount, total_amount,
                status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        po_params = (
            po_number, supplier_id,
            datetime.now().strftime('%Y-%m-%d'),
            data.get('expected_delivery_date'),
            subtotal, tax, total,
            'Draft', data.get('created_by', 'system')
        )
        result = execute_command_via_cloudflare(insert_po_query, po_params)
        if not result.get('success', False):
            return jsonify({"error": "Failed to create PO"}), 500
        
        # Get PO ID
        get_po_id_query = "SELECT id FROM erp_purchase_orders WHERE po_number = ?"
        po_result = execute_query_via_cloudflare(get_po_id_query, [po_number])
        po_id = po_result[0]['id'] if po_result else None
        
        # Insert order lines
        for i, item in enumerate(items):
            # Get product details if not provided
            if not item.get('product_code') or not item.get('product_name'):
                product_query = "SELECT product_code, product_name FROM erp_products WHERE id = ?"
                product_result = execute_query_via_cloudflare(product_query, [item.get('product_id')])
                if product_result:
                    item['product_code'] = product_result[0].get('product_code', '')
                    item['product_name'] = product_result[0].get('product_name', '')
            
            line_query = """
                INSERT INTO erp_purchase_order_lines (
                    po_id, line_number, product_id, product_code, product_name,
                    quantity, unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            line_params = (
                po_id, i + 1, item.get('product_id'),
                str(item.get('product_code', '')),
                str(item.get('product_name', '')),
                float(item.get('quantity', 0)),
                float(item.get('unit_price', 0)),
                float(item.get('quantity', 0)) * float(item.get('unit_price', 0))
            )
            execute_command_via_cloudflare(line_query, line_params)
        
        return jsonify({
            "status": "success",
            "po_number": po_number,
            "total_amount": total,
            "po_id": po_id
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error creating purchase order: {e}")
        traceback.print_exc()
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
        
        receipt_number = 'GRN-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        # Get PO details
        po_query = "SELECT id, supplier_id FROM erp_purchase_orders WHERE po_number = ?"
        po_result = execute_query_via_cloudflare(po_query, [data['po_number']])
        
        if not po_result:
            return jsonify({"error": "Purchase order not found"}), 404
        
        po = po_result[0]
        items = data.get('items', [])
        total_quantity = sum(float(item['quantity']) for item in items)
        total_cost = sum(float(item['quantity']) * float(item['unit_cost']) for item in items)
        
        # Create goods receipt
        receipt_query = """
            INSERT INTO erp_goods_receipts (
                receipt_number, po_id, supplier_id, receipt_date,
                total_quantity, total_cost, status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        receipt_params = (
            receipt_number, po['id'], po['supplier_id'],
            datetime.now().strftime('%Y-%m-%d'),
            total_quantity, total_cost, 'Completed', data.get('created_by', 'system')
        )
        result = execute_command_via_cloudflare(receipt_query, receipt_params)
        if not result.get('success', False):
            return jsonify({"error": "Failed to create goods receipt"}), 500
        
        receipt_id = result.get('id', 0)
        
        # Process each item - UPDATE STOCK
        for i, item in enumerate(items):
            # Insert receipt line
            line_query = """
                INSERT INTO erp_goods_receipt_lines (
                    receipt_id, line_number, product_id, product_code, product_name,
                    quantity, unit_cost, total_cost
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            line_params = (
                receipt_id, i + 1, item['product_id'],
                str(item.get('product_code', '')),
                str(item.get('product_name', '')),
                float(item['quantity']),
                float(item['unit_cost']),
                float(item['quantity']) * float(item['unit_cost'])
            )
            execute_command_via_cloudflare(line_query, line_params)
            
            # Update stock - ADD to current_stock
            update_stock_query = """
                UPDATE erp_products 
                SET current_stock = ISNULL(current_stock, 0) + ? 
                WHERE id = ?
            """
            execute_command_via_cloudflare(update_stock_query, (
                float(item['quantity']), item['product_id']
            ))
            logger.info(f"📦 Stock updated for product {item['product_id']}: +{float(item['quantity'])}")
        
        # Update PO status
        update_po_query = """
            UPDATE erp_purchase_orders 
            SET status = 'Received'
            WHERE id = ?
        """
        execute_command_via_cloudflare(update_po_query, [po['id']])
        
        return jsonify({
            "status": "success",
            "receipt_number": receipt_number,
            "total_quantity": total_quantity,
            "total_cost": total_cost
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Error receiving goods: {e}")
        traceback.print_exc()
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
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting recent sales: {e}")
        return jsonify([]), 200

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
            "products/add": "POST /products/add",
            "sales_orders": "GET /sales-orders, POST /sales-orders",
            "purchase_orders": "GET /purchase-orders, POST /purchase-orders",
            "goods_receipt": "POST /goods-receipt",
            "recent": "GET /recent"
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
    print("   POST /products/add")
    print("   GET  /sales-orders")
    print("   POST /sales-orders")
    print("   GET  /purchase-orders")
    print("   POST /purchase-orders")
    print("   POST /goods-receipt")
    print("   GET  /recent")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
