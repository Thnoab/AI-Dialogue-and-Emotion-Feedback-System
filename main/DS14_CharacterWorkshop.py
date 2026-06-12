import os
import json
import re
import shutil
import sqlite3
import traceback
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles


def _safe_filename(name: str) -> str:
    """
    生成适合文件系统和 URL 使用的 ID。
    保留中文、英文、数字、下划线和短横线；其它字符替换为下划线。
    """
    name = (name or "").strip()
    name = re.sub(r'[\\/:*?"<>|\s]+', "_", name)
    return name or "character"


def _env_path(env_name: str, default_path: str) -> str:
    """
    路径读取统一入口。
    如果环境变量给的是相对路径，则自动转成绝对路径。
    方便本地开发和服务器部署共用同一份代码。
    """
    value = os.getenv(env_name)
    path = value if value else default_path
    return os.path.abspath(path)


class CharacterWorkshopService:
    def __init__(self, base_dir: str, auth_service):
        self.base_dir = os.path.abspath(base_dir)
        self.auth_service = auth_service

        # 默认目录结构：
        # workshop/
        # ├── main/
        # │   ├── DS_API14.py
        # │   ├── characters/
        # │   └── static/images/
        # └── character_edit/
        #     ├── main.py
        #     ├── templates/
        #     └── static/
        #
        # 服务器上线时，如果目录结构不同，可以用环境变量覆盖。
        self.workshop_dir = _env_path(
            "CHAR_WORKSHOP_DIR",
            os.path.join(self.base_dir, "..", "character_edit")
        )

        self.template_dir = _env_path(
            "CHAR_WORKSHOP_TEMPLATE_DIR",
            os.path.join(self.workshop_dir, "templates")
        )

        self.static_dir = _env_path(
            "CHAR_WORKSHOP_STATIC_DIR",
            os.path.join(self.workshop_dir, "static")
        )

        # 角色工坊自己的管理数据库。
        self.db_path = _env_path(
            "CHAR_WORKSHOP_DB_PATH",
            os.path.join(self.workshop_dir, "instance", "tavern.db")
        )

        # 输出给主聊天系统读取的角色卡 JSON。
        self.chat_character_dir = _env_path(
            "CHAT_CHARACTER_DIR",
            os.path.join(self.base_dir, "characters")
        )

        # 输出给主聊天系统读取的立绘/表情图片。
        self.chat_image_dir = _env_path(
            "CHAT_IMAGE_DIR",
            os.path.join(self.base_dir, "static", "images")
        )

        # JSON 里写入的图片 URL 前缀。
        # 本地默认 /static/images，与主聊天页现有静态挂载一致。
        # 如果服务器上用 CDN 或 Nginx 映射，也可以通过环境变量改。
        self.chat_image_url_prefix = os.getenv("CHAT_IMAGE_URL_PREFIX", "/static/images").rstrip("/")

        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(self.chat_character_dir, exist_ok=True)
        os.makedirs(self.chat_image_dir, exist_ok=True)

        self.templates = Jinja2Templates(directory=self.template_dir)
        self.init_db()

    # ==================== 权限 ====================

    def get_token_from_request(self, request: Request):
        """
        角色工坊是服务端渲染页面，普通 fetch Authorization 不一定方便带。
        因此这里依次支持：
        1. Authorization: Bearer xxx
        2. Cookie: tavern_token=xxx
        3. URL: ?token=xxx
        """
        auth = request.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            return auth.replace("Bearer ", "", 1).strip()

        token = request.cookies.get("tavern_token")
        if token:
            return token

        token = request.query_params.get("token")
        if token:
            return token

        return None

    def require_admin(self, request: Request):
        token = self.get_token_from_request(request)
        if not token:
            raise HTTPException(status_code=401, detail="请先登录。")

        user = self.auth_service.verificare(token)
        if user.get("role") != "Admin":
            raise HTTPException(status_code=403, detail="只有管理员可以进入角色工坊。")

        return user

    # ==================== DB ====================

    def get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_db()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                prompt TEXT NOT NULL,
                attributes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()

    def create_character_record(self, name, description, prompt, attributes_dict):
        conn = self.get_db()
        attributes_json = json.dumps(attributes_dict, ensure_ascii=False)
        conn.execute(
            "INSERT INTO characters (name, description, prompt, attributes) VALUES (?, ?, ?, ?)",
            (name, description, prompt, attributes_json)
        )
        conn.commit()
        last_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return last_id

    def get_all_characters(self):
        conn = self.get_db()
        rows = conn.execute("SELECT * FROM characters ORDER BY created_at DESC").fetchall()
        conn.close()

        characters = []
        for row in rows:
            char = dict(row)
            char["attributes"] = json.loads(char["attributes"]) if char.get("attributes") else {}
            characters.append(char)
        return characters

    def get_character_by_name(self, name):
        conn = self.get_db()
        row = conn.execute("SELECT * FROM characters WHERE name = ?", (name,)).fetchone()
        conn.close()

        if row:
            char = dict(row)
            char["attributes"] = json.loads(char["attributes"]) if char.get("attributes") else {}
            return char
        return None

    # ==================== 文件处理 ====================

    def image_url(self, filename: str) -> str:
        return f"{self.chat_image_url_prefix}/{filename}"

    def save_upload_to_chat_images(self, upload_file, filename):
        save_path = os.path.join(self.chat_image_dir, filename)
        with open(save_path, "wb") as f:
            shutil.copyfileobj(upload_file.file, f)
        return self.image_url(filename)

    def build_character_json(self, name, prompt, matrix, inertia_list, avatar_path, expressions):
        """
        注意：
        character_id 必须和 JSON 文件名一致。
        你的 Detection.elige(character_id) 会按 characters/{character_id}.json 读取，
        所以这里不能用可能包含特殊字符的原始角色名当文件 ID。
        """
        character_id = _safe_filename(name)

        default_expressions = {
            "neutral": self.image_url("Neutral1.png"),
            "shy": self.image_url("Shy.png"),
            "happy": self.image_url("Smile1.png"),
            "angry": self.image_url("Angry.png"),
            "sad": self.image_url("Sad1.png")
        }

        final_expressions = expressions if expressions else default_expressions

        return {
            "character_id": character_id,
            "name": name,
            "prompt": prompt,
            "personality_matrix": matrix or [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
            "inertia": inertia_list or [0.5, 0.5, 0.5],
            "default_expression": "neutral",
            "avatar": avatar_path or final_expressions.get("neutral") or self.image_url("Neutral1.png"),
            "expressions": final_expressions
        }

    def write_character_json(self, name, character_json):
        safe_name = _safe_filename(name)
        json_path = os.path.join(self.chat_character_dir, f"{safe_name}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(character_json, f, ensure_ascii=False, indent=2)
        return json_path


def create_character_workshop_router(service: CharacterWorkshopService):
    router = APIRouter(prefix="/admin", tags=["character-workshop"])

    @router.get("/")
    async def admin_index():
        return RedirectResponse(url="/admin/characters")

    @router.get("/characters")
    async def list_characters(request: Request, success: Optional[str] = None):
        service.require_admin(request)
        try:
            characters = service.get_all_characters()
        except Exception:
            service.init_db()
            characters = service.get_all_characters()
        return service.templates.TemplateResponse(
            "characters.html",
            {
                "request": request,
                "characters": characters,
                "success": success
            }
        )

    @router.get("/characters/new")
    async def new_character(request: Request):
        service.require_admin(request)
        return service.templates.TemplateResponse("new_character.html", {"request": request})

    @router.post("/characters")
    async def create_character_route(request: Request):
        service.require_admin(request)
        form_data = await request.form()

        name = form_data.get("name")
        description = form_data.get("description")
        prompt = form_data.get("prompt")
        behavior_tags = form_data.get("behavior_tags")
        personality_tags = form_data.get("personality_tags")
        story_weight = form_data.get("story_weight", 5)
        personality_matrix = form_data.get("personality_matrix")
        inertia = form_data.get("inertia")

        if not name or not prompt:
            return service.templates.TemplateResponse(
                "new_character.html",
                {"request": request, "error": "角色名称和提示词为必填项！"}
            )

        if service.get_character_by_name(name):
            return service.templates.TemplateResponse(
                "new_character.html",
                {"request": request, "error": f'角色名 "{name}" 已存在！'}
            )

        safe_name = _safe_filename(name)

        avatar_file = form_data.get("avatar")
        avatar_path = None

        if avatar_file and hasattr(avatar_file, "filename") and avatar_file.filename:
            ext = os.path.splitext(avatar_file.filename)[1] or ".png"
            avatar_filename = f"{safe_name}_avatar{ext}"
            avatar_path = service.save_upload_to_chat_images(avatar_file, avatar_filename)

        expressions = {}
        for key, file_obj in form_data.items():
            if key.startswith("expressions_") and file_obj and hasattr(file_obj, "filename") and file_obj.filename:
                emotion = key.replace("expressions_", "")
                ext = os.path.splitext(file_obj.filename)[1] or ".png"
                filename = f"{safe_name}_{emotion}{ext}"
                image_path = service.save_upload_to_chat_images(file_obj, filename)
                expressions[emotion] = image_path

        try:
            matrix = json.loads(personality_matrix) if personality_matrix else None
        except Exception:
            matrix = None

        try:
            inertia_list = json.loads(inertia) if inertia else None
        except Exception:
            inertia_list = None

        try:
            behavior_list = json.loads(behavior_tags) if behavior_tags else None
        except Exception:
            behavior_list = None

        try:
            personality_list = json.loads(personality_tags) if personality_tags else None
        except Exception:
            personality_list = None

        attributes = {}
        if behavior_list:
            attributes["behavior_tags"] = behavior_list
        if personality_list:
            attributes["personality_tags"] = personality_list
        if story_weight:
            attributes["story_weight"] = int(story_weight)
        if avatar_path:
            attributes["avatar"] = avatar_path
        if expressions:
            attributes["expressions"] = expressions
        if matrix:
            attributes["personality_matrix"] = matrix
        if inertia_list:
            attributes["inertia"] = inertia_list

        service.create_character_record(name, description or "", prompt, attributes)

        character_json = service.build_character_json(
            name=name,
            prompt=prompt,
            matrix=matrix,
            inertia_list=inertia_list,
            avatar_path=avatar_path,
            expressions=expressions
        )
        service.write_character_json(name, character_json)

        return RedirectResponse(url="/admin/characters?success=created", status_code=303)

    @router.get("/characters/{name}/edit")
    async def edit_character(request: Request, name: str):
        service.require_admin(request)
        character = service.get_character_by_name(name)
        if not character:
            raise HTTPException(status_code=404, detail="角色不存在")
        return service.templates.TemplateResponse(
            "edit_character.html",
            {
                "request": request,
                "character": character
            }
        )

    @router.post("/characters/{old_name}/update")
    async def update_character(request: Request, old_name: str):
        service.require_admin(request)
        form = await request.form()

        new_name = form.get("new_name")
        description = form.get("description")
        prompt = form.get("prompt")
        story_weight = form.get("story_weight", 5)
        behavior_tags_json = form.get("behavior_tags")
        personality_tags_json = form.get("personality_tags")
        personality_matrix_json = form.get("personality_matrix")
        inertia_0 = form.get("inertia_0")
        inertia_1 = form.get("inertia_1")
        inertia_2 = form.get("inertia_2")

        if not new_name or not prompt:
            return RedirectResponse(
                url=f"/admin/characters/{old_name}/edit?error=名称和提示词不能为空",
                status_code=303
            )

        if new_name != old_name and service.get_character_by_name(new_name):
            return RedirectResponse(
                url=f"/admin/characters/{old_name}/edit?error=角色名 '{new_name}' 已存在",
                status_code=303
            )

        old_char = service.get_character_by_name(old_name)
        if not old_char:
            raise HTTPException(status_code=404, detail="原角色不存在")

        safe_new_name = _safe_filename(new_name)

        avatar_path = old_char.get("attributes", {}).get("avatar") if old_char else None
        expressions = old_char.get("attributes", {}).get("expressions", {}).copy()

        avatar_file = form.get("avatar")
        if avatar_file and hasattr(avatar_file, "filename") and avatar_file.filename:
            ext = os.path.splitext(avatar_file.filename)[1] or ".png"
            new_avatar_name = f"{safe_new_name}_avatar{ext}"
            avatar_path = service.save_upload_to_chat_images(avatar_file, new_avatar_name)

        for key, file_obj in form.items():
            if key.startswith("expressions_") and file_obj and hasattr(file_obj, "filename") and file_obj.filename:
                emotion = key.replace("expressions_", "")
                ext = os.path.splitext(file_obj.filename)[1] or ".png"
                new_file_name = f"{safe_new_name}_{emotion}{ext}"
                expressions[emotion] = service.save_upload_to_chat_images(file_obj, new_file_name)

        try:
            behavior_list = json.loads(behavior_tags_json) if behavior_tags_json else None
        except Exception:
            behavior_list = None

        try:
            personality_list = json.loads(personality_tags_json) if personality_tags_json else None
        except Exception:
            personality_list = None

        try:
            matrix = json.loads(personality_matrix_json) if personality_matrix_json else None
        except Exception:
            matrix = None

        try:
            inertia_list = [
                float(inertia_0 or 0.5),
                float(inertia_1 or 0.5),
                float(inertia_2 or 0.5)
            ]
        except Exception:
            inertia_list = [0.5, 0.5, 0.5]

        attributes = {}
        if behavior_list:
            attributes["behavior_tags"] = behavior_list
        if personality_list:
            attributes["personality_tags"] = personality_list
        if story_weight:
            attributes["story_weight"] = int(story_weight)
        if avatar_path:
            attributes["avatar"] = avatar_path
        if expressions:
            attributes["expressions"] = expressions
        if matrix:
            attributes["personality_matrix"] = matrix
        attributes["inertia"] = inertia_list

        conn = service.get_db()
        try:
            conn.execute(
                "UPDATE characters SET name = ?, description = ?, prompt = ?, attributes = ? WHERE name = ?",
                (
                    new_name,
                    description or "",
                    prompt,
                    json.dumps(attributes, ensure_ascii=False),
                    old_name
                )
            )
            conn.commit()
        except Exception as e:
            conn.close()
            return RedirectResponse(
                url=f"/admin/characters/{old_name}/edit?error=数据库更新失败: {str(e)}",
                status_code=303
            )
        conn.close()

        character_json = service.build_character_json(
            name=new_name,
            prompt=prompt,
            matrix=matrix,
            inertia_list=inertia_list,
            avatar_path=avatar_path,
            expressions=expressions
        )
        service.write_character_json(new_name, character_json)

        old_safe_name = _safe_filename(old_name)
        new_safe_name = _safe_filename(new_name)
        if old_safe_name != new_safe_name:
            old_json = os.path.join(service.chat_character_dir, f"{old_safe_name}.json")
            if os.path.exists(old_json):
                os.remove(old_json)

        return RedirectResponse(url="/admin/characters?success=updated", status_code=303)

    @router.post("/characters/{name}/delete")
    async def delete_character(request: Request, name: str):
        service.require_admin(request)

        try:
            conn = service.get_db()
            cursor = conn.execute("DELETE FROM characters WHERE name = ?", (name,))
            conn.commit()
            deleted = cursor.rowcount
            conn.close()

            if deleted == 0:
                raise HTTPException(status_code=404, detail="角色不存在")

            safe_name = _safe_filename(name)
            json_path = os.path.join(service.chat_character_dir, f"{safe_name}.json")
            if os.path.exists(json_path):
                os.remove(json_path)

            return {"message": "删除成功"}
        except HTTPException:
            raise
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    return router


def mount_character_workshop(app, auth_service, base_dir: str):
    service = CharacterWorkshopService(base_dir=base_dir, auth_service=auth_service)

    # 角色工坊自己的 CSS/JS 静态资源，避免和主聊天页 /static 冲突。
    if os.path.exists(service.static_dir):
        app.mount(
            "/character_static",
            StaticFiles(directory=service.static_dir),
            name="character_static"
        )

    app.include_router(create_character_workshop_router(service))
    return service