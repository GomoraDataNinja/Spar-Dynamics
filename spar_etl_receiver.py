"""
SPAR ETL Receiver - Render Version
Complete API with Products, Sales, Purchase Orders, and Goods Receiving
Connects to local SQL Server via Cloudflare tunnel
"""

from flask import Flask, request, jsonify
from datetime import datetime
import logging
import os
import random
import requests
import traceback
import time

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
        
        order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        rewards = total * 0.02
        
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
                status, approval_status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        order_params = (
            order_number, customer_id,
            datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M:%S'),
            subtotal, tax, total, rewards,
            'Confirmed', 'Approved', data.get('recorded_by', 'system')
        )
        result = execute_command_via_cloudflare(insert_order_query, order_params)
        if not result.get('success', False):
            return jsonify({"error": "Failed to create order"}), 500
        
        order_id = result.get('id', 0)
        
        # Insert order lines and update stock
        for i, item in enumerate(items):
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
        
        po_number = 'PO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        
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
                status, approval_status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        po_params = (
            po_number, supplier_id,
            datetime.now().strftime('%Y-%m-%d'),
            data.get('expected_delivery_date'),
            subtotal, tax, total,
            'Draft', 'Pending', data.get('created_by', 'system')
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
        
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        receipt_number = 'GRN-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
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
            SET status = 'Received', approval_status = 'Approved'
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
# NEW: BANK ACCOUNTS PROXY - GET
# ============================================

@app.route('/bank-accounts', methods=['GET'])
def get_bank_accounts_proxy():
    """Proxy to get bank accounts"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        result = execute_query_via_cloudflare(
            "SELECT id, account_name, account_number, bank_name, balance, currency, is_active FROM erp_bank_accounts WHERE is_active = 1 ORDER BY account_name"
        )
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting bank accounts: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: BANK BALANCE PROXY - GET
# ============================================

@app.route('/bank-balance', methods=['GET'])
def get_bank_balance_proxy():
    """Proxy to get total bank balance"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        result = execute_query_via_cloudflare(
            "SELECT ISNULL(SUM(balance), 0) as total_balance FROM erp_bank_accounts WHERE is_active = 1"
        )
        total = result[0]['total_balance'] if result and len(result) > 0 else 0
        return jsonify({"total_balance": total}), 200
    except Exception as e:
        logger.error(f"❌ Error getting bank balance: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: DOCUMENTS PROXY - GET
# ============================================

@app.route('/documents', methods=['GET'])
def get_documents_proxy():
    """Proxy to get documents"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        query = """
            SELECT 
                id,
                document_name,
                document_type,
                status,
                uploaded_by,
                uploaded_at,
                reference_id,
                reference_type
            FROM erp_documents
            WHERE is_active = 1
            ORDER BY uploaded_at DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting documents: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: INCOMING DOCUMENTS PROXY - GET
# ============================================

@app.route('/incoming-documents', methods=['GET'])
def get_incoming_documents_proxy():
    """Proxy to get incoming documents count"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        result = execute_query_via_cloudflare(
            "SELECT COUNT(*) as count FROM erp_documents WHERE status = 'Pending' AND is_active = 1"
        )
        count = result[0]['count'] if result and len(result) > 0 else 0
        return jsonify({"count": count}), 200
    except Exception as e:
        logger.error(f"❌ Error getting incoming documents: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: PAYMENTS PROXY - GET
# ============================================

@app.route('/payments', methods=['GET'])
def get_payments_proxy():
    """Proxy to get payments"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        query = """
            SELECT 
                id,
                payment_number,
                payment_date,
                amount,
                payment_method,
                status,
                reference,
                created_by,
                created_at
            FROM erp_payments
            ORDER BY created_at DESC
        """
        result = execute_query_via_cloudflare(query)
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting payments: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: UNPROCESSED PAYMENTS PROXY - GET
# ============================================

@app.route('/unprocessed-payments', methods=['GET'])
def get_unprocessed_payments_proxy():
    """Proxy to get unprocessed payments count"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        result = execute_query_via_cloudflare(
            "SELECT COUNT(*) as count FROM erp_payments WHERE status = 'Pending'"
        )
        count = result[0]['count'] if result and len(result) > 0 else 0
        return jsonify({"count": count}), 200
    except Exception as e:
        logger.error(f"❌ Error getting unprocessed payments: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: OVERDUE POS PROXY - GET
# ============================================

@app.route('/overdue-pos', methods=['GET'])
def get_overdue_pos_proxy():
    """Proxy to get overdue purchase orders count"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        result = execute_query_via_cloudflare(
            "SELECT COUNT(*) as overdue_count FROM erp_purchase_orders WHERE expected_delivery_date < CAST(GETDATE() AS DATE) AND status NOT IN ('Received', 'Cancelled')"
        )
        count = result[0]['overdue_count'] if result and len(result) > 0 else 0
        return jsonify({"overdue_count": count}), 200
    except Exception as e:
        logger.error(f"❌ Error getting overdue POs: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: PENDING APPROVALS PROXY - GET
# ============================================

@app.route('/pending-approvals', methods=['GET'])
def get_pending_approvals_proxy():
    """Proxy to get pending approvals counts"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        result = execute_query_via_cloudflare(
            "SELECT (SELECT COUNT(*) FROM erp_purchase_orders WHERE approval_status = 'Pending') as pending_pos, (SELECT COUNT(*) FROM erp_sales_orders WHERE approval_status = 'Pending') as pending_sos"
        )
        if result and len(result) > 0:
            return jsonify({
                "pending_pos": result[0]['pending_pos'],
                "pending_sos": result[0]['pending_sos']
            }), 200
        return jsonify({"pending_pos": 0, "pending_sos": 0}), 200
    except Exception as e:
        logger.error(f"❌ Error getting pending approvals: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: APPROVE PURCHASE ORDER PROXY - POST
# ============================================

@app.route('/purchase-orders/<po_number>/approve', methods=['POST'])
def approve_purchase_order_proxy(po_number):
    """Proxy to approve a purchase order"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        # First check if PO exists
        check_query = "SELECT id FROM erp_purchase_orders WHERE po_number = ?"
        check_result = execute_query_via_cloudflare(check_query, [po_number])
        if not check_result:
            return jsonify({"error": "PO not found"}), 404
        
        # Approve the PO
        update_query = """
            UPDATE erp_purchase_orders 
            SET approval_status = 'Approved', status = 'Confirmed'
            WHERE po_number = ?
        """
        result = execute_command_via_cloudflare(update_query, [po_number])
        if result.get('success', False):
            return jsonify({"status": "success", "message": f"PO {po_number} approved"}), 200
        else:
            return jsonify({"error": "Failed to approve PO"}), 500
    except Exception as e:
        logger.error(f"❌ Error approving PO: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: REJECT PURCHASE ORDER PROXY - POST
# ============================================

@app.route('/purchase-orders/<po_number>/reject', methods=['POST'])
def reject_purchase_order_proxy(po_number):
    """Proxy to reject a purchase order"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        # First check if PO exists
        check_query = "SELECT id FROM erp_purchase_orders WHERE po_number = ?"
        check_result = execute_query_via_cloudflare(check_query, [po_number])
        if not check_result:
            return jsonify({"error": "PO not found"}), 404
        
        # Reject the PO
        update_query = """
            UPDATE erp_purchase_orders 
            SET approval_status = 'Rejected', status = 'Cancelled'
            WHERE po_number = ?
        """
        result = execute_command_via_cloudflare(update_query, [po_number])
        if result.get('success', False):
            return jsonify({"status": "success", "message": f"PO {po_number} rejected"}), 200
        else:
            return jsonify({"error": "Failed to reject PO"}), 500
    except Exception as e:
        logger.error(f"❌ Error rejecting PO: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# NEW: DELETE EMPTY PURCHASE ORDER PROXY - DELETE
# ============================================

@app.route('/purchase-orders/<po_number>', methods=['DELETE'])
def delete_empty_purchase_order_proxy(po_number):
    """Proxy to delete an empty purchase order"""
    try:
        if not CLOUDFLARE_API_URL:
            return jsonify({"error": "Cloudflare not configured"}), 500
        
        # Forward the DELETE request to local server
        url = f"{CLOUDFLARE_API_URL}/purchase-orders/{po_number}"
        response = requests.delete(url, timeout=30)
        
        if response.status_code == 200:
            return jsonify(response.json()), 200
        else:
            error_msg = response.json() if response.text else {"error": f"Error from local server: {response.status_code}"}
            return jsonify(error_msg), response.status_code
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
            "bank-balance": "GET /bank-balance",
            "documents": "GET /documents",
            "incoming-documents": "GET /incoming-documents",
            "payments": "GET /payments",
            "unprocessed-payments": "GET /unprocessed-payments",
            "overdue-pos": "GET /overdue-pos",
            "pending-approvals": "GET /pending-approvals"
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
    print("   GET  /bank-balance")
    print("   GET  /documents")
    print("   GET  /incoming-documents")
    print("   GET  /payments")
    print("   GET  /unprocessed-payments")
    print("   GET  /overdue-pos")
    print("   GET  /pending-approvals")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
