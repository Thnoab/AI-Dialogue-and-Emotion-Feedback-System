import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from DS3_Memo import Memorize  # 新增
import json  # 新增
from DS4_Emo import Calculator # DS3 新增
from fastapi.staticfiles import StaticFiles # DS3 新增

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

if not API_KEY:
    raise RuntimeError("未找到 DeepSeek API Key")

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

memo = Memorize()

# ---------- 调用人物卡 ----------
def load_character_card(path="characters/demo_character.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
character_card = load_character_card()

# ---------- 前端静态页面 ----------
@app.get("/")
async def serve_frontend():
    """返回 index.html 文件"""
    return FileResponse("index_DS4.html")

# ---------- API 接口 ----------
class ChatRequest(BaseModel):
    message: str
    system_prompt: Optional[str] = f"你必须严格输出JSON格式,你是一个DeepSeek助手，回答要简洁有用。"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000

class ChatResponse(BaseModel):
    reply: str
    expression: str

@app.post("/chat", response_model=ChatResponse)
def chat_with_deepseek(req: ChatRequest):
    url = f"{BASE_URL}/chat/completions"
    messages = []
    if req.system_prompt:
        messages.append({"role": "system", "content": req.system_prompt})
    # ----------------------------------------------------------
    # DS3 新增
    # 这里是把过去的历史内容合并的代码
    memoria = memo.rappelez(5)
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
        histext = memo.quote()
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
        print("准备写入数据库")
        memo.request(req.message,abr1,reply,abr2,emotion,historia)
        print("数据库写入完成")
        # ----------------------------------------------------------
        return ChatResponse(reply=reply, expression=expression)
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="请求超时")
    except Exception as e:
        print("后端异常 =", repr(e))
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "deepseek-chat", "model": MODEL}

if __name__ == "__main__":
    import uvicorn
    print("🚀 DeepSeek API 服务启动...")
    print("📍 访问地址: http://localhost:8000")
    print("📄 前端页面: http://localhost:8000 直接打开")
    uvicorn.run(app, host="0.0.0.0", port=8000)