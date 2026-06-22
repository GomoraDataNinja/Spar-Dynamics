"""
SPAR ETL Receiver - Complete API with Sales Orders, Purchase Orders, and Goods Receiving
"""

from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import json
import logging
import sys
import os
import traceback
import random

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('spar_etl_receiver.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================
# CONFIGURATION
# ============================================
RAW_DATA_FOLDER = Path(r"C:\Users\Lenovo\OneDrive\Desktop\HBMI\Data Warehousing\ETL_Projects\raw_data")
RAW_DATA_FOLDER.mkdir(parents=True, exist_ok=True)

stats = {
    'total_received': 0,
    'today_received': 0,
    'start_time': datetime.now(),
    'last_sale': None
}

# Store sales in memory for fast access
sales_memory = []

# ============================================
# SQL SERVER CONNECTION
# ============================================
def get_sql_connection():
    try:
        import pyodbc
        conn = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=(local);"
            "DATABASE=SPAR_ETL;"
            "Trusted_Connection=yes;"
        )
        return conn
    except Exception as e:
        logger.error(f"SQL Server connection error: {e}")
        return None

def execute_query(query, params=None):
    """Execute SELECT query and return DataFrame"""
    conn = get_sql_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        if params:
            return pd.read_sql(query, conn, params=params)
        else:
            return pd.read_sql(query, conn)
    except Exception as e:
        logger.error(f"Query error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def execute_command(query, params=None):
    """Execute INSERT/UPDATE/DELETE"""
    conn = get_sql_connection()
    if conn is None:
        return False, "Database connection failed"
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        conn.commit()
        cursor.close()
        return True, "Success"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

# ============================================
# SAVE FUNCTIONS
# ============================================
def save_to_sql_server(data):
    try:
        conn = get_sql_connection()
        if conn is None:
            return False
        
        cursor = conn.cursor()
        
        query = """
            INSERT INTO etl_sales_raw (
                sale_id, customer_name, customer_email, customer_id,
                phone, product_category, product_name, quantity,
                unit_price, total_sales, rewards_earned, sale_date,
                sale_month, sale_year, sale_time, timestamp_utc,
                recorded_by, etl_processed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        cursor.execute(query, (
            str(data.get('sale_id', '')),
            str(data.get('customer_name', '')),
            str(data.get('customer_email', '')),
            str(data.get('customer_id', '')),
            str(data.get('phone', '')),
            str(data.get('product_category', '')),
            str(data.get('product', '')),
            int(data.get('quantity', 0)),
            float(data.get('unit_price', 0)),
            float(data.get('total_sales', 0)),
            float(data.get('rewards_earned', 0)),
            data.get('sale_date', datetime.now().strftime('%Y-%m-%d')),
            datetime.now().strftime('%b').upper(),
            datetime.now().year,
            data.get('sale_time', datetime.now().strftime('%H:%M:%S')),
            data.get('timestamp_utc', datetime.now().isoformat()),
            str(data.get('recorded_by', 'system')),
            0
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Sale saved to SQL Server")
        return True
    except Exception as e:
        logger.error(f"SQL insert error: {e}")
        return False

def save_to_memory(data):
    """Store sale in memory for fast retrieval"""
    sale_record = {
        'sale_id': data.get('sale_id', ''),
        'customer_name': data.get('customer_name', ''),
        'customer_email': data.get('customer_email', ''),
        'product_category': data.get('product_category', ''),
        'product_name': data.get('product', ''),
        'quantity': data.get('quantity', 0),
        'unit_price': data.get('unit_price', 0),
        'total_sales': data.get('total_sales', 0),
        'rewards_earned': data.get('rewards_earned', 0),
        'sale_date': data.get('sale_date', datetime.now().strftime('%Y-%m-%d')),
        'sale_time': data.get('sale_time', datetime.now().strftime('%H:%M:%S')),
        'recorded_by': data.get('recorded_by', 'system'),
        'created_at': datetime.now().isoformat(),
        'etl_processed': 0
    }
    
    sales_memory.insert(0, sale_record)
    if len(sales_memory) > 200:
        sales_memory.pop()
    
    stats['total_received'] += 1
    stats['today_received'] += 1
    stats['last_sale'] = sale_record
    
    return True

# ============================================
# API ENDPOINTS
# ============================================

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        logger.info(f"Received sale from: {data.get('customer_name')} - ${data.get('total_sales', 0):,.2f}")
        
        save_to_memory(data)
        sql_success = save_to_sql_server(data)
        
        if sql_success:
            return jsonify({
                "status": "success",
                "message": "Sale recorded successfully",
                "sale_id": data.get('sale_id')
            }), 200
        else:
            return jsonify({"status": "error", "message": "Failed to save"}), 500
            
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    try:
        if sales_memory:
            today = datetime.now().strftime('%Y-%m-%d')
            today_sales = [s for s in sales_memory if s.get('sale_date') == today]
            if today_sales:
                return jsonify(today_sales[:50]), 200
        
        conn = get_sql_connection()
        if conn:
            query = """
                SELECT TOP 50 
                    sale_id, customer_name, customer_email,
                    product_category, product_name, quantity,
                    unit_price, total_sales, rewards_earned,
                    sale_date, sale_time, recorded_by,
                    created_at, etl_processed
                FROM etl_sales_raw
                WHERE sale_date = CAST(GETDATE() AS DATE)
                ORDER BY id DESC
            """
            df = pd.read_sql(query, conn)
            conn.close()
            
            if not df.empty:
                records = df.to_dict('records')
                for record in records:
                    save_to_memory(record)
                return jsonify(records), 200
        
        return jsonify([]), 200
        
    except Exception as e:
        logger.error(f"Error getting recent sales: {e}")
        return jsonify([]), 200

@app.route('/my-sales', methods=['GET'])
def get_my_sales():
    try:
        recorded_by = request.args.get('recorded_by', '')
        if not recorded_by:
            return jsonify({"error": "recorded_by parameter required"}), 400
        
        user_sales = [s for s in sales_memory if s.get('recorded_by') == recorded_by]
        if user_sales:
            return jsonify(user_sales[:50]), 200
        
        conn = get_sql_connection()
        if conn:
            query = """
                SELECT TOP 50 
                    sale_id, customer_name, customer_email,
                    product_category, product_name, quantity,
                    unit_price, total_sales, rewards_earned,
                    sale_date, sale_time, recorded_by,
                    created_at, etl_processed
                FROM etl_sales_raw
                WHERE recorded_by = ?
                AND sale_date = CAST(GETDATE() AS DATE)
                ORDER BY id DESC
            """
            df = pd.read_sql(query, conn, params=[recorded_by])
            conn.close()
            
            if not df.empty:
                return jsonify(df.to_dict('records')), 200
        
        return jsonify([]), 200
        
    except Exception as e:
        logger.error(f"Error getting user sales: {e}")
        return jsonify([]), 200

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "uptime_seconds": (datetime.now() - stats['start_time']).total_seconds(),
        "total_received": stats['total_received'],
        "today_received": stats['today_received'],
        "memory_sales": len(sales_memory)
    })

# ============================================
# PRODUCT ENDPOINTS
# ============================================

@app.route('/products', methods=['GET'])
def get_products():
    try:
        conn = get_sql_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500
        
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
        
        df = pd.read_sql(query, conn)
        conn.close()
        
        if df.empty:
            sample_products = [
                {'id': 1, 'product_code': 'PRD001', 'product_name': 'Golden Delicious Apples', 'category_name': 'Fresh Produce', 'unit_price': 2.99, 'current_stock': 45, 'available_stock': 45, 'reorder_level': 20, 'unit_of_measure': 'KG', 'stock_status': 'in-stock', 'stock_label': 'In Stock'},
                {'id': 2, 'product_code': 'PRD002', 'product_name': 'Fresh Bananas', 'category_name': 'Fresh Produce', 'unit_price': 1.49, 'current_stock': 60, 'available_stock': 60, 'reorder_level': 25, 'unit_of_measure': 'KG', 'stock_status': 'in-stock', 'stock_label': 'In Stock'},
                {'id': 3, 'product_code': 'PRD003', 'product_name': 'Beef Steak Rump', 'category_name': 'Meat & Poultry', 'unit_price': 12.99, 'current_stock': 18, 'available_stock': 18, 'reorder_level': 15, 'unit_of_measure': 'KG', 'stock_status': 'in-stock', 'stock_label': 'In Stock'},
                {'id': 4, 'product_code': 'PRD004', 'product_name': 'Chicken Breast Fillets', 'category_name': 'Meat & Poultry', 'unit_price': 8.99, 'current_stock': 5, 'available_stock': 5, 'reorder_level': 20, 'unit_of_measure': 'KG', 'stock_status': 'low-stock', 'stock_label': 'Low Stock'},
                {'id': 5, 'product_code': 'PRD005', 'product_name': 'Fresh Full Cream Milk 1L', 'category_name': 'Dairy', 'unit_price': 1.99, 'current_stock': 8, 'available_stock': 8, 'reorder_level': 15, 'unit_of_measure': 'L', 'stock_status': 'low-stock', 'stock_label': 'Low Stock'},
            ]
            return jsonify(sample_products), 200
        
        products = df.to_dict('records')
        return jsonify(products), 200
        
    except Exception as e:
        logger.error(f"Error getting products: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/products/categories', methods=['GET'])
def get_categories():
    try:
        query = """
            SELECT category_code, category_name
            FROM erp_product_categories
            WHERE is_active = 1
            ORDER BY category_name
        """
        df = execute_query(query)
        
        if df.empty:
            default_categories = [
                {'category_name': 'Fresh Produce'},
                {'category_name': 'Meat & Poultry'},
                {'category_name': 'Dairy'},
                {'category_name': 'Bakery'},
                {'category_name': 'Beverages'},
                {'category_name': 'Household'},
                {'category_name': 'Personal Care'},
                {'category_name': 'Snacks & Sweets'},
                {'category_name': 'Frozen Foods'},
                {'category_name': 'Grocery'},
                {'category_name': 'Processed Meats'},
                {'category_name': 'Spices & Seasonings'}
            ]
            return jsonify(default_categories), 200
        
        return jsonify(df.to_dict('records')), 200
        
    except Exception as e:
        logger.error(f"Error getting categories: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# SALES ORDER ENDPOINTS
# ============================================

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    """Create a sales order with stock update"""
    try:
        data = request.json
        conn = get_sql_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = conn.cursor()
        
        # Check if tables exist, if not create them
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sales_orders')
            BEGIN
                CREATE TABLE sales_orders (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    order_number VARCHAR(50) UNIQUE NOT NULL,
                    customer_name VARCHAR(100) NOT NULL,
                    customer_email VARCHAR(100),
                    order_date DATE NOT NULL,
                    order_time TIME,
                    subtotal DECIMAL(18,2) DEFAULT 0,
                    tax_amount DECIMAL(18,2) DEFAULT 0,
                    total_amount DECIMAL(18,2) DEFAULT 0,
                    rewards_earned DECIMAL(18,2) DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'Draft',
                    payment_status VARCHAR(20) DEFAULT 'Unpaid',
                    recorded_by VARCHAR(50),
                    notes TEXT,
                    created_at DATETIME DEFAULT GETDATE()
                )
                PRINT '✅ sales_orders table created'
            END
        """)
        
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sales_order_lines')
            BEGIN
                CREATE TABLE sales_order_lines (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    order_id INT REFERENCES sales_orders(id) ON DELETE CASCADE,
                    line_number INT NOT NULL,
                    product_id INT REFERENCES products(id),
                    product_code VARCHAR(50),
                    product_name VARCHAR(200),
                    product_category VARCHAR(50),
                    quantity DECIMAL(18,2) NOT NULL,
                    unit_price DECIMAL(18,2) DEFAULT 0,
                    discount_percent DECIMAL(5,2) DEFAULT 0,
                    line_total DECIMAL(18,2) DEFAULT 0,
                    created_at DATETIME DEFAULT GETDATE()
                )
                PRINT '✅ sales_order_lines table created'
            END
        """)
        
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sales_invoices')
            BEGIN
                CREATE TABLE sales_invoices (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    invoice_number VARCHAR(50) UNIQUE NOT NULL,
                    order_id INT REFERENCES sales_orders(id),
                    customer_name VARCHAR(100) NOT NULL,
                    customer_email VARCHAR(100),
                    invoice_date DATE NOT NULL,
                    due_date DATE,
                    subtotal DECIMAL(18,2) DEFAULT 0,
                    tax_amount DECIMAL(18,2) DEFAULT 0,
                    total_amount DECIMAL(18,2) DEFAULT 0,
                    amount_paid DECIMAL(18,2) DEFAULT 0,
                    balance_due DECIMAL(18,2) DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'Open',
                    recorded_by VARCHAR(50),
                    created_at DATETIME DEFAULT GETDATE()
                )
                PRINT '✅ sales_invoices table created'
            END
        """)
        
        # Generate order number
        order_number = 'SO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        # Calculate totals
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        rewards = total * 0.02
        
        # Insert sales order
        cursor.execute("""
            INSERT INTO sales_orders (
                order_number, customer_name, customer_email, order_date, order_time,
                subtotal, tax_amount, total_amount, rewards_earned,
                status, recorded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_number, data['customer_name'], data.get('customer_email', ''),
            datetime.now().strftime('%Y-%m-%d'), datetime.now().strftime('%H:%M:%S'),
            subtotal, tax, total, rewards,
            'Confirmed', data.get('recorded_by', 'system')
        ))
        
        order_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchval()
        
        # Insert order lines and update stock
        for i, item in enumerate(items):
            # Get product details
            cursor.execute("""
                SELECT product_code, product_name, category_name, current_stock
                FROM products p
                LEFT JOIN product_categories pc ON p.category_id = pc.id
                WHERE p.id = ?
            """, (item['product_id'],))
            product = cursor.fetchone()
            
            if not product:
                continue
            
            # Check stock
            if product[3] < item['quantity']:
                conn.rollback()
                conn.close()
                return jsonify({
                    "error": f"Insufficient stock for {product[1]}. Available: {product[3]}"
                }), 400
            
            # Insert order line
            cursor.execute("""
                INSERT INTO sales_order_lines (
                    order_id, line_number, product_id, product_code, product_name,
                    product_category, quantity, unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order_id, i + 1, item['product_id'], product[0], product[1],
                product[2], item['quantity'], item['unit_price'],
                item['quantity'] * item['unit_price']
            ))
            
            # Update stock
            cursor.execute("""
                UPDATE products SET current_stock = current_stock - ? WHERE id = ?
            """, (item['quantity'], item['product_id']))
        
        # Create invoice
        invoice_number = 'INV-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        cursor.execute("""
            INSERT INTO sales_invoices (
                invoice_number, order_id, customer_name, customer_email,
                invoice_date, due_date, subtotal, tax_amount, total_amount,
                recorded_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_number, order_id, data['customer_name'], data.get('customer_email', ''),
            datetime.now().strftime('%Y-%m-%d'), (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            subtotal, tax, total, data.get('recorded_by', 'system')
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
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
    """Get sales orders for a user or all"""
    try:
        recorded_by = request.args.get('recorded_by')
        date_filter = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        conn = get_sql_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        # Check if tables exist
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sys.tables WHERE name = 'sales_orders'")
        if cursor.fetchval() == 0:
            conn.close()
            return jsonify([]), 200
        
        query = """
            SELECT 
                so.order_number, so.customer_name, so.order_date, so.order_time,
                so.total_amount, so.rewards_earned, so.status,
                COUNT(sol.id) AS line_count,
                so.recorded_by
            FROM sales_orders so
            LEFT JOIN sales_order_lines sol ON so.id = sol.order_id
            WHERE CAST(so.order_date AS DATE) = ?
        """
        params = [date_filter]
        
        if recorded_by:
            query += " AND so.recorded_by = ?"
            params.append(recorded_by)
        
        query += " GROUP BY so.order_number, so.customer_name, so.order_date, so.order_time, so.total_amount, so.rewards_earned, so.status, so.recorded_by"
        query += " ORDER BY so.order_time DESC"
        
        df = pd.read_sql(query, conn, params=params)
        conn.close()
        
        return jsonify(df.to_dict('records')), 200
        
    except Exception as e:
        logger.error(f"Error getting sales orders: {e}")
        return jsonify({"error": str(e)}), 500

# ============================================
# PURCHASE ORDER ENDPOINTS
# ============================================

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    """Create a purchase order"""
    try:
        data = request.json
        conn = get_sql_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'purchase_orders')
            BEGIN
                CREATE TABLE purchase_orders (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    po_number VARCHAR(50) UNIQUE NOT NULL,
                    supplier_name VARCHAR(100) NOT NULL,
                    supplier_email VARCHAR(100),
                    order_date DATE NOT NULL,
                    expected_delivery_date DATE,
                    delivery_date DATE,
                    status VARCHAR(20) DEFAULT 'Draft',
                    subtotal DECIMAL(18,2) DEFAULT 0,
                    tax_amount DECIMAL(18,2) DEFAULT 0,
                    total_amount DECIMAL(18,2) DEFAULT 0,
                    notes TEXT,
                    created_by VARCHAR(50),
                    created_at DATETIME DEFAULT GETDATE()
                )
                PRINT '✅ purchase_orders table created'
            END
        """)
        
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'purchase_order_lines')
            BEGIN
                CREATE TABLE purchase_order_lines (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    po_id INT REFERENCES purchase_orders(id) ON DELETE CASCADE,
                    line_number INT NOT NULL,
                    product_id INT REFERENCES products(id),
                    product_code VARCHAR(50),
                    product_name VARCHAR(200),
                    quantity DECIMAL(18,2) NOT NULL,
                    unit_price DECIMAL(18,2) DEFAULT 0,
                    line_total DECIMAL(18,2) DEFAULT 0,
                    received_quantity DECIMAL(18,2) DEFAULT 0,
                    remaining_quantity DECIMAL(18,2) DEFAULT 0,
                    is_completed BIT DEFAULT 0,
                    created_at DATETIME DEFAULT GETDATE()
                )
                PRINT '✅ purchase_order_lines table created'
            END
        """)
        
        po_number = 'PO-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        items = data.get('items', [])
        subtotal = sum(item['quantity'] * item['unit_price'] for item in items)
        tax = subtotal * 0.155
        total = subtotal + tax
        
        cursor.execute("""
            INSERT INTO purchase_orders (
                po_number, supplier_name, supplier_email, order_date,
                expected_delivery_date, subtotal, tax_amount, total_amount,
                status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            po_number, data['supplier_name'], data.get('supplier_email', ''),
            datetime.now().strftime('%Y-%m-%d'), data.get('expected_delivery_date'),
            subtotal, tax, total,
            'Draft', data.get('created_by', 'system')
        ))
        
        po_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchval()
        
        for i, item in enumerate(items):
            cursor.execute("""
                INSERT INTO purchase_order_lines (
                    po_id, line_number, product_id, product_code, product_name,
                    quantity, unit_price, line_total
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                po_id, i + 1, item['product_id'], item.get('product_code', ''),
                item.get('product_name', ''), item['quantity'], item['unit_price'],
                item['quantity'] * item['unit_price']
            ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
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
    """Get all purchase orders"""
    try:
        conn = get_sql_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sys.tables WHERE name = 'purchase_orders'")
        if cursor.fetchval() == 0:
            conn.close()
            return jsonify([]), 200
        
        query = """
            SELECT 
                po_number, supplier_name, order_date, expected_delivery_date,
                status, total_amount,
                COUNT(pol.id) AS line_count
            FROM purchase_orders po
            LEFT JOIN purchase_order_lines pol ON po.id = pol.po_id
            GROUP BY po_number, supplier_name, order_date, expected_delivery_date,
                     status, total_amount
            ORDER BY order_date DESC
        """
        df = pd.read_sql(query, conn)
        conn.close()
        
        return jsonify(df.to_dict('records')), 200
        
    except Exception as e:
        logger.error(f"Error getting purchase orders: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/goods-receipt', methods=['POST'])
def receive_goods():
    """Receive goods and update stock"""
    try:
        data = request.json
        conn = get_sql_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed"}), 500
        
        cursor = conn.cursor()
        
        # Check if goods_receipts table exists
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'goods_receipts')
            BEGIN
                CREATE TABLE goods_receipts (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    receipt_number VARCHAR(50) UNIQUE NOT NULL,
                    po_id INT REFERENCES purchase_orders(id),
                    supplier_name VARCHAR(100) NOT NULL,
                    receipt_date DATE NOT NULL,
                    status VARCHAR(20) DEFAULT 'Draft',
                    total_quantity DECIMAL(18,2) DEFAULT 0,
                    total_cost DECIMAL(18,2) DEFAULT 0,
                    notes TEXT,
                    created_by VARCHAR(50),
                    created_at DATETIME DEFAULT GETDATE(),
                    posted_at DATETIME,
                    posted_by VARCHAR(50)
                )
                PRINT '✅ goods_receipts table created'
            END
        """)
        
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'goods_receipt_lines')
            BEGIN
                CREATE TABLE goods_receipt_lines (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    receipt_id INT REFERENCES goods_receipts(id) ON DELETE CASCADE,
                    line_number INT NOT NULL,
                    product_id INT REFERENCES products(id),
                    product_code VARCHAR(50),
                    product_name VARCHAR(200),
                    quantity DECIMAL(18,2) NOT NULL,
                    unit_cost DECIMAL(18,2) DEFAULT 0,
                    total_cost DECIMAL(18,2) DEFAULT 0,
                    created_at DATETIME DEFAULT GETDATE()
                )
                PRINT '✅ goods_receipt_lines table created'
            END
        """)
        
        receipt_number = 'GRN-' + datetime.now().strftime('%Y%m%d') + '-' + str(random.randint(1000, 9999))
        
        # Get PO details
        cursor.execute("""
            SELECT po_number, supplier_name FROM purchase_orders WHERE id = ?
        """, (data['po_id'],))
        po = cursor.fetchone()
        
        if not po:
            return jsonify({"error": "Purchase order not found"}), 404
        
        items = data.get('items', [])
        total_quantity = sum(item['quantity'] for item in items)
        total_cost = sum(item['quantity'] * item['unit_cost'] for item in items)
        
        # Create goods receipt
        cursor.execute("""
            INSERT INTO goods_receipts (
                receipt_number, po_id, supplier_name, receipt_date,
                total_quantity, total_cost, status, created_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            receipt_number, data['po_id'], po[1], datetime.now().strftime('%Y-%m-%d'),
            total_quantity, total_cost, 'Draft', data.get('created_by', 'system')
        ))
        
        receipt_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchval()
        
        for i, item in enumerate(items):
            # Get product details
            cursor.execute("SELECT product_code, product_name FROM products WHERE id = ?", (item['product_id'],))
            product = cursor.fetchone()
            
            # Insert receipt line
            cursor.execute("""
                INSERT INTO goods_receipt_lines (
                    receipt_id, line_number, product_id, product_code, product_name,
                    quantity, unit_cost, total_cost
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                receipt_id, i + 1, item['product_id'], product[0] if product else '',
                product[1] if product else '', item['quantity'], item['unit_cost'],
                item['quantity'] * item['unit_cost']
            ))
            
            # Update product stock
            cursor.execute("""
                UPDATE products 
                SET current_stock = current_stock + ? 
                WHERE id = ?
            """, (item['quantity'], item['product_id']))
        
        # Update PO status
        cursor.execute("""
            UPDATE purchase_orders 
            SET status = 'Partially Received',
                delivery_date = GETDATE()
            WHERE id = ?
        """, (data['po_id'],))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "receipt_number": receipt_number,
            "total_quantity": total_quantity,
            "total_cost": total_cost
        }), 200
        
    except Exception as e:
        logger.error(f"Error receiving goods: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/sales/stats', methods=['GET'])
def get_sales_stats():
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        today_sales = [s for s in sales_memory if s.get('sale_date') == today]
        today_total = sum(float(s.get('total_sales', 0)) for s in today_sales)
        today_count = len(today_sales)
        
        total_revenue = sum(float(s.get('total_sales', 0)) for s in sales_memory)
        total_orders = len(sales_memory)
        
        low_query = """
            SELECT COUNT(*) as low_count
            FROM erp_products
            WHERE (ISNULL(current_stock, 0) - ISNULL(reserved_stock, 0)) <= reorder_level
            AND is_active = 1
        """
        low_df = execute_query(low_query)
        low_count = low_df.iloc[0]['low_count'] if not low_df.empty else 0
        
        product_query = "SELECT COUNT(*) as total FROM erp_products WHERE is_active = 1"
        product_df = execute_query(product_query)
        total_products = product_df.iloc[0]['total'] if not product_df.empty else 0
        
        return jsonify({
            'today_sales': today_total,
            'today_orders': today_count,
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'low_stock_count': low_count,
            'total_products': total_products
        }), 200
        
    except Exception as e:
        logger.error(f"Error getting sales stats: {e}")
        return jsonify({"error": str(e)}), 500

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

@app.route('/', methods=['OPTIONS', 'GET'])
def index():
    return jsonify({
        "service": "SPAR ETL Receiver",
        "status": "running",
        "endpoints": {
            "webhook": "POST /webhook",
            "health": "GET /health",
            "stats": "GET /stats",
            "recent": "GET /recent",
            "my-sales": "GET /my-sales?recorded_by=username",
            "products": "GET /products",
            "products/categories": "GET /products/categories",
            "sales-orders": "POST /sales-orders (create), GET /sales-orders (list)",
            "purchase-orders": "POST /purchase-orders (create), GET /purchase-orders (list)",
            "goods-receipt": "POST /goods-receipt",
            "sales/stats": "GET /sales/stats"
        }
    })

if __name__ == '__main__':
    print("=" * 70)
    print("🛒 SPAR ETL RECEIVER - COMPLETE ERP API")
    print("=" * 70)
    print(f"\n🚀 Starting server on port 8000...")
    print(f"\n📍 Local URL: http://localhost:8000")
    print(f"📍 Products: http://localhost:8000/products")
    print(f"📍 Sales Orders: http://localhost:8000/sales-orders")
    print(f"📍 Purchase Orders: http://localhost:8000/purchase-orders")
    print(f"📍 Recent Sales: http://localhost:8000/recent")
    print(f"📍 Health: http://localhost:8000/health")
    print("\nPress Ctrl+C to stop")
    print("=" * 70)
    
    app.run(host='0.0.0.0', port=8000, debug=False, threaded=True)