"""SPAR ETL Receiver - Render Version
Complete API with Products, Sales, Purchase Orders, and Goods Receiving
"""
from flask import Flask, request, jsonify
from datetime import datetime
import logging
import os
import random
import requests
import traceback

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
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        
        logger.info(f"📡 Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Query returned {len(result) if isinstance(result, list) else '?'} rows")
            return result
        else:
            logger.error(f"❌ Cloudflare query error: {response.status_code} - {response.text[:200]}")
            return []
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ Connection error: {e}")
        return []
    except Exception as e:
        logger.error(f"❌ Cloudflare query exception: {e}")
        traceback.print_exc()
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
            timeout=60,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"✅ Command executed: {result}")
            return result
        else:
            logger.error(f"❌ Cloudflare command error: {response.status_code} - {response.text[:200]}")
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
        except requests.exceptions.ConnectionError:
            cloudflare_status = "disconnected (connection refused)"
            logger.error("❌ Cannot reach Cloudflare tunnel - connection refused")
        except requests.exceptions.Timeout:
            cloudflare_status = "disconnected (timeout)"
            logger.error("❌ Cloudflare tunnel timeout")
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
        return jsonify(result if result else []), 200
    except Exception as e:
        logger.error(f"❌ Error getting products: {e}")
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
            "sales_orders": "GET /sales-orders",
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
    print("   GET  /sales-orders")
    print("   GET  /recent")
    print("=" * 70)
    app.run(host='0.0.0.0', port=port, debug=False)
