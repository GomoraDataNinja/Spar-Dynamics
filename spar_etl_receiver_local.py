"""
SPAR ETL Receiver - Render Version with Complete API
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
        "service": "SPAR ETL Receiver",
        "timestamp": datetime.now().isoformat(),
        "cloudflare_configured": bool(CLOUDFLARE_API_URL),
        "cloudflare_status": cloudflare_status
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
                "recent": "GET /recent"
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
# CLOUDFLARE PROXY ENDPOINTS
# ============================================

def execute_query_via_cloudflare(query, params=None):
    """Execute a SELECT query via Cloudflare tunnel"""
    if not CLOUDFLARE_API_URL:
        logger.warning("⚠️ CLOUDFLARE_API_URL not configured")
        return []
    try:
        logger.info(f"📊 Query: {query[:100]}...")
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-query",
            json={"query": query, "params": params or []},
            timeout=60
        )
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Query returned {len(result)} rows")
            return result
        logger.error(f"Cloudflare query error: {response.status_code} - {response.text}")
        return []
    except Exception as e:
        logger.error(f"Cloudflare query exception: {e}")
        return []

def execute_command_via_cloudflare(query, params=None):
    """Execute an INSERT/UPDATE/DELETE command via Cloudflare"""
    if not CLOUDFLARE_API_URL:
        logger.warning("⚠️ CLOUDFLARE_API_URL not configured")
        return {"success": False, "error": "CLOUDFLARE_API_URL not configured"}
    try:
        logger.info(f"📝 Command: {query[:100]}...")
        logger.info(f"📝 Params: {params}")
        response = requests.post(
            f"{CLOUDFLARE_API_URL}/execute-command",
            json={"query": query, "params": params or []},
            timeout=60
        )
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Command executed: {result}")
            return result
        logger.error(f"Cloudflare command error: {response.status_code} - {response.text}")
        return {"success": False, "error": f"Status {response.status_code}"}
    except Exception as e:
        logger.error(f"Cloudflare command exception: {e}")
        return {"success": False, "error": str(e)}

# ============================================
# PRODUCTS ENDPOINT - GET
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    """Get all active products"""
    try:
        sample_products = [
            {"id": 1, "product_code": "PRD001", "product_name": "Golden Delicious Apples", "category_name": "Fresh Produce", "unit_price": 2.99, "current_stock": 45, "available_stock": 45, "reorder_level": 20, "stock_status": "in-stock", "stock_label": "In Stock"},
            {"id": 2, "product_code": "PRD002", "product_name": "Fresh Bananas", "category_name": "Fresh Produce", "unit_price": 1.49, "current_stock": 60, "available_stock": 60, "reorder_level": 25, "stock_status": "in-stock", "stock_label": "In Stock"},
            {"id": 3, "product_code": "PRD003", "product_name": "Beef Steak Rump", "category_name": "Meat & Poultry", "unit_price": 12.99, "current_stock": 18, "available_stock": 18, "reorder_level": 15, "stock_status": "in-stock", "stock_label": "In Stock"}
        ]
        
        if not CLOUDFLARE_API_URL:
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
        return jsonify(result if result else sample_products), 200
    except Exception as e:
        logger.error(f"Error getting products: {e}")
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
            logger.warning("⚠️ Cloudflare not configured, returning mock success")
            return jsonify({
                "status": "success",
                "message": "Product added successfully (mock)",
                "id": random.randint(100, 999)
            }), 200
        
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
        
        check_query = "SELECT id FROM erp_products WHERE product_code = ?"
        check_result = execute_query_via_cloudflare(check_query, [data['product_code']])
        
        if check_result:
            return jsonify({"error": f"Product code '{data['product_code']}' already exists"}), 400
        
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
        logger.error(f"Error adding product: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# SALES ORDERS ENDPOINT - GET
# ============================================

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    """Get all sales orders"""
    try:
        sample_orders = [
            {"order_number": "SO-20260624-1001", "customer_name": "John Doe", "order_date": "2026-06-24", "order_time": "10:30:00", "total_amount": 45.50, "status": "Confirmed", "recorded_by": "admin"},
            {"order_number": "SO-20260624-1002", "customer_name": "Jane Smith", "order_date": "2026-06-24", "order_time": "11:15:00", "total_amount": 67.25, "status": "Confirmed", "recorded_by": "operator1"}
        ]
        
        if not CLOUDFLARE_API_URL:
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
        return jsonify(result if result else sample_orders), 200
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
        
        order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        rewards = total * 0.02
        
        if not CLOUDFLARE_API_URL:
            return jsonify({
                "status": "success",
                "order_number": order_number,
                "invoice_number": "INV-" + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999)),
                "total_amount": total,
                "rewards_earned": rewards
            }), 200
        
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
        
        for item in items:
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

# ============================================
# PURCHASE ORDERS ENDPOINT - GET
# ============================================

@app.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    """Get all purchase orders"""
    try:
        sample_pos = [
            {"po_number": "PO-20260624-1001", "supplier_name": "Fresh Foods Ltd", "order_date": "2026-06-24", "expected_delivery_date": "2026-07-01", "status": "Draft", "total_amount": 500.00, "id": 1},
            {"po_number": "PO-20260624-1002", "supplier_name": "Meat Suppliers Inc", "order_date": "2026-06-24", "expected_delivery_date": "2026-06-30", "status": "Received", "total_amount": 750.00, "id": 2}
        ]
        
        if not CLOUDFLARE_API_URL:
            return jsonify(sample_pos), 200
        
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
        return jsonify(result if result else sample_pos), 200
    except Exception as e:
        logger.error(f"Error getting purchase orders: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# PURCHASE ORDER LINES ENDPOINT - GET
# ============================================

@app.route('/purchase-orders/<po_number>/lines', methods=['GET'])
def get_purchase_order_lines(po_number):
    """Get lines for a specific purchase order"""
    try:
        logger.info(f"📋 Fetching lines for PO: {po_number}")
        
        if not CLOUDFLARE_API_URL:
            sample_lines = [
                {"product_id": 1, "product_code": "PRD001", "product_name": "Golden Delicious Apples", "quantity": 10, "unit_price": 1.50},
                {"product_id": 2, "product_code": "PRD002", "product_name": "Fresh Bananas", "quantity": 20, "unit_price": 0.80}
            ]
            return jsonify(sample_lines), 200
        
        # First, get the PO ID
        po_id_query = "SELECT id FROM erp_purchase_orders WHERE po_number = ?"
        po_result = execute_query_via_cloudflare(po_id_query, [po_number])
        
        if not po_result:
            logger.warning(f"⚠️ PO not found: {po_number}")
            return jsonify([]), 200
        
        po_id = po_result[0]['id']
        logger.info(f"✅ Found PO ID: {po_id}")
        
        # Get lines for this PO
        query = """
            SELECT 
                pol.product_id,
                pol.product_code,
                pol.product_name,
                pol.quantity,
                pol.unit_price,
                pol.line_total,
                pol.expected_date,
                pol.received_quantity,
                pol.remaining_quantity
            FROM erp_purchase_order_lines pol
            WHERE pol.po_id = ?
            ORDER BY pol.line_number
        """
        result = execute_query_via_cloudflare(query, [po_id])
        logger.info(f"✅ Found {len(result)} lines for PO {po_number}")
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"Error getting PO lines: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# ============================================
# PURCHASE ORDERS ENDPOINT - POST (FIXED)
# ============================================

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    """Create a new purchase order with line items"""
    try:
        data = request.json
        logger.info("=" * 70)
        logger.info("📦 CREATING PURCHASE ORDER")
        logger.info(f"📦 Supplier: {data.get('supplier_name')}")
        logger.info(f"📦 Items received: {data.get('items')}")
        
        po_number = 'PO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        
        if not CLOUDFLARE_API_URL:
            logger.warning("⚠️ Cloudflare not configured, returning mock success")
            return jsonify({
                "status": "success",
                "po_number": po_number,
                "total_amount": total
            }), 200
        
        supplier_name = data['supplier_name'].strip()
        supplier_email = data.get('supplier_email', '').strip()
        
        # Get or create supplier
        supplier_query = "SELECT id FROM erp_suppliers WHERE supplier_name = ?"
        supplier_result = execute_query_via_cloudflare(supplier_query, [supplier_name])
        
        if supplier_result:
            supplier_id = supplier_result[0]['id']
            logger.info(f"✅ Found existing supplier: {supplier_name} (ID: {supplier_id})")
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
                logger.error(f"❌ Failed to create supplier: {result}")
                return jsonify({"error": "Failed to create supplier"}), 500
            supplier_result = execute_query_via_cloudflare(supplier_query, [supplier_name])
            supplier_id = supplier_result[0]['id'] if supplier_result else None
            logger.info(f"✅ Created new supplier: {supplier_name} (ID: {supplier_id})")
        
        # Insert purchase order
        insert_po_query = """
            INSERT INTO erp_purchase_orders (
                po_number, supplier_id, order_date,
                expected_delivery_date, subtotal, tax_amount, total_amount,
                status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        po_params = (
            po_number, 
            supplier_id,
            datetime.now().strftime('%Y-%m-%d'),
            data.get('expected_delivery_date'),
            subtotal, 
            tax, 
            total,
            'Draft', 
            data.get('created_by', 'system')
        )
        
        logger.info(f"📝 Inserting PO with params: {po_params}")
        result = execute_command_via_cloudflare(insert_po_query, po_params)
        
        if not result.get('success', False):
            logger.error(f"❌ Failed to create PO: {result}")
            return jsonify({"error": "Failed to create purchase order"}), 500
        
        # Get the PO ID by querying for it
        get_po_id_query = "SELECT id FROM erp_purchase_orders WHERE po_number = ?"
        po_result = execute_query_via_cloudflare(get_po_id_query, [po_number])
        
        if not po_result:
            logger.error(f"❌ Failed to get PO ID for {po_number}")
            return jsonify({"error": "Failed to get PO ID"}), 500
        
        po_id = po_result[0]['id']
        logger.info(f"✅ PO created with ID: {po_id}")
        
        if po_id == 0 or po_id is None:
            logger.error("❌ Failed to get PO ID")
            return jsonify({"error": "Failed to get PO ID"}), 500
        
        # Insert each order line
        lines_inserted = 0
        for i, item in enumerate(items):
            try:
                line_query = """
                    INSERT INTO erp_purchase_order_lines (
                        po_id, line_number, product_id, product_code, product_name,
                        quantity, unit_price, line_total,
                        expected_date, received_quantity, remaining_quantity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                line_params = (
                    po_id,  # CRITICAL: This must be the PO ID from the insert above
                    i + 1, 
                    item.get('product_id'),
                    item.get('product_code', ''),
                    item.get('product_name', ''),
                    item.get('quantity'),
                    item.get('unit_price'),
                    item.get('quantity') * item.get('unit_price'),
                    data.get('expected_delivery_date'),
                    0,  # received_quantity - initially 0
                    item.get('quantity')  # remaining_quantity - initially full quantity
                )
                logger.info(f"📝 Inserting line {i+1}: {item.get('product_name')} x {item.get('quantity')} with po_id={po_id}")
                logger.info(f"📝 Line params: {line_params}")
                line_result = execute_command_via_cloudflare(line_query, line_params)
                logger.info(f"✅ Line {i+1} result: {line_result}")
                if line_result.get('success', False):
                    lines_inserted += 1
                else:
                    logger.error(f"❌ Line {i+1} insert failed: {line_result}")
            except Exception as e:
                logger.error(f"❌ Error inserting line {i+1}: {e}")
                import traceback
                traceback.print_exc()
        
        # Verify lines were inserted
        verify_query = "SELECT COUNT(*) as count FROM erp_purchase_order_lines WHERE po_id = ?"
        verify_result = execute_query_via_cloudflare(verify_query, [po_id])
        line_count = verify_result[0]['count'] if verify_result else 0
        logger.info(f"✅ Verification: {line_count} lines inserted for PO {po_number}")
        
        # Also verify the PO exists
        po_verify = "SELECT id, po_number FROM erp_purchase_orders WHERE id = ?"
        po_verify_result = execute_query_via_cloudflare(po_verify, [po_id])
        logger.info(f"✅ PO verification: {po_verify_result}")
        
        logger.info(f"📦 PO creation completed: {po_number}")
        logger.info("=" * 70)
        
        return jsonify({
            "status": "success",
            "po_number": po_number,
            "total_amount": total,
            "lines_inserted": line_count,
            "po_id": po_id
        }), 200
        
    except Exception as e:
        logger.error(f"Error creating purchase order: {e}")
        import traceback
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
            return jsonify({
                "status": "success",
                "receipt_number": receipt_number,
                "total_quantity": sum(item['quantity'] for item in data.get('items', [])),
                "total_cost": sum(item['quantity'] * item['unit_cost'] for item in data.get('items', []))
            }), 200
        
        # Get PO details
        po_query = "SELECT id, supplier_id FROM erp_purchase_orders WHERE po_number = ?"
        po_result = execute_query_via_cloudflare(po_query, [data['po_number']])
        
        if not po_result:
            return jsonify({"error": "Purchase order not found"}), 404
        
        po = po_result[0]
        items = data.get('items', [])
        
        if not items:
            return jsonify({"error": "No items to receive"}), 400
        
        total_quantity = sum(item['quantity'] for item in items)
        total_cost = sum(item['quantity'] * item['unit_cost'] for item in items)
        
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
                receipt_id, i + 1, item['product_id'], item.get('product_code', ''),
                item.get('product_name', ''), item['quantity'],
                item['unit_cost'], item['quantity'] * item['unit_cost']
            )
            execute_command_via_cloudflare(line_query, line_params)
            
            # Update PO line - mark as received
            update_po_line_query = """
                UPDATE erp_purchase_order_lines 
                SET received_quantity = received_quantity + ?,
                    remaining_quantity = quantity - received_quantity
                WHERE po_id = ? AND product_id = ?
            """
            execute_command_via_cloudflare(update_po_line_query, (
                item['quantity'], po['id'], item['product_id']
            ))
            
            # CRITICAL: Update stock - ADD to current_stock
            update_stock_query = """
                UPDATE erp_products 
                SET current_stock = ISNULL(current_stock, 0) + ? 
                WHERE id = ?
            """
            result_stock = execute_command_via_cloudflare(update_stock_query, (item['quantity'], item['product_id']))
            logger.info(f"📦 Stock updated for product {item['product_id']}: +{item['quantity']}")
        
        # Update PO status to Received
        update_po_query = """
            UPDATE erp_purchase_orders 
            SET status = 'Received'
            WHERE id = ?
        """
        execute_command_via_cloudflare(update_po_query, [po['id']])
        logger.info(f"✅ PO {data['po_number']} marked as Received")
        
        return jsonify({
            "status": "success",
            "receipt_number": receipt_number,
            "total_quantity": total_quantity,
            "total_cost": total_cost
        }), 200
        
    except Exception as e:
        logger.error(f"Error receiving goods: {e}")
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
        sample_sales = [
            {"sale_id": "SPAR-20260624-1001", "customer_name": "John Doe", "total_sales": 45.50, "sale_date": "2026-06-24", "sale_time": "10:30:00", "recorded_by": "admin", "etl_processed": 1},
            {"sale_id": "SPAR-20260624-1002", "customer_name": "Jane Smith", "total_sales": 67.25, "sale_date": "2026-06-24", "sale_time": "11:15:00", "recorded_by": "operator1", "etl_processed": 1}
        ]
        
        if not CLOUDFLARE_API_URL:
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
        return jsonify(result if result else sample_sales), 200
    except Exception as e:
        logger.error(f"Error getting recent sales: {e}")
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
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
