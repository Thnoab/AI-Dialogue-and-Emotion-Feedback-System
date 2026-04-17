from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import pymysql
import uuid                     # ← 新增：生成 Token
from datetime import datetime, timedelta   # ← 新增：过期时间计算

app = Flask(__name__)
CORS(app)

# 配置区域
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '1121',  # 数据库密码
    'db': 'tavern_users',  # 数据库名
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

# 1. 首页路由
@app.route('/')
def home():
    return render_template('index.html')

# ==================== 新增：获取当前登录用户（自动登录用） ====================
@app.route('/api/me', methods=['GET'])
def get_current_user():
    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return jsonify({"code": 401, "message": "未登录"}), 401
    
    token = auth[7:]
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = """
                SELECT u.id, u.username, u.created_at 
                FROM sessions s 
                JOIN users u ON s.user_id = u.id 
                WHERE s.session_token = %s 
                  AND s.expires_at > NOW()
            """
            cursor.execute(sql, (token,))
            user = cursor.fetchone()
            
            if user:
                return jsonify({"code": 200, "data": user}), 200
            else:
                return jsonify({"code": 401, "message": "会话已过期或无效"}), 401
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"code": 500, "message": "服务器内部错误"}), 500
    finally:
        if connection:
            connection.close()

# ==================== 新增：退出登录 ====================
@app.route('/api/logout', methods=['POST'])
def logout():
    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return jsonify({"code": 200, "message": "已退出"}), 200
    
    token = auth[7:]
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE session_token = %s", (token,))
            connection.commit()
        return jsonify({"code": 200, "message": "退出成功"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"code": 500, "message": "服务器内部错误"}), 500
    finally:
        if connection:
            connection.close()

# ==================== 登录接口（已完整加入 Token 机制） ====================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"code": 400, "message": "账号或密码不能为空"}), 400

    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            # 查询用户
            sql = "SELECT id, username, created_at FROM users WHERE username = %s AND password = %s"
            cursor.execute(sql, (username, password))
            user = cursor.fetchone()
            
            if not user:
                return jsonify({"code": 401, "message": "用户名或密码错误"}), 401
            
            # ==================== Token 机制核心代码 ====================
            session_token = uuid.uuid4().hex
            expires_at = datetime.now() + timedelta(days=7)
            
            sql_session = """
                INSERT INTO sessions (session_token, user_id, expires_at) 
                VALUES (%s, %s, %s)
            """
            cursor.execute(sql_session, (session_token, user['id'], expires_at))
            connection.commit()
            # =========================================================
            
            # 返回用户信息 + token
            user['token'] = session_token
            return jsonify({
                "code": 200,
                "message": "登录成功",
                "data": user
            }), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"code": 500, "message": "服务器内部错误"}), 500
    finally:
        if connection:
            connection.close()

# ==================== 注册接口（保持不变） ====================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"code": 400, "message": "账号或密码不能为空"}), 400

    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            # 查重
            sql_check = "SELECT id FROM users WHERE username = %s"
            cursor.execute(sql_check, (username,))
            if cursor.fetchone():
                return jsonify({"code": 409, "message": "用户已存在"}), 409
            
            # 写入
            sql_insert = "INSERT INTO users (username, password) VALUES (%s, %s)"
            cursor.execute(sql_insert, (username, password))
            connection.commit()
            
        return jsonify({"code": 200, "message": "注册成功！请登录"}), 200
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"code": 500, "message": str(e)}), 500
    finally:
        if connection:
            connection.close()

if __name__ == '__main__':
    print("🍷 酒馆已开张: http://localhost:5000")
    app.run(debug=True, port=5000)