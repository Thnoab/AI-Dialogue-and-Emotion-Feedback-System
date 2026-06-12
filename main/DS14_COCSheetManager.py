import os
import json
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse


class COCSheetManagerService:
    """
    COC 七版角色卡管理模块。
    Python 只负责接口、权限、AI 生成、数据库读写；
    UI 页面放在 coc_sheet_manager.html，避免 Python 文件臃肿。
    """

    def __init__(self, auth_service, sheet_store):
        self.auth_service = auth_service
        self.sheet_store = sheet_store
        self.api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY") or ""
        self.base_url = (
            os.getenv("DEEPSEEK_API_BASE")
            or os.getenv("LLM_BASE_URL")
            or "https://api.deepseek.com/v1"
        ).rstrip("/")
        self.model = os.getenv("DEEPSEEK_MODEL") or os.getenv("LLM_MODEL") or "deepseek-chat"
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.html_path = os.getenv(
            "COC_SHEET_MANAGER_HTML_PATH",
            os.path.join(self.base_dir, "coc_sheet_manager.html")
        )

    def get_token_from_request(self, request: Request):
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

    def require_trpg_access_from_request(self, request: Request):
        token = self.get_token_from_request(request)
        if not token:
            return None
        user = self.auth_service.verificare(token)
        if not self.auth_service.can_use_trpg(user):
            raise HTTPException(status_code=403, detail="角色卡管理属于 VIP 跑团功能，请升级 VIP 后使用。")
        return user

    def load_page_html(self):
        if not os.path.exists(self.html_path):
            return (
                "<h1>缺少 coc_sheet_manager.html</h1>"
                "<p>请把 coc_sheet_manager.html 放到主程序目录，"
                "或设置 COC_SHEET_MANAGER_HTML_PATH 指向页面文件。</p>"
            )
        with open(self.html_path, "r", encoding="utf-8") as f:
            return f.read()

    def build_blank_skills(self, sheet_data: dict):
        """
        创建空白角色卡时使用真正的 COC 初始技能值。
        目的：
        - 新建空白卡时不触发 DS12_Sheet.py 里的职业/常用技能自动补正；
        - 保证急救=30、聆听=20、图书馆使用=20、心理学=10、侦查=25 等保持规则默认值；
        - 母语根据 EDU 计算；
        - 闪避根据 DEX / 2 计算。
        """
        stats = sheet_data.get("stats", sheet_data) or {}

        try:
            edu = int(stats.get("EDU", 50))
        except Exception:
            edu = 50

        try:
            dex = int(stats.get("DEX", 50))
        except Exception:
            dex = 50

        blank_skills = []

        for name, base in self.sheet_store.DEFAULT_SKILLS:
            value = int(base)

            if name == "母语":
                value = edu

            if name == "闪避":
                value = max(1, dex // 2)

            blank_skills.append({
                "name": name,
                "base_value": value,
                "value": value,
                "note": ""
            })

        return blank_skills

    def call_ai_generate_sheet(self, payload: dict):
        if not self.api_key:
            raise HTTPException(status_code=500, detail="缺少 DEEPSEEK_API_KEY 或 LLM_API_KEY，无法 AI 生成角色卡。")

        messages = [
            {
                "role": "system",
                "content": """
你是 COC 七版调查员角色卡生成器。你必须严格输出 JSON，不要输出解释、markdown 或代码块。

请根据用户提供的基础信息，生成一份适合 COC 七版的完整调查员角色卡。
硬性要求：
1. 必须输出完整 JSON 对象。
2. STR/DEX/POW/CON/APP/EDU/SIZ/INS/LUCK 取 1-100。
3. 技能 value 取 0-100。
4. 技能表至少给出 35 个技能。
5. 必须包含这些技能：
侦查、聆听、图书馆使用、心理学、闪避、格斗、射击、急救、话术、说服、信用评级、母语、克苏鲁神话、神秘学、历史、法律、医学、精神分析、潜行、导航。
6. 如果职业明显涉及语言、科学、驾驶、格斗、射击、学问、生存、艺术与手艺，可以添加细分技能，例如：
外语：英语、科学：化学、驾驶：汽车、射击：手枪、格斗：剑、学问：民俗学、艺术与手艺：写作。
7. 每个细分类别最多给 3 个。
8. 自定义技能最多给 3 个，并使用“自定义：技能名”的格式。

返回格式：
{
  "name":"姓名",
  "age":25,
  "gender":"性别",
  "occupation":"职业",
  "residence":"住地",
  "birthplace":"故乡",
  "stats":{"STR":50,"DEX":50,"POW":50,"CON":50,"APP":50,"EDU":50,"SIZ":50,"INS":50},
  "luck":50,
  "credit_rating":20,
  "background":"简短背景",
  "personal_description":"外貌描述",
  "ideology":"信念/思想",
  "important_people":"重要之人",
  "meaningful_locations":"重要地点",
  "treasured_possessions":"宝贵物品",
  "traits":"特质",
  "injuries":"伤口/伤疤",
  "phobias":"恐惧症/狂躁症",
  "spells":"法术",
  "possessions":"携带物品",
  "cash_assets":"现金与资产",
  "notes":"备注",
  "skills":[
    {"name":"侦查","base_value":25,"value":60,"note":""},
    {"name":"外语：英语","base_value":1,"value":45,"note":""}
  ]
}
"""
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        ]

        response = requests.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.75,
                "max_tokens": 3200,
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=90,
        )
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"AI 生成角色卡失败：{response.text[:300]}")

        content = response.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines).strip()

        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or start > end:
            raise HTTPException(status_code=500, detail="AI 返回中没有找到 JSON 对象。")
        try:
            return json.loads(content[start:end + 1])
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=500, detail=f"AI 返回 JSON 解析失败：{str(exc)}")


def create_coc_sheet_manager_router(service: COCSheetManagerService):
    router = APIRouter(tags=["trpg-coc-sheet-manager"])

    @router.get("/trpg/sheets")
    def serve_coc_sheet_manager(request: Request, session_id: str = Query(default="")):
        user = service.require_trpg_access_from_request(request)
        if user is None:
            return RedirectResponse(url="/profile")
        return HTMLResponse(service.load_page_html())

    @router.get("/api/trpg/sheets")
    def get_trpg_sheets(session_id: str, user: dict = Depends(service.auth_service.get_current_user)):
        if not service.auth_service.can_use_trpg(user):
            raise HTTPException(status_code=403, detail="角色卡管理属于 VIP 跑团功能，请升级 VIP 后使用。")
        try:
            sheets = service.sheet_store.list_sheets(session_id)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"角色卡读取失败：{str(exc)}")
        return {"session_id": session_id, "count": len(sheets), "sheets": sheets}

    @router.post("/api/trpg/sheets/generate")
    def generate_trpg_sheet(data: dict, user: dict = Depends(service.auth_service.get_current_user)):
        if not service.auth_service.can_use_trpg(user):
            raise HTTPException(status_code=403, detail="角色卡管理属于 VIP 跑团功能，请升级 VIP 后使用。")
        session_id = data.get("session_id")
        owner_id = data.get("owner_id") or "user"
        if not session_id:
            raise HTTPException(status_code=400, detail="缺少 session_id。")
        generated = service.call_ai_generate_sheet(data)
        generated["name"] = generated.get("name") or data.get("name") or "未命名调查员"
        generated["age"] = generated.get("age") or data.get("age") or 25
        generated["gender"] = generated.get("gender") or data.get("gender") or "未知"
        generated["occupation"] = generated.get("occupation") or data.get("occupation") or ""
        try:
            sheet = service.sheet_store.create_full_sheet(session_id=session_id, owner_id=owner_id, data=generated)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"角色卡保存失败：{str(exc)}")
        return {"status": "success", "sheet": sheet, "generated": generated}

    @router.post("/api/trpg/sheets/create_blank")
    def create_blank_sheet(data: dict, user: dict = Depends(service.auth_service.get_current_user)):
        if not service.auth_service.can_use_trpg(user):
            raise HTTPException(status_code=403, detail="角色卡管理属于 VIP 跑团功能，请升级 VIP 后使用。")

        session_id = data.get("session_id")
        owner_id = data.get("owner_id") or "user"
        sheet_data = data.get("sheet") or {}

        if not session_id:
            raise HTTPException(status_code=400, detail="缺少 session_id。")

        # 关键修正：
        # 空白角色卡必须使用 COC 默认初始技能值，不触发职业/常用技能自动补正。
        # 如果不传 skills，DS12_Sheet.init_default_skills 会把常用技能自动提高，
        # 例如急救 30 -> 40、聆听 20 -> 45，这不是空白卡应有的行为。
        if not sheet_data.get("skills"):
            sheet_data["skills"] = service.build_blank_skills(sheet_data)

        try:
            sheet = service.sheet_store.create_full_sheet(
                session_id=session_id,
                owner_id=owner_id,
                data=sheet_data
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"空白角色卡创建失败：{str(exc)}")

        return {
            "status": "success",
            "sheet": sheet
        }

    @router.post("/api/trpg/sheets/update")
    def update_trpg_sheet(data: dict, user: dict = Depends(service.auth_service.get_current_user)):
        if not service.auth_service.can_use_trpg(user):
            raise HTTPException(status_code=403, detail="角色卡管理属于 VIP 跑团功能，请升级 VIP 后使用。")
        session_id = data.get("session_id")
        local_id = data.get("local_id")
        sheet_data = data.get("sheet") or {}
        if not session_id or local_id is None:
            raise HTTPException(status_code=400, detail="缺少 session_id 或 local_id。")
        try:
            sheet = service.sheet_store.update_full_sheet(session_id=session_id, local_id=int(local_id), data=sheet_data)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"角色卡保存失败：{str(exc)}")
        return {"status": "success", "sheet": sheet}

    @router.post("/api/trpg/sheets/delete")
    def delete_trpg_sheet(data: dict, user: dict = Depends(service.auth_service.get_current_user)):
        if not service.auth_service.can_use_trpg(user):
            raise HTTPException(status_code=403, detail="角色卡管理属于 VIP 跑团功能，请升级 VIP 后使用。")
        session_id = data.get("session_id")
        local_id = data.get("local_id")
        if not session_id or local_id is None:
            raise HTTPException(status_code=400, detail="缺少 session_id 或 local_id。")
        try:
            deleted = service.sheet_store.delete_sheet(session_id, int(local_id))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"角色卡删除失败：{str(exc)}")
        return {"status": "success", "deleted": deleted}

    return router


def mount_coc_sheet_manager(app, auth_service, sheet_store):
    service = COCSheetManagerService(auth_service=auth_service, sheet_store=sheet_store)
    app.include_router(create_coc_sheet_manager_router(service))
    return service
