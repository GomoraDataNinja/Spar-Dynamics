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
CLOUDFLARE_API_URL = os.environ.get('CLOUDFLARE_API_URL', 'https://distinguished-geography-mlb-hebrew.trycloudflare.com')

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

@app.route('/products/add', methods=['POST'])
def add_product():
    """
    Add a new product to the database
    """
    try:
        data = request.json
        logger.info(f"Adding product: {data.get('product_name')}")
        
        # Get category ID from category name
        category_query = "SELECT id FROM erp_product_categories WHERE category_name = ?"
        category_result = execute_query_via_cloudflare(category_query, [data.get('category_name')])
        
        if not category_result:
            return jsonify({"error": f"Category '{data.get('category_name')}' not found"}), 400
        
        category_id = category_result[0]['id']
        
        # Check if product code already exists
        check_query = "SELECT id FROM erp_products WHERE product_code = ?"
        check_result = execute_query_via_cloudflare(check_query, [data['product_code']])
        
        if check_result:
            return jsonify({"error": f"Product code '{data['product_code']}' already exists"}), 400
        
        # Insert new product
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
        
        # Get or create customer
        customer_query = "SELECT id FROM erp_customers WHERE customer_name = ?"
        customer_result = execute_query_via_cloudflare(customer_query, [data['customer_name']])
        
        if customer_result:
            customer_id = customer_result[0]['id']
        else:
            # Create customer
            insert_customer = """
                INSERT INTO erp_customers (customer_code, customer_name, customer_type, email)
                VALUES (?, ?, ?, ?)
            """
            customer_code = 'CUST-' + datetime.now().strftime('%Y%m%d%H%M%S')
            execute_command_via_cloudflare(
                insert_customer,
                [customer_code, data['customer_name'], 'Retail', data.get('customer_email', '')]
            )
            # Get the new customer ID
            customer_result = execute_query_via_cloudflare(customer_query, [data['customer_name']])
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
        
        for i, item in enumerate(items):
            product_query = """
                SELECT product_code, product_name, current_stock
                FROM erp_products 
                WHERE id = ?
            """
            product_result = execute_query_via_cloudflare(product_query, [item['product_id']])
            
            if not product_result:
                continue
            
            product = product_result[0]
            
            line_query = """
                INSERT INTO erp_sales_order_lines (
                    so_id, line_number, product_id, product_code, product_name,
                    quantity, unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            line_params = (
                order_id, i + 1, item['product_id'], product.get('product_code', ''),
                product.get('product_name', ''),
                item['quantity'], item['unit_price'],
                item['quantity'] * item['unit_price']
            )
            execute_command_via_cloudflare(line_query, line_params)
            
            update_stock_query = """
                UPDATE erp_products SET current_stock = current_stock - ? WHERE id = ?
            """
            execute_command_via_cloudflare(update_stock_query, (item['quantity'], item['product_id']))
        
        invoice_number = 'INV-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        invoice_query = """
            INSERT INTO erp_sales_invoices (
                invoice_number, customer_id, invoice_date, due_date,
                subtotal, tax_amount, total_amount,
                created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        invoice_params = (
            invoice_number, customer_id,
            datetime.now().strftime('%Y-%m-%d'),
            (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            subtotal, tax, total,
            data.get('recorded_by', 'system')
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

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    try:
        data = request.json
        po_number = 'PO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        
        # Get or create supplier
        supplier_query = "SELECT id FROM erp_suppliers WHERE supplier_name = ?"
        supplier_result = execute_query_via_cloudflare(supplier_query, [data['supplier_name']])
        
        if supplier_result:
            supplier_id = supplier_result[0]['id']
        else:
            insert_supplier = """
                INSERT INTO erp_suppliers (supplier_code, supplier_name, email)
                VALUES (?, ?, ?)
            """
            supplier_code = 'SUP-' + datetime.now().strftime('%Y%m%d%H%M%S')
            execute_command_via_cloudflare(
                insert_supplier,
                [supplier_code, data['supplier_name'], data.get('supplier_email', '')]
            )
            supplier_result = execute_query_via_cloudflare(supplier_query, [data['supplier_name']])
            supplier_id = supplier_result[0]['id'] if supplier_result else None
        
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
        
        po_id = result.get('id', 0)
        
        for i, item in enumerate(items):
            line_query = """
                INSERT INTO erp_purchase_order_lines (
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
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting purchase orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    try:
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
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Error getting recent sales: {e}")
        return jsonify([]), 200

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        logger.info(f"Received sale from: {data.get('customer_name')}")
        
        # Get or create customer
        customer_query = "SELECT id FROM erp_customers WHERE customer_name = ?"
        customer_result = execute_query_via_cloudflare(customer_query, [data.get('customer_name', 'Webhook Customer')])
        
        if customer_result:
            customer_id = customer_result[0]['id']
        else:
            insert_customer = """
                INSERT INTO erp_customers (customer_code, customer_name, customer_type)
                VALUES (?, ?, ?)
            """
            customer_code = 'WEB-' + datetime.now().strftime('%Y%m%d%H%M%S')
            execute_command_via_cloudflare(
                insert_customer,
                [customer_code, data.get('customer_name', 'Webhook Customer'), 'Retail']
            )
            customer_result = execute_query_via_cloudflare(customer_query, [data.get('customer_name', 'Webhook Customer')])
            customer_id = customer_result[0]['id'] if customer_result else None
        
        insert_query = """
            INSERT INTO erp_sales_orders (
                so_number, customer_id, order_date, order_time,
                total_amount, rewards_earned, status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get('sale_id', 'WEB-' + datetime.now().strftime('%Y%m%d%H%M%S')),
            customer_id,
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
                so.so_number as sale_id,
                c.customer_name,
                so.order_date as sale_date,
                so.order_time as sale_time,
                so.total_amount as total_sales,
                so.rewards_earned,
                so.status,
                so.created_by as recorded_by
            FROM erp_sales_orders so
            LEFT JOIN erp_customers c ON so.customer_id = c.id
            WHERE so.created_by = ?
            AND so.order_date = CAST(GETDATE() AS DATE)
            ORDER BY so.created_at DESC
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
            FROM erp_sales_orders
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

@app.route('/goods-receipt', methods=['POST'])
def receive_goods():
    try:
        data = request.json
        receipt_number = 'GRN-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        # Get PO details
        po_query = "SELECT id, supplier_id FROM erp_purchase_orders WHERE po_number = ?"
        po_result = execute_query_via_cloudflare(po_query, [data['po_number']])
        
        if not po_result:
            return jsonify({"error": "Purchase order not found"}), 404
        
        po = po_result[0]
        items = data.get('items', [])
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
            total_quantity, total_cost, 'Draft', data.get('created_by', 'system')
        )
        result = execute_command_via_cloudflare(receipt_query, receipt_params)
        
        if not result.get('success', False):
            return jsonify({"error": "Failed to create goods receipt"}), 500
        
        receipt_id = result.get('id', 0)
        
        for i, item in enumerate(items):
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
            
            # Update stock
            update_stock_query = """
                UPDATE erp_products SET current_stock = current_stock + ? WHERE id = ?
            """
            execute_command_via_cloudflare(update_stock_query, (item['quantity'], item['product_id']))
        
        # Update PO status
        update_po_query = """
            UPDATE erp_purchase_orders 
            SET status = 'Partially Received'
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
        logger.error(f"Error receiving goods: {e}")
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
            "products/add": "POST /products/add",
            "sales_orders": "POST /sales-orders, GET /sales-orders",
            "purchase_orders": "POST /purchase-orders, GET /purchase-orders",
            "goods-receipt": "POST /goods-receipt",
            "recent": "GET /recent",
            "webhook": "POST /webhook",
            "my-sales": "GET /my-sales?recorded_by=username",
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