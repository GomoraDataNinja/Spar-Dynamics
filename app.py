from flask import Flask, jsonify, request
from flask_cors import CORS
import pymssql
import json
from datetime import time, datetime, date
import decimal
import os

app = Flask(__name__)
CORS(app)

# ============================================
# CUSTOM JSON ENCODER - FIXES TIME SERIALIZATION
# ============================================
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, time):
            return obj.strftime('%H:%M:%S')
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        if isinstance(obj, decimal.Decimal):
            return float(obj)
        return super().default(obj)

app.json_encoder = CustomJSONEncoder

# ============================================
# DATABASE CONNECTION
# ============================================
def get_db_connection():
    # Use environment variables for security
    server = os.environ.get('DB_SERVER', 'your_server.database.windows.net')
    database = os.environ.get('DB_NAME', 'SPAR_ETL')
    username = os.environ.get('DB_USER', 'your_username')
    password = os.environ.get('DB_PASSWORD', 'your_password')
    
    return pymssql.connect(
        server=server,
        user=username,
        password=password,
        database=database,
        timeout=30
    )

# ============================================
# ROUTES
# ============================================

@app.route('/')
def index():
    return jsonify({
        'status': 'running',
        'message': 'SPAR Dynamics 365 Backend API',
        'version': '1.0.0'
    })

@app.route('/health', methods=['GET'])
def health():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM erp_sales_orders")
        count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'connected',
            'total_received': count,
            'message': 'ETL is running'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'total_received': 0,
            'message': str(e)
        }), 500

@app.route('/sales-orders', methods=['GET'])
def get_sales_orders():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id,
                so_number,
                customer_id,
                order_date,
                order_time,
                subtotal,
                tax_amount,
                total_amount,
                rewards_earned,
                status,
                payment_status,
                created_at
            FROM erp_sales_orders 
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            result.append({
                'id': row[0],
                'order_number': row[1],
                'customer_id': row[2],
                'order_date': row[3].isoformat() if row[3] else None,
                'order_time': str(row[4]) if row[4] else None,
                'subtotal': float(row[5]) if row[5] else 0,
                'tax_amount': float(row[6]) if row[6] else 0,
                'total_amount': float(row[7]) if row[7] else 0,
                'rewards_earned': float(row[8]) if row[8] else 0,
                'status': row[9] or 'Draft',
                'payment_status': row[10] or 'Pending',
                'created_at': row[11].isoformat() if row[11] else None
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/sales-orders', methods=['POST'])
def create_sales_order():
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get customer or create new
        customer_name = data.get('customer_name', '').strip()
        customer_email = data.get('customer_email', '').strip()
        
        cursor.execute("""
            SELECT id FROM erp_customers 
            WHERE LTRIM(RTRIM(customer_name)) = LTRIM(RTRIM(%s))
        """, (customer_name,))
        customer_row = cursor.fetchone()
        
        if customer_row:
            customer_id = customer_row[0]
        else:
            # Create new customer
            cursor.execute("""
                INSERT INTO erp_customers (
                    customer_code,
                    customer_name,
                    email,
                    country,
                    payment_terms,
                    is_active,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, GETDATE())
            """, (
                'CUST-' + datetime.now().strftime('%Y%m%d%H%M%S'),
                customer_name,
                customer_email,
                'Zimbabwe',
                'Cash',
                1
            ))
            customer_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
        
        # Generate SO number
        cursor.execute("""
            SELECT COUNT(*) + 1 FROM erp_sales_orders 
            WHERE CAST(created_at AS DATE) = CAST(GETDATE() AS DATE)
        """)
        next_number = cursor.fetchone()[0]
        so_number = f"SO-{datetime.now().strftime('%Y%m%d')}-{next_number:04d}"
        
        # Calculate totals
        subtotal = 0
        for item in data.get('items', []):
            subtotal += item['quantity'] * item['unit_price']
        
        tax_amount = subtotal * 0.155
        total_amount = subtotal + tax_amount
        rewards_earned = total_amount * 0.02
        
        # Insert sales order
        cursor.execute("""
            INSERT INTO erp_sales_orders (
                so_number,
                customer_id,
                order_date,
                order_time,
                subtotal,
                tax_amount,
                total_amount,
                rewards_earned,
                status,
                payment_status,
                created_at,
                updated_at
            ) VALUES (%s, %s, GETDATE(), CAST(%s AS TIME), %s, %s, %s, %s, %s, %s, GETDATE(), GETDATE())
        """, (
            so_number,
            customer_id,
            datetime.now().strftime('%H:%M:%S'),
            subtotal,
            tax_amount,
            total_amount,
            rewards_earned,
            'Confirmed',
            'Paid'
        ))
        
        order_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
        
        # Insert order lines and update stock
        for idx, item in enumerate(data.get('items', [])):
            product_id = item['product_id']
            quantity = item['quantity']
            unit_price = item['unit_price']
            line_total = quantity * unit_price
            line_tax = line_total * 0.155
            
            # Get product info
            cursor.execute("""
                SELECT product_code, product_name FROM erp_products WHERE id = %s
            """, (product_id,))
            product = cursor.fetchone()
            
            # Insert order line
            cursor.execute("""
                INSERT INTO erp_sales_order_lines (
                    so_id,
                    line_number,
                    product_id,
                    product_code,
                    product_name,
                    quantity,
                    unit_price,
                    line_total,
                    tax_rate,
                    tax_amount,
                    created_at,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, GETDATE(), GETDATE())
            """, (
                order_id,
                idx + 1,
                product_id,
                product[0] if product else '',
                product[1] if product else '',
                quantity,
                unit_price,
                line_total,
                15.5,
                line_tax
            ))
            
            # Update stock
            cursor.execute("""
                UPDATE erp_products 
                SET current_stock = current_stock - %s,
                    available_stock = available_stock - %s
                WHERE id = %s
            """, (quantity, quantity, product_id))
        
        conn.commit()
        conn.close()
        
        # Also insert into etl_sales_raw for ETL processing
        try:
            etl_conn = get_db_connection()
            etl_cursor = etl_conn.cursor()
            
            sale_data = data.get('items', [])
            product_names = []
            product_categories = []
            total_qty = 0
            total_value = 0
            
            for item in sale_data:
                cursor.execute("SELECT product_name, category_name FROM erp_products WHERE id = %s", (item['product_id'],))
                p = cursor.fetchone()
                if p:
                    product_names.append(p[0])
                    product_categories.append(p[1] or 'General')
                total_qty += item['quantity']
                total_value += item['quantity'] * item['unit_price']
            
            etl_cursor.execute("""
                INSERT INTO etl_sales_raw (
                    sale_id,
                    customer_name,
                    customer_email,
                    product_category,
                    quantity,
                    unit_price,
                    total_sales,
                    rewards_earned,
                    sale_date,
                    sale_time,
                    timestamp_utc,
                    recorded_by,
                    etl_processed,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, GETDATE(), CAST(%s AS TIME), GETUTCDATE(), %s, 0, GETDATE())
            """, (
                so_number,
                customer_name,
                customer_email,
                ', '.join(product_categories[:3]),
                total_qty,
                sale_data[0]['unit_price'] if sale_data else 0,
                total_value,
                rewards_earned,
                datetime.now().strftime('%H:%M:%S'),
                data.get('recorded_by', 'system')
            ))
            etl_conn.commit()
            etl_conn.close()
        except Exception as e:
            print(f"ETL insert error: {e}")
        
        return jsonify({
            'success': True,
            'order_number': so_number,
            'order_id': order_id,
            'invoice_number': f"INV-{so_number}"
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/products', methods=['GET'])
def get_products():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id,
                product_code,
                product_name,
                category_name,
                unit_price,
                current_stock,
                available_stock,
                reorder_level,
                unit_of_measure,
                is_active,
                created_at
            FROM erp_products 
            WHERE is_active = 1
            ORDER BY product_name
        """)
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            stock = row[6] if row[6] is not None else row[5]
            reorder = row[7] or 10
            
            if stock is None:
                stock = 0
            
            status = 'in-stock'
            if stock <= 0:
                status = 'out-of-stock'
            elif stock <= reorder:
                status = 'low-stock'
            
            result.append({
                'id': row[0],
                'product_code': row[1],
                'product_name': row[2],
                'category_name': row[3],
                'unit_price': float(row[4]) if row[4] else 0,
                'current_stock': float(stock),
                'available_stock': float(stock),
                'reorder_level': reorder,
                'unit_of_measure': row[8] or 'EA',
                'stock_status': status,
                'stock_label': {
                    'in-stock': 'In Stock',
                    'low-stock': 'Low Stock',
                    'out-of-stock': 'Out of Stock'
                }[status],
                'created_at': row[10].isoformat() if row[10] else None
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/products/add', methods=['POST'])
def add_product():
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO erp_products (
                product_code,
                product_name,
                category_name,
                unit_of_measure,
                unit_price,
                cost_price,
                current_stock,
                available_stock,
                reorder_level,
                is_active,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, GETDATE(), GETDATE())
        """, (
            data['product_code'],
            data['product_name'],
            data['category_name'],
            data.get('unit_of_measure', 'EA'),
            data.get('unit_price', 0),
            data.get('cost_price', 0),
            data.get('initial_stock', 0),
            data.get('initial_stock', 0),
            data.get('reorder_level', 10)
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Product added'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/purchase-orders', methods=['GET'])
def get_purchase_orders():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                po_number,
                supplier_name,
                order_date,
                expected_delivery_date,
                total_amount,
                status,
                created_at
            FROM purchase_orders
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            result.append({
                'po_number': row[0],
                'supplier_name': row[1],
                'order_date': row[2].isoformat() if row[2] else None,
                'expected_delivery_date': row[3].isoformat() if row[3] else None,
                'total_amount': float(row[4]) if row[4] else 0,
                'status': row[5] or 'Draft',
                'created_at': row[6].isoformat() if row[6] else None
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/purchase-orders', methods=['POST'])
def create_purchase_order():
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Generate PO number
        cursor.execute("SELECT COUNT(*) + 1 FROM purchase_orders")
        count = cursor.fetchone()[0]
        po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{str(count).zfill(4)}"
        
        # Calculate total
        total = sum(item['quantity'] * item['unit_price'] for item in data.get('items', []))
        tax = total * 0.155
        grand_total = total + tax
        
        cursor.execute("""
            INSERT INTO purchase_orders (
                po_number,
                supplier_name,
                supplier_email,
                order_date,
                expected_delivery_date,
                subtotal,
                tax_amount,
                total_amount,
                status,
                created_by,
                created_at
            ) VALUES (%s, %s, %s, GETDATE(), %s, %s, %s, %s, %s, %s, GETDATE())
        """, (
            po_number,
            data['supplier_name'],
            data.get('supplier_email', ''),
            data.get('expected_delivery_date'),
            total,
            tax,
            grand_total,
            'Open',
            data.get('created_by', 'system')
        ))
        
        po_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
        
        for idx, item in enumerate(data.get('items', [])):
            cursor.execute("""
                INSERT INTO purchase_order_lines (
                    po_id,
                    line_number,
                    product_id,
                    product_code,
                    product_name,
                    quantity,
                    unit_price,
                    line_total,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, GETDATE())
            """, (
                po_id,
                idx + 1,
                item['product_id'],
                item.get('product_code', ''),
                item.get('product_name', ''),
                item['quantity'],
                item['unit_price'],
                item['quantity'] * item['unit_price']
            ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'po_number': po_number,
            'po_id': po_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/recent', methods=['GET'])
def get_recent_sales():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 10
                sale_id,
                customer_name,
                total_sales,
                rewards_earned,
                sale_date,
                sale_time,
                recorded_by,
                etl_processed,
                created_at
            FROM etl_sales_raw
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        result = []
        for row in rows:
            result.append({
                'sale_id': row[0],
                'customer_name': row[1],
                'total_sales': float(row[2]) if row[2] else 0,
                'rewards_earned': float(row[3]) if row[3] else 0,
                'sale_date': row[4].isoformat() if row[4] else None,
                'sale_time': str(row[5]) if row[5] else None,
                'recorded_by': row[6] or 'system',
                'etl_processed': row[7] or 0,
                'created_at': row[8].isoformat() if row[8] else None
            })
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO etl_sales_raw (
                sale_id,
                customer_name,
                customer_email,
                product_category,
                quantity,
                unit_price,
                total_sales,
                rewards_earned,
                sale_date,
                sale_time,
                timestamp_utc,
                recorded_by,
                etl_processed,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, GETDATE())
        """, (
            data.get('sale_id'),
            data.get('customer_name'),
            data.get('customer_email'),
            data.get('product_category'),
            data.get('quantity', 0),
            data.get('unit_price', 0),
            data.get('total_sales', 0),
            data.get('rewards_earned', 0),
            data.get('sale_date'),
            data.get('sale_time'),
            data.get('timestamp_utc'),
            data.get('recorded_by', 'webhook')
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Webhook received'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
