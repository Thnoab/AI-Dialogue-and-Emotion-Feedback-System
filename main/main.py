from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import sqlite3
import uuid
from datetime import datetime, timedelta
import hashlib
import time
import os
import json

# ================= 全局配置项 (后端可随时修改) =================
INVITE_CODE = "Invited@123"           # VIP 邀请码
ADMIN_SECRET_SUFFIX = "@P2m;"         # 管理员动态秘钥后缀
# =============================================================

app = FastAPI(title="AI酒馆 - 用户与鉴权模块")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

if not os.path.exists("templates"): os.makedirs("templates")
app.mount("/static", StaticFiles(directory="templates"), name="static")

security = HTTPBearer()

def get_db():
    conn = sqlite3.connect("tavern_users.db")
    conn.row_factory = sqlite3.Row
    return conn

# 💡 新增：专门从 JSON 读取角色的函数 (满足你不查数据库的要求)
def get_role_from_json(username: str) -> str:
    file_path = os.path.join("player_cards", f"{username}_profile.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            return profile.get("role", "Adventurer")
        except Exception:
            pass
    return "Adventurer"

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.id, u.username, u.email, u.level, u.personal_code, u.is_vip, u.avatar, u.created_at
            FROM sessions s JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ? AND s.expires_at > datetime('now')
        """, (token,))
        user = cursor.fetchone()
        if not user: raise HTTPException(status_code=401, detail={"code": 401, "message": "会话已过期"})
        
        user_dict = dict(user)
        # 💡 在返回前，强行去读取一次 JSON 拿到最新的 role
        user_dict["role"] = get_role_from_json(user_dict["username"])
        return user_dict
    finally:
        conn.close()

@app.get("/")
async def home(): return FileResponse("templates/index.html")

@app.get("/api/me")
async def get_current_user_endpoint(user: dict = Depends(get_current_user)):
    return {"code": 200, "data": user}

@app.post("/api/login")
async def login(data: dict):
    username = data.get("username")
    password = data.get("password")
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, email, level, personal_code, is_vip, avatar, created_at FROM users WHERE username = ? AND password = ?",
            (username, password)
        )
        user = cursor.fetchone()
        if not user: return {"code": 401, "message": "用户名或密码错误"}
        session_token = uuid.uuid4().hex
        expires_at = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO sessions (session_token, user_id, expires_at) VALUES (?, ?, ?)", (session_token, user["id"], expires_at))
        conn.commit()
        
        user_dict = dict(user)
        user_dict["token"] = session_token
        # 💡 登录成功时，也从 JSON 读取 role 返回给前端
        user_dict["role"] = get_role_from_json(user_dict["username"])
        return {"code": 200, "message": "登录成功", "data": user_dict}
    finally:
        conn.close()

@app.post("/api/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sessions WHERE session_token = ?", (token,))
        conn.commit()
        return {"code": 200, "message": "退出成功"}
    finally:
        conn.close()

@app.post("/api/register")
async def register(data: dict):
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")
    if not username or not email or not password: return {"code": 400, "message": "信息填写不完整"}
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone(): return {"code": 409, "message": "用户已存在"}
        personal_code = hashlib.sha256(f"{username}_{time.time()}_secret".encode('utf-8')).hexdigest()[:16].upper() 
        cursor.execute("INSERT INTO users (username, email, password, level, personal_code, is_vip, avatar) VALUES (?, ?, ?, ?, ?, 0, '')",
            (username, email, password, 1, personal_code))
        conn.commit()
        
        os.makedirs("player_cards", exist_ok=True)
        # 💡 默认设定为 Adventurer (普通冒险者)
        with open(os.path.join("player_cards", f"{username}_profile.json"), "w", encoding="utf-8") as f:
            json.dump({"username": username, "email": email, "level": 1, "personal_code": personal_code, "is_vip": 0, "role": "Adventurer", "status": "active"}, f, ensure_ascii=False, indent=4)
        return {"code": 200, "message": "注册成功！请登录"}
    finally:
        conn.close()

@app.post("/api/recover_password")
async def recover_password(data: dict):
    username = data.get("username")
    email = data.get("email")
    new_password = data.get("new_password")
    if not username or not email or not new_password: return {"code": 400, "message": "信息不完整"}
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE username = ? AND email = ?", (username, email))
        user = cursor.fetchone()
        if not user: return {"code": 404, "message": "账号或邮箱错误"}
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user["id"]))
        conn.commit()
        return {"code": 200, "message": "密码重置成功！"}
    finally:
        conn.close()

@app.post("/api/change_password")
async def change_password(data: dict, user: dict = Depends(get_current_user)):
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    if not old_password or not new_password: return {"code": 400, "message": "密码不能为空"}
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE id = ? AND password = ?", (user['id'], old_password))
        if not cursor.fetchone(): return {"code": 401, "message": "原密码输入错误"}
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (new_password, user['id']))
        conn.commit()
        return {"code": 200, "message": "密码修改成功，请重新登录"}
    finally:
        conn.close()

# ========== 💡 新增：兑换码综合接口 ==========
@app.post("/api/redeem_code")
async def redeem_code(data: dict, user: dict = Depends(get_current_user)):
    code = data.get("code", "")
    if not code:
        return {"code": 400, "message": "兑换码不能为空"}

    # 1. 动态生成今天的管理员秘钥 (例如：20260507@P2m;)
    today_str = datetime.now().strftime("%Y%m%d")
    dynamic_admin_key = f"{today_str}{ADMIN_SECRET_SUFFIX}"

    file_path = os.path.join("player_cards", f"{user['username']}_profile.json")

    # 匹配管理员秘钥
    if code == dynamic_admin_key:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: profile = json.load(f)
            profile["role"] = "Admin" # 写入管理员身份
            with open(file_path, "w", encoding="utf-8") as f: json.dump(profile, f, ensure_ascii=False, indent=4)
            return {"code": 200, "message": "秘钥验证成功！您已拥有管理员最高权限。", "data": {"type": "admin"}}
        return {"code": 500, "message": "找不到档案文件"}

    # 匹配 VIP 邀请码
    if code == INVITE_CODE:
        if user['is_vip'] == 1:
            return {"code": 400, "message": "您已经是 VIP 了！"}
        # VIP 依然需要修改数据库
        conn = get_db()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_vip = 1 WHERE id = ?", (user['id'],))
            conn.commit()
        finally:
            conn.close()
            
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: profile = json.load(f)
            profile["is_vip"] = 1
            with open(file_path, "w", encoding="utf-8") as f: json.dump(profile, f, ensure_ascii=False, indent=4)
        return {"code": 200, "message": "兑换成功！已为您开通 VIP 权限。", "data": {"type": "vip"}}

    return {"code": 400, "message": "无效的秘钥或邀请码"}

# 其他接口 (upgrade_vip, update_profile, delete_account) 保持不变...
@app.post("/api/upgrade_vip")
async def upgrade_vip(user: dict = Depends(get_current_user)):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_vip = 1 WHERE id = ?", (user['id'],))
        conn.commit()
        file_path = os.path.join("player_cards", f"{user['username']}_profile.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f: profile = json.load(f)
            profile["is_vip"] = 1
            with open(file_path, "w", encoding="utf-8") as f: json.dump(profile, f, ensure_ascii=False, indent=4)
        return {"code": 200, "message": "支付成功！"}
    finally:
        conn.close()

@app.post("/api/update_profile")
async def update_profile(data: dict, user: dict = Depends(get_current_user)):
    new_username = data.get("username")
    new_avatar = data.get("avatar")
    conn = get_db()
    try:
        cursor = conn.cursor()
        if new_username and new_username != user['username']:
            cursor.execute("SELECT id FROM users WHERE username = ?", (new_username,))
            if cursor.fetchone(): return {"code": 409, "message": "被占用"}
        final_username = new_username or user['username']
        final_avatar = new_avatar or user['avatar']
        cursor.execute("UPDATE users SET username = ?, avatar = ? WHERE id = ?", (final_username, final_avatar, user['id']))
        conn.commit()
        if new_username and new_username != user['username']:
            old_path = os.path.join("player_cards", f"{user['username']}_profile.json")
            new_path = os.path.join("player_cards", f"{new_username}_profile.json")
            if os.path.exists(old_path):
                with open(old_path, "r", encoding="utf-8") as f: profile = json.load(f)
                profile["username"] = new_username
                with open(new_path, "w", encoding="utf-8") as f: json.dump(profile, f, ensure_ascii=False, indent=4)
                os.remove(old_path)
        return {"code": 200, "message": "更新成功"}
    finally:
        conn.close()

@app.post("/api/delete_account")
async def delete_account(user: dict = Depends(get_current_user)):
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE id = ?", (user['id'],))
        conn.commit()
        file_path = os.path.join("player_cards", f"{user['username']}_profile.json")
        if os.path.exists(file_path): os.remove(file_path)
        return {"code": 200, "message": "注销成功"}
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)