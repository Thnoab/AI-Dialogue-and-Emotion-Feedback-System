import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from DS11_Memo import Memorize  # 新增
import json  # 新增
from DS4_Emo import Calculator # DS3 新增
from fastapi.staticfiles import StaticFiles # DS3 新增
from DS5_Circl import Circulation # DS5 新增
from DS7_Chara import Detection # DS6 新增
from DS10_Roll import DiceRoller # DS9 新增
from DS12_Sheet import TrpgSheetStore, SheetCommandError # DS12 新增

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

if not API_KEY:
    raise RuntimeError("未找到 DeepSeek API Key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # DS6 新增

# ----------------------------------------------------------
# DS13 新增，用于读取用户个人文件的json文件
USER_PROFILE_DIR = os.getenv(
    "USER_PROFILE_DIR",
    os.path.abspath(
        os.path.join(
            BASE_DIR,
            "..",
            "别人的",
            "2026.5.1",
            "2026.5.3",
            "player_cards"
        )
    )
)
DEFAULT_USERNAME = os.getenv("DEFAULT_USERNAME", "test")
def get_user_profile_path(username=DEFAULT_USERNAME):
    return os.path.join(USER_PROFILE_DIR, f"{username}_profile.json")
# ----------------------------------------------------------

app = FastAPI()
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static"
)  # DS6 修改

# ----------------------------------------------------------
# DS11 新增，用于debug
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.body()
        print("请求验证失败 URL =", request.url)
        print("请求验证失败 body =", body.decode("utf-8"))
        print("请求验证失败 errors =", exc.errors())
    except Exception as e:
        print("读取验证失败请求体时出错 =", repr(e))

    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors()
        }
    )
# ----------------------------------------------------------

memo = Memorize()

group_circulations = {}

chara = Detection(os.path.join(BASE_DIR, "characters"))

dice = DiceRoller()

sheet = TrpgSheetStore()

# ----------------------------------------------------------
# DS13 新增
def load_user_profile(username=DEFAULT_USERNAME):
    """
    读取当前用户档案 JSON。
    当前演示版本默认读取 DEFAULT_USERNAME 对应的用户档案。
    """
    profile_path = get_user_profile_path(username)
    if not os.path.exists(profile_path):
        return {
            "username": username,
            "level": 1,
            "is_vip": 0,
            "status": "active",
            "settings": {
                "hide_trpg_guide": False
            }
        }
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile = json.load(f)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="用户档案 JSON 格式错误")
    if "settings" not in profile or not isinstance(profile["settings"], dict):
        profile["settings"] = {}
    if "hide_trpg_guide" not in profile["settings"]:
        profile["settings"]["hide_trpg_guide"] = False
    return profile

def save_user_profile(profile):
    """
    保存当前用户档案 JSON。
    会保留原有字段，只新增/修改 settings.hide_trpg_guide。
    """
    username = profile.get("username", DEFAULT_USERNAME)
    profile_path = get_user_profile_path(username)
    os.makedirs(os.path.dirname(profile_path), exist_ok=True)
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=4)

# ----------------------------------------------------------
# DS6 新增：多人模式公共群聊历史
# 用来保存用户和多个AI在群聊中最近说过的话
group_context_history = {}

def add_group_context(session_id, speaker, content):
    """
    保存指定 session 的多人模式公共群聊上下文。
    session_id: 当前群聊/房间/会话 ID
    speaker: 说话者名称，例如 "用户"、"芙罗拉"
    content: 发言内容
    """
    global group_context_history
    if session_id not in group_context_history:
        group_context_history[session_id] = []
    group_context_history[session_id].append({
        "speaker": speaker,
        "content": content
    })
    # 每个 session 只保留最近20条
    if len(group_context_history[session_id]) > 20:
        group_context_history[session_id] = group_context_history[session_id][-20:]


def ordinatus(session_id):
    """
    把指定 session 的公共群聊历史整理成 prompt 文本。
    """
    if session_id not in group_context_history:
        return "暂无群聊历史。"
    if not group_context_history[session_id]:
        return "暂无群聊历史。"
    text = ""
    for item in group_context_history[session_id]:
        text += f'{item["speaker"]}：{item["content"]}\n'
    return text

# ----------------------------------------------------------
# DS8 新增：跑团模式公共群聊历史
trpg_context_history = {}
trpg_circulations = {}

def add_trpg_context(session_id, speaker, content):
    global trpg_context_history
    if session_id not in trpg_context_history:
        trpg_context_history[session_id] = []
    trpg_context_history[session_id].append({
        "speaker": speaker,
        "content": content
    })
    # 跑团上下文可以比普通多人更长一点
    if len(trpg_context_history[session_id]) > 50:
        trpg_context_history[session_id] = trpg_context_history[session_id][-50:]

def ordinati(session_id):
    if session_id not in trpg_context_history:
        return "暂无跑团上下文。"
    if not trpg_context_history[session_id]:
        return "暂无跑团上下文。"
    text = ""
    for item in trpg_context_history[session_id]:
        text += f'{item["speaker"]}：{item["content"]}\n'
    return text

# ----------------------------------------------------------
# ---------- 调用人物卡 ----------
# ---------- 统一调用人物卡：单人模式与多人模式共用 ----------
def appel(character_id):
    try:
        return chara.elige(character_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
# ----------------------------------------------------------
# DS8 新增
def parse_model_json(content, name="模型"):
    """
    清洗并解析模型返回的 JSON。
    兼容 ```json ... ``` 代码块。
    """
    cleaned = content.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or start > end:
        raise HTTPException(
            status_code=500,
            detail=f"{name}返回中未找到JSON对象: {cleaned[:200]}"
        )
    json_text = cleaned[start:end + 1]
    try:
        return json.loads(json_text)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail=f"{name}返回的JSON无法解析: {json_text[:200]}"
        )
    
def format_trpg_memory(memory_pack):
    """
    把 memo.rappeler() 返回的跑团记忆包整理成 prompt 文本。
    这些文本将会一同投入ai对话。
    """
    relevant_lines = []
    for item in memory_pack.get("relevant_memory", []):
        summary = item.get("summary", "")
        motto = item.get("motto", "")
        if summary or motto:
            relevant_lines.append(f"- {summary} / {motto}")
    relevant_text = "\n".join(relevant_lines) if relevant_lines else "暂无相关旧记忆。"
    return f"""
    【固定设定记忆】
    {memory_pack.get("fixed_memory", "") or "暂无固定设定。"}
    【相关旧记忆】
    {relevant_text}
    【最近完整记忆：用户输入】
    {memory_pack.get("recent_submit", [])}
    【最近完整记忆：AI回复】
    {memory_pack.get("recent_reply", [])}
    【较早缩略记忆：用户摘要】
    {memory_pack.get("old_summary", [])}
    【较早缩略记忆：AI摘要】
    {memory_pack.get("old_motto", [])}
    """
# ---------- 前端静态页面 ----------
@app.get("/")
async def serve_frontend():
    """返回 index.html 文件"""
    return FileResponse(os.path.join(BASE_DIR, "index_DS13.html"))

# ---------- API 接口 ----------
class ChatRequest(BaseModel):
    message: str
    character_id: str
    session_id: str
    system_prompt: Optional[str] = "你必须严格输出JSON格式，不允许输出任何额外文字。"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000

class ChatResponse(BaseModel):
    reply: str
    expression: str
    expression_image: str
    character_id: str
    name: str

# ---------- DS6 新增清空指定session历史 ----------
class GroupResetRequest(BaseModel):
    session_id: str

# ---------- DS5 新增多人付费模式 API 接口 ----------
class GroupChatRequest(BaseModel):
    message: str
    session_id: str
    active_characters: list[str]
    system_prompt: Optional[str] = "你必须严格输出JSON格式，不允许输出任何额外文字。"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000

class GroupCharacterReply(BaseModel):
    character_id: str
    name: str
    reply: str
    expression: str
    expression_image: str = ""

class GroupChatResponse(BaseModel):
    replies: list[GroupCharacterReply]

# ---------- DS8 新增多人TRPG模式 API 接口 ----------
class TrpgChatRequest(BaseModel):
    message: str
    session_id: str
    active_characters: list[str]
    fixed_memory: Optional[str] = ""
    dice_rule: Optional[str] = "common"
    dice_rule_config: Optional[dict] = None
    system_prompt: Optional[str] = "你必须严格输出JSON格式，不允许输出任何额外文字。"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1200

# ---------- DS9 新增多人TRPG模式骰娘接口 ----------
class DiceRollRequest(BaseModel):
    command: str
    rule: Optional[str] = "common"
    rule_config: Optional[dict] = None
    session_id: Optional[str] = None

class DiceRollResponse(BaseModel):
    rule: str
    command: str
    type: str
    expression: str
    terms: list
    rolls: list
    total: int
    text: str

# ---------- DS11 新增多人TRPG模式清空接口 ----------
class ConversationDeleteRequest(BaseModel):
    session_id: str
    mode: str

# ---------- DS13 新增读取用户json文件接口 ----------
class TrpgGuideSettingRequest(BaseModel):
    hide_trpg_guide: bool

# ----------------------------------------------------------
# DS8 新增，用ai来先提取关键词
def extract_trpg_keywords(req: TrpgChatRequest):
    """
    跑团模式第一阶段：
    先让 AI 根据当前输入、固定设定和跑团上下文提取关键词。
    """
    url = f"{BASE_URL}/chat/completions"
    trpg_context_text = ordinati(req.session_id)
    messages = [
        {
            "role": "system",
            "content": """
        你是跑团模式的关键词提取器。
        你只负责从当前输入和上下文中提取关键词，用于长期记忆检索。
        你必须严格返回 JSON，不允许输出任何额外文字。
        """
        },
        {
            "role": "user",
            "content": f"""
        【固定设定】
        {req.fixed_memory or "暂无固定设定。"}
        【当前跑团上下文】
        {trpg_context_text}
        【当前用户输入】
        {req.message}
        请提取 3 到 10 个关键词。
        关键词优先包含：
        人物、地点、组织、道具、线索、任务、事件、怪物、阵营、特殊名词。
        返回格式必须是：
        {{
        "keywords": ["关键词1", "关键词2", "关键词3"]
        }}
        """
        }
    ]
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 300
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"跑团关键词提取失败: {response.text[:100]}"
        )
    data = response.json()
    content = data["choices"][0]["message"]["content"].strip()
    print("跑团关键词提取 content =", content)
    result = parse_model_json(content, "跑团关键词提取器")
    keywords = result.get("keywords", [])
    if not isinstance(keywords, list):
        keywords = []
    clean_keywords = []
    for kw in keywords:
        if isinstance(kw, str):
            kw = kw.strip()
            if kw:
                clean_keywords.append(kw)
    clean_keywords = list(dict.fromkeys(clean_keywords))[:10]
    print("跑团关键词 =", clean_keywords)
    return clean_keywords

# ----------------------------------------------------------
# DS9 新增，从ai回复获得骰子指令
def extract_dice_commands(text):
    """
    从 AI 回复中提取骰子指令。
    只识别单独一行以 @Dice 开头的内容。
    这样可以避免把“请使用 @Dice r1d6”这种提示误当成真正执行指令。
    """
    commands = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("@Dice "):
            commands.append(line)
    return commands
# ----------------------------------------------------------
# DS12 新增，处理新加的数值的指令
def solvendo(command, session_id, owner_id="user", rule="common", rule_config=None):
    """
    统一处理跑团 @Dice 指令。
    优先交给角色卡系统处理：
    @Dice card add ...
    @Dice 1 hp -3
    @Dice 2 san -5
    @Dice check 1 STR
    @Dice sheet 1
    @Dice cards
    如果不是角色卡指令，再交给普通骰子系统处理：
    @Dice r1d6
    @Dice ra斗殴 60
    """
    if rule_config is None:
        rule_config = {}
    try:
        sheet_result = sheet.handle_command(
            session_id=session_id,
            full_command=command,
            owner_id=owner_id,
            rule_config=rule_config or {}
        )
        if sheet_result is not None:
            return sheet_result
    except SheetCommandError:
        raise
    except Exception as e:
        raise SheetCommandError(f"角色卡指令执行失败：{str(e)}")
    return dice.roll(
        command=command,
        rule=rule or "common",
        rule_config=rule_config or {}
    )
# ----------------------------------------------------------

@app.post("/chat", response_model=ChatResponse)
def chat_with_deepseek(req: ChatRequest):
    url = f"{BASE_URL}/chat/completions"
    character_card = appel(req.character_id)
    character_name = character_card.get("name", req.character_id)
    character_prompt = character_card.get("prompt", "")
    messages = []
    messages.append({
    "role": "system",
    "content": f"""
    {req.system_prompt}
    你正在以以下角色身份与用户对话：
    角色名：{character_name}
    你只能代表该角色发言，不要替用户说话。
    你的回复中不要写“{character_name}：”这种名字前缀。
    {character_prompt}
    """
    })
    # ----------------------------------------------------------
    # DS3 新增
    # 这里是把过去的历史内容合并的代码
    memoria = memo.rappelez(req.session_id, req.character_id, 5)
    if memoria.get("status") == "empty":
        memory = "暂无历史对话。"
    else:
        memory = f"""
    最近用户输入：
    {memoria["recent_submit"]}
    最近AI回复：
    {memoria["recent_reply"]}
    较早的用户摘要：
    {memoria["old_summary"]}
    较早的AI摘要：
    {memoria["old_motto"]}
    """
    # ----------------------------------------------------------
    messages.append({"role": "user", "content": f"""
    用户输入:
    {req.message}
    你还需要参考你与用户的历史交互内容：
    {memory}
    并且，请一同完成以下任务，并返回 JSON：
    1. reply：正常回复用户
    2. abr1：对用户输入的简要概括
    3. abr2：对AI回复的简要概括
    4. emotion：一个长度为3的情绪向量 [glee, buzz, stance]，
    每一项取值范围为 -1 到 1，即emotion 的每一个值都必须满足：-1 <= value <= 1。
    如果该情绪不存在，则为 0。
    禁止输出小于 -1 或大于 1 的数值。
    禁止输出字符串、解释、百分比或其他格式。
    emotion 示例：[0.2, 0.7, -0.4]
    细致一些，遵循以下：
    1. Glee (Pleasure/Valence)：“甜度”轴
    定义：衡量情感的正负向，即“主观体验是否愉悦”。
    低 Glee (负值)：痛苦、厌恶、悲伤、不满。语义通常指向“失去”、“受损”或“排斥”。
    高 Glee (正值)：快乐、满足、爱慕、欣慰。语义通常指向“获得”、“和谐”或“趋近”。
    判定标准：这件事对“我”来说是好事还是坏事？
    2. Buzz (Arousal)：“烈度”轴
    定义：衡量生理唤醒度或精神能量的活跃水平。
    低 Buzz (静息)：冷淡、疲惫、平静、抑郁。语义表现为：语速慢、字数少、情感波动小。
    高 Buzz (亢奋)：激动、狂热、惊恐、愤怒。语义表现为：叹词多、语气词强烈、逻辑跳跃、生理反应描述多。
    判定标准：情绪的火焰是快要熄灭了，还是正在熊熊燃烧？
    3. Power (Dominance/Stance)：“力度”轴
    定义：衡量个体对环境的控制感与心理优势。这是区分攻击性情绪与受挫性情绪的关键。
    低 Power (被动/弱势)：委屈、无助、恐惧、愧疚、痛哭流涕。
    AI 逻辑：此时个体是“承受者”，能量向内收缩，表现为退缩、求助或放弃。
    高 Power (主动/强势)：自信、轻蔑、傲慢、勃然大怒。
    AI 逻辑：此时个体是“支配者”，能量向外扩张，表现为攻击、批判、命令或保护。
    判定标准：我是这个局面的主人，还是这个局面的牺牲品？
    同理，你应该依照上面的要求和例子，在emotion处分别给出glee,buzz,stance三项数值。
    """})
    
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": req.temperature,
        "max_tokens": req.max_tokens
    }
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"API调用失败: {response.text[:100]}")
        data = response.json()
        content = data["choices"][0]["message"]["content"].strip()
        print("content =", content)
        # ----------------------------------------------------------
        cleaned = content.strip()
        # 如果有代码块标记，先粗清洗
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        # 再提取最外层 JSON 对象
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or start > end:
            raise HTTPException(
                status_code=500,
                detail=f"模型返回中未找到JSON对象: {cleaned[:200]}"
            )
        json_text = cleaned[start:end + 1]
        try:
            result = json.loads(json_text)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=500,
                detail=f"模型返回的JSON仍然无法解析: {json_text[:200]}"
            )

        print("JSON解析完成")
        reply = result["reply"]
        abr1 = result["abr1"]
        abr2 = result["abr2"]
        emt = result["emotion"]
        emotion = json.dumps(emt, ensure_ascii=False)
        # ----------------------------------------------------------
        # DS3 与 DS4 新增内容
        histext = memo.quote(req.session_id, req.character_id)
        if histext is None:
            old = [0, 0, 0]
        else:
            old = json.loads(histext)
        personality = character_card["personality_matrix"]
        inertia = character_card["inertia"]
        emoca = Calculator(emt,old,personality,inertia)
        history = emoca.calculate()
        historia = json.dumps(history.tolist(), ensure_ascii=False)
        history_list = history.tolist()
        expression = emoca.dikastis(old, emt, history_list)
        # ----------------------------------------------------------
        # DS7 新增内容
        expressions = character_card.get("expressions", {})
        default_expression = character_card.get("default_expression", "neutral")
        expression_image = expressions.get(
            expression,
            expressions.get(default_expression, character_card.get("default_image", ""))
        )
        # ----------------------------------------------------------
        print("准备写入数据库")
        memo.request(req.session_id, req.character_id, req.message, abr1, reply, abr2, emotion, historia)
        print("数据库写入完成")
        # ----------------------------------------------------------
        return ChatResponse(
        reply=reply,
        expression=expression,
        expression_image=expression_image,
        character_id=req.character_id,
        name=character_name
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="请求超时")
    except Exception as e:
        print("后端异常 =", repr(e))
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")
    
# --------------------------- DS6 新增 -------------------------------
# 获取所有人物卡
@app.get("/characters")
def get_characters():
    return {
        "characters": chara.list_character_cards()
    }

# --------------------------- DS13 新增 -------------------------------
# 获取用户json
@app.get("/user/profile")
def get_user_profile():
    """
    获取当前用户档案。
    前端会读取 profile.settings.hide_trpg_guide，
    判断是否需要显示跑团模式首次引导。
    """
    profile = load_user_profile()
    return {
        "profile": profile
    }


@app.post("/user/profile/trpg-guide")
def update_trpg_guide_setting(req: TrpgGuideSettingRequest):
    """
    更新跑团模式首次引导是否隐藏。
    写入用户 JSON 的 settings.hide_trpg_guide 字段。
    """
    profile = load_user_profile()
    if "settings" not in profile or not isinstance(profile["settings"], dict):
        profile["settings"] = {}
    profile["settings"]["hide_trpg_guide"] = req.hide_trpg_guide
    save_user_profile(profile)
    return {
        "status": "success",
        "hide_trpg_guide": profile["settings"]["hide_trpg_guide"]
    }

# --------------------------- DS5 新增 -------------------------------
# 多人ai对话
@app.post("/group_chat", response_model=GroupChatResponse)
def group_chat(req: GroupChatRequest):
    global group_circulations
    url = f"{BASE_URL}/chat/completions"
    if len(req.active_characters) < 1:
        raise HTTPException(status_code=400, detail="至少需要选择1个AI角色")
    if len(req.active_characters) > 3:
        raise HTTPException(status_code=400, detail="最多只能选择3个AI角色")
    if (
        req.session_id not in group_circulations
        or group_circulations[req.session_id].active_characters != req.active_characters
    ):
        group_circulations[req.session_id] = Circulation(req.active_characters)
    speaker_order = group_circulations[req.session_id].get_and_advance()
    replies = []
    add_group_context(req.session_id, "用户", req.message)
    for character_id in speaker_order:
        character_card_group = appel(character_id)
        character_name = character_card_group.get("name", character_id)
        character_prompt = character_card_group.get("prompt", "")
        messages = []
        messages.append({
            "role": "system",
            "content": f"""
        {req.system_prompt}
        你正在一个多人群聊中。
        你的身份是：{character_name}。
        你只能代表你自己发言。
        你不能替用户或其他AI角色发言。
        你的回复中不要写“{character_name}：”这种名字前缀。
        群聊上下文中包含你自己和其他人的历史发言，请参考上下文，但不要重复自己已经说过的话。
        {character_prompt}
        """
        })
        group_context_text = ordinatus(req.session_id)

        memoria = memo.rappellent(req.session_id, character_id, 5)
        if memoria.get("status") == "empty":
            memory = "暂无历史对话。"
        else:
            memory = f"""
        最近用户输入：
        {memoria["recent_submit"]}
        最近AI回复：
        {memoria["recent_reply"]}
        较早的用户摘要：
        {memoria["old_summary"]}
        较早的AI摘要：
        {memoria["old_motto"]}
        """
        messages.append({
            "role": "user",
            "content": f"""
        【当前群聊上下文】
        {group_context_text}
        【你与用户的历史交互内容】
        {memory}
        请你以“{character_name}”的身份回应当前群聊。
        你只能输出你自己的回复，不要替其他角色说话。
        并且，请一同完成以下任务，并返回 JSON：
        1. reply：正常回复用户或群聊
        2. abr1：对用户最新输入的简要概括
        3. abr2：对你本次回复的简要概括
        4. emotion：一个长度为3的情绪向量 [glee, buzz, stance]。
        emotion 的每一个值都必须满足：-1 <= value <= 1。
        如果该情绪不存在，则为 0。
        禁止输出小于 -1 或大于 1 的数值。
        禁止输出字符串、解释、百分比或其他格式。
        emotion 示例：[0.2, 0.7, -0.4]
        情绪轴说明：
        1. Glee：情感正负向。高为快乐、满足、亲近；低为悲伤、不满、厌恶。
        2. Buzz：唤醒度。高为激动、兴奋、愤怒、惊恐；低为平静、冷淡、疲惫。
        3. Stance：控制感与心理优势。高为主动、自信、强势；低为委屈、无助、退缩。
        """
        })
        payload = {
            "model": MODEL,
            "messages": messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens
        }
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"{character_name} API调用失败: {response.text[:100]}"
                )
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            print(f"{character_name} content =", content)
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or start > end:
                raise HTTPException(
                    status_code=500,
                    detail=f"{character_name} 模型返回中未找到JSON对象: {cleaned[:200]}"
                )
            json_text = cleaned[start:end + 1]
            try:
                result = json.loads(json_text)
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail=f"{character_name} 模型返回的JSON仍然无法解析: {json_text[:200]}"
                )
            reply = result["reply"]
            abr1 = result["abr1"]
            abr2 = result["abr2"]
            emt = result["emotion"]
            emotion = json.dumps(emt, ensure_ascii=False)
            histext = memo.quote_multi(req.session_id, character_id)
            if histext is None:
                old = [0, 0, 0]
            else:
                old = json.loads(histext)
            personality = character_card_group["personality_matrix"]
            inertia = character_card_group["inertia"]
            emoca = Calculator(emt, old, personality, inertia)
            history = emoca.calculate()
            history_list = history.tolist()
            historia = json.dumps(history_list, ensure_ascii=False)
            expression = emoca.dikastis(old, emt, history_list)
            memo.request_multi(req.session_id, character_id, req.message, abr1, reply, abr2, emotion, historia)
            add_group_context(req.session_id, character_name, reply)
            replies.append(GroupCharacterReply(
                character_id=character_id,
                name=character_name,
                reply=reply,
                expression=expression
            ))
        except requests.exceptions.Timeout:
            raise HTTPException(status_code=504, detail=f"{character_name} 请求超时")
        except Exception as e:
            print(f"{character_name} 后端异常 =", repr(e))
            raise HTTPException(status_code=500, detail=f"{character_name} 服务器错误: {str(e)}")
    return GroupChatResponse(replies=replies)

@app.post("/trpg_chat", response_model=GroupChatResponse)
def trpg_chat(req: TrpgChatRequest):
    global trpg_circulations
    url = f"{BASE_URL}/chat/completions"
    if len(req.active_characters) < 1:
        raise HTTPException(status_code=400, detail="至少需要选择1个AI角色")
    if len(req.active_characters) > 3:
        raise HTTPException(status_code=400, detail="最多只能选择3个AI角色")
    if (
        req.session_id not in trpg_circulations
        or trpg_circulations[req.session_id].active_characters != req.active_characters
    ):
        trpg_circulations[req.session_id] = Circulation(req.active_characters)
    speaker_order = trpg_circulations[req.session_id].get_and_advance()
    # 第一阶段：先提取关键词
    current_keywords = extract_trpg_keywords(req)
    replies = []
    add_trpg_context(req.session_id, "用户", req.message)
    for character_id in speaker_order:
        character_card_group = appel(character_id)
        character_name = character_card_group.get("name", character_id)
        character_prompt = character_card_group.get("prompt", "")

        trpg_context_text = ordinati(req.session_id)
        character_sheet_text = sheet.format_all_for_prompt(req.session_id)

        # 第二阶段：用关键词召回跑团记忆
        memory_pack = memo.rappeler(
            session_id=req.session_id,
            character_id=character_id,
            current_keywords=current_keywords,
            fixed_memory=req.fixed_memory,
            n=25,
            total=65,
            relevant_limit=5
        )
        memory_text = format_trpg_memory(memory_pack)
        messages = []
        messages.append({
            "role": "system",
            "content": f"""
        {req.system_prompt}
        你正在跑团模式中发言。
        你的身份是：{character_name}。
        你只能代表你自己发言。
        你不能替用户或其他AI角色发言。
        你的回复中不要写“{character_name}：”这种名字前缀。
        你需要遵守跑团叙事逻辑：
        1. 不要替玩家做决定。
        2. 不要无故跳过调查、行动、检定、交流等过程。
        3. 如果你是NPC，应只根据自己知道的信息发言。
        4. 如果你像主持人一样描述场景，应保持清晰、具体、有氛围。
        5. 参考固定设定、相关旧记忆、最近记忆和当前上下文，保持剧情连续。
        【骰子指令规则】
        如果你需要自己进行掷骰或判定，你可以在 reply 中单独输出一行骰子指令。
        格式必须是：
        @Dice r1d6
        @Dice r1d20+5
        @Dice r1d6+2d4
        要求：
        1. @Dice 指令必须单独占一行。
        2. 不要伪造骰子结果。
        3. 你只负责发出骰子指令，真实骰子结果由系统生成。
        4. 如果你希望用户亲自掷骰，请明确告诉用户需要输入什么指令，而不要自己输出独立的 @Dice 行。
        如果你需要进行 COC 式技能检定，可以使用：
        @Dice ra技能名 数值
        例如：
        @Dice ra斗殴 60
        @Dice ra侦查 45
        其中的数值为你的人物当前的数值。
        该指令会由系统投 1d100，并根据当前骰子规则判断是否通过。
        如果当前规则启用了大成功/大失败，则系统会自动判断 1-5 为大成功、96-100 为大失败。
        角色卡录入：
        @Dice card add 角色名 年龄 性别 STR DEX POW CON APP EDU SIZ INS
        例如：
        @Dice card add 约翰 35 男 60 55 70 50 40 65 60 70
        角色状态修改：
        @Dice 1 hp -3 即要求角色id=1的角色血量减少3
        @Dice 2 san -5 即要求角色id=2的角色理智减少5
        角色数值查询：
        @Dice check 1 STR 即查询角色id=1的力量的数值
        @Dice check 1 HP 即查询角色id=1的血量的数值
        @Dice sheet 1
        @Dice cards
        绑定角色自动检定：
        当你已经在本局创建并绑定了自己的角色卡后，可以直接使用属性名进行检定：
        @Dice ra力量
        @Dice raSTR
        @Dice ra敏捷
        @Dice raDEX
        @Dice ra意志
        @Dice raPOW
        系统会自动读取你当前绑定角色卡中的对应数值，并投 1d100 进行检定。
        用户也可以使用同样格式，系统会读取用户绑定的角色卡。
        注意：
        1. 如果你是 AI，直接属性检定会使用你自己绑定的角色卡。
        2. 如果你是用户，直接属性检定会使用用户绑定的角色卡。
        3. HP、SAN、MOV 用这种格式时只查询当前状态，不作为普通检定。
        【角色设定】
        {character_prompt}
        """
        })
        messages.append({
            "role": "user",
            "content": f"""
        【跑团专属记忆】
        {memory_text}
        【当前跑团上下文】
        {trpg_context_text}
        【本局角色卡实时数据】
        {character_sheet_text}
        【本轮检索关键词】
        {current_keywords}
        请你以“{character_name}”的身份回应当前跑团场景。
        你必须返回合法 JSON，格式如下：
        {{
        "reply": "你的回复",
        "abr1": "对用户最新输入的简要概括",
        "abr2": "对你本次回复的简要概括",
        "emotion": [0.0, 0.0, 0.0],
        "keywords": ["关键词1", "关键词2", "关键词3"]
        }}
        字段要求：
        1. reply：正常回复当前跑团场景。
        2. abr1：对用户最新输入的简要概括。
        3. abr2：对你本次回复的简要概括。
        4. emotion：长度为3的情绪向量 [glee, buzz, stance]。
        每一项必须满足 -1 <= value <= 1。
        禁止字符串、解释、百分比或其他格式。
        5. keywords：从当前用户输入、当前上下文和你的回复中提取 3 到 8 个关键词。
        优先包含人物、地点、组织、道具、线索、任务、事件。
        """
        })
        payload = {
            "model": MODEL,
            "messages": messages,
            "temperature": req.temperature,
            "max_tokens": req.max_tokens
        }
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"{character_name} 跑团API调用失败: {response.text[:100]}"
                )
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            print(f"{character_name} 跑团 content =", content)
            result = parse_model_json(content, f"{character_name} 跑团模型")
            reply = result["reply"]
            abr1 = result["abr1"]
            abr2 = result["abr2"]
            emt = result["emotion"]
            # 合并第一阶段关键词 + 正式回复关键词
            reply_keywords = result.get("keywords", [])
            if not isinstance(reply_keywords, list):
                reply_keywords = []
            merged_keywords = []
            for kw in current_keywords + reply_keywords:
                if isinstance(kw, str):
                    kw = kw.strip()
                    if kw:
                        merged_keywords.append(kw)
            merged_keywords = list(dict.fromkeys(merged_keywords))[:12]
            emotion = json.dumps(emt, ensure_ascii=False)
            histext = memo.quote_trpg(req.session_id, character_id)
            if histext is None:
                old = [0, 0, 0]
            else:
                old = json.loads(histext)
            personality = character_card_group["personality_matrix"]
            inertia = character_card_group["inertia"]
            emoca = Calculator(emt, old, personality, inertia)
            history = emoca.calculate()
            history_list = history.tolist()
            historia = json.dumps(history_list, ensure_ascii=False)
            expression = emoca.dikastis(old, emt, history_list)
            memo.request_trpg(
                session_id=req.session_id,
                character_id=character_id,
                submit=req.message,
                reply=reply,
                summary=abr1,
                motto=abr2,
                emotion=emotion,
                history=historia,
                keywords=merged_keywords
            )
            # 1. 先把 AI 自己的回复加入公共上下文
            add_trpg_context(req.session_id, character_name, reply)
            # 2. 也加入返回列表，让前端能看到 AI 发出的 @Dice 指令
            replies.append(GroupCharacterReply(
                character_id=character_id,
                name=character_name,
                reply=reply,
                expression=expression,
            ))
            # 3. 后端拦截 AI 回复中的 @Dice 指令
            dice_commands = extract_dice_commands(reply)

            for dice_command in dice_commands:
                try:
                    dice_result = solvendo(
                        command=dice_command,
                        session_id=req.session_id,
                        owner_id=character_id,
                        rule=req.dice_rule or "common",
                        rule_config=req.dice_rule_config or {}
                    )
                    dice_text = (
                        f"{character_name} 执行跑团指令：{dice_command}\n\n"
                        f"{dice_result['text']}"
                    )
                    # 4. 骰子结果进入跑团公共上下文
                    # 后续 AI 在同一轮内就能看到这个结果
                    add_trpg_context(req.session_id, "跑团系统", dice_text)
                    # 5. 骰子结果也返回给前端显示
                    replies.append(GroupCharacterReply(
                        character_id="dice_system",
                        name="跑团系统",
                        reply=dice_text,
                        expression="neutral",
                        expression_image=""
                    ))
                except (ValueError, SheetCommandError) as e:
                    dice_error_text = (
                        f"{character_name} 执行跑团指令失败：{dice_command}\n\n"
                        f"错误原因：{str(e)}"
                    )
                    add_trpg_context(req.session_id, "跑团系统", dice_error_text)
                    replies.append(GroupCharacterReply(
                        character_id="dice_system",
                        name="跑团系统",
                        reply=dice_error_text,
                        expression="neutral",
                        expression_image=""
                    ))
        except requests.exceptions.Timeout:
            raise HTTPException(status_code=504, detail=f"{character_name} 跑团请求超时")
        except Exception as e:
            print(f"{character_name} 跑团后端异常 =", repr(e))
            raise HTTPException(status_code=500, detail=f"{character_name} 跑团服务器错误: {str(e)}")
    return GroupChatResponse(replies=replies)

# ----------------------------------------------------------
# DS9 新增，骰娘，丢骰子
@app.post("/dice/roll", response_model=DiceRollResponse)
def dice_roll(req: DiceRollRequest):
    try:
        result = solvendo(
            command=req.command,
            session_id=req.session_id,
            owner_id="user",
            rule=req.rule or "common",
            rule_config=req.rule_config or {}
        )
        # 如果前端传了 session_id，说明这是跑团模式中的手动掷骰。
        # 这时把骰子结果写入跑团公共上下文，让后续 AI 能看到。
        if req.session_id:
            add_trpg_context(
                req.session_id,
                "骰子系统",
                result["text"]
            )
        return DiceRollResponse(**result)
    except (ValueError, SheetCommandError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print("骰子后端异常 =", repr(e))
        raise HTTPException(status_code=500, detail=f"骰子服务器错误: {str(e)}")
# ----------------------------------------------------------
# DS11 新增，清空所有模式的记录
@app.post("/conversation/delete")
def delete_conversation(req: ConversationDeleteRequest):
    global group_context_history
    global group_circulations
    global trpg_context_history
    global trpg_circulations
    if req.mode == "group_tavern":
        if req.session_id in group_context_history:
            del group_context_history[req.session_id]
        if req.session_id in group_circulations:
            del group_circulations[req.session_id]
    if req.mode == "group_trpg":
        if req.session_id in trpg_context_history:
            del trpg_context_history[req.session_id]
        if req.session_id in trpg_circulations:
            del trpg_circulations[req.session_id]
    deleted_rows = memo.obliviscere(
        session_id=req.session_id,
        mode=req.mode
    )
    deleted_sheets = 0
    if req.mode == "group_trpg":
        deleted_sheets = sheet.delete_session(req.session_id)
    return {
        "status": "ok",
        "message": f"会话已删除: {req.session_id}",
        "deleted_rows": deleted_rows,
        "deleted_sheets": deleted_sheets
    }
# ----------------------------------------------------------

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "deepseek-chat", "model": MODEL}

if __name__ == "__main__":
    import uvicorn
    print("🚀 DeepSeek API 服务启动...")
    print("📍 访问地址: http://localhost:8000")
    print("📄 前端页面: http://localhost:8000 直接打开")
    uvicorn.run(app, host="0.0.0.0", port=8000)