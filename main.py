import os
import json
import time
import shutil
import traceback
from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from typing import Optional
from database import init_db, create_character, get_all_characters, get_character_by_name, get_db

app = FastAPI(title="AI Tavern 角色管理")


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 目录
UPLOAD_DIR = "static/uploads"
CHARACTERS_JSON_DIR = "data/characters"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(CHARACTERS_JSON_DIR, exist_ok=True)

@app.on_event("startup")
def startup():
    init_db()

@app.get("/")
async def index():
    return RedirectResponse(url="/characters")


@app.get("/characters/new")
async def new_character(request: Request):
    return templates.TemplateResponse("new_character.html", {"request": request})

@app.post("/characters")
async def create_character_route(request: Request):
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
        return templates.TemplateResponse("new_character.html", {"request": request, "error": "角色名称和提示词为必填项！"})
    if get_character_by_name(name):
        return templates.TemplateResponse("new_character.html", {"request": request, "error": f'角色名 "{name}" 已存在！'})

    # 处理默认头像
    avatar_file = form_data.get("avatar")
    avatar_path = None
    if avatar_file and hasattr(avatar_file, 'filename') and avatar_file.filename:
        ext = os.path.splitext(avatar_file.filename)[1]
        avatar_filename = f"{name}_avatar{ext}"
        avatar_save_path = os.path.join(UPLOAD_DIR, avatar_filename)
        with open(avatar_save_path, "wb") as f:
            shutil.copyfileobj(avatar_file.file, f)
        avatar_path = f"/static/uploads/{avatar_filename}"

    # 处理情绪差分
    expressions = {}
    for key, file_obj in form_data.items():
        if key.startswith("expressions_") and file_obj and hasattr(file_obj, 'filename') and file_obj.filename:
            emotion = key.replace("expressions_", "")
            ext = os.path.splitext(file_obj.filename)[1]
            filename = f"{name}_{emotion}{ext}"
            save_path = os.path.join(UPLOAD_DIR, filename)
            with open(save_path, "wb") as f:
                shutil.copyfileobj(file_obj.file, f)
            expressions[emotion] = f"/static/uploads/{filename}"


    try:
        matrix = json.loads(personality_matrix) if personality_matrix else None
    except:
        matrix = None
    try:
        inertia_list = json.loads(inertia) if inertia else None
    except:
        inertia_list = None
    try:
        behavior_list = json.loads(behavior_tags) if behavior_tags else None
    except:
        behavior_list = None
    try:
        personality_list = json.loads(personality_tags) if personality_tags else None
    except:
        personality_list = None

    attributes = {}
    if behavior_list:
        attributes['behavior_tags'] = behavior_list
    if personality_list:
        attributes['personality_tags'] = personality_list
    if story_weight:
        attributes['story_weight'] = int(story_weight)
    if avatar_path:
        attributes['avatar'] = avatar_path
    if expressions:
        attributes['expressions'] = expressions
    if matrix:
        attributes['personality_matrix'] = matrix
    if inertia_list:
        attributes['inertia'] = inertia_list

    create_character(name, description or "", prompt, attributes)

    default_expressions = {
        "neutral": "/static/images/Neutral1.png",
        "shy": "/static/images/Shy.png",
        "happy": "/static/images/Smile1.png",
        "angry": "/static/images/Angry.png",
        "sad": "/static/images/Sad1.png"
    }
    final_expressions = expressions if expressions else default_expressions
    character_json = {
        "character_id": name,
        "name": name,
        "prompt": prompt,
        "personality_matrix": matrix or [[1,0,0],[0,1,0],[0,0,1]],
        "inertia": inertia_list or [0.5,0.5,0.5],
        "default_expression": "neutral",
        "avatar": avatar_path or "/static/images/default.png",
        "expressions": final_expressions
    }
    json_path = os.path.join(CHARACTERS_JSON_DIR, f"{name}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(character_json, f, ensure_ascii=False, indent=2)

    return RedirectResponse(url="/characters?success=created", status_code=303)

# 角色裂表 

@app.get("/characters")
async def list_characters(request: Request, success: Optional[str] = None):
    try:
        characters = get_all_characters()
    except Exception as e:
        init_db()
        characters = get_all_characters()
    return templates.TemplateResponse("characters.html", {"request": request, "characters": characters, "success": success})

# 删除角色
@app.post("/characters/{name}/delete")
async def delete_character(name: str):
    try:
        conn = get_db()
        cursor = conn.execute("DELETE FROM characters WHERE name = ?", (name,))
        conn.commit()
        deleted = cursor.rowcount
        conn.close()

        if deleted == 0:
            raise HTTPException(status_code=404, detail="角色不存在")

        json_path = os.path.join(CHARACTERS_JSON_DIR, f"{name}.json")
        if os.path.exists(json_path):
            os.remove(json_path)

        return {"message": "删除成功"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

#  编辑角色
@app.get("/characters/{name}/edit")
async def edit_character(request: Request, name: str):
    character = get_character_by_name(name)
    if not character:
        raise HTTPException(status_code=404, detail="角色不存在")
    return templates.TemplateResponse("edit_character.html", {"request": request, "character": character})

@app.post("/characters/{old_name}/update")
async def update_character(request: Request, old_name: str):
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
        return RedirectResponse(url=f"/characters/{old_name}/edit?error=名称和提示词不能为空", status_code=303)

    if new_name != old_name:
        existing = get_character_by_name(new_name)
        if existing:
            return RedirectResponse(url=f"/characters/{old_name}/edit?error=角色名 '{new_name}' 已存在", status_code=303)


    old_char = get_character_by_name(old_name)
    if not old_char:
        raise HTTPException(status_code=404, detail="原角色不存在")


    avatar_path = old_char.get('attributes', {}).get('avatar') if old_char else None
    if new_name != old_name and avatar_path:
        old_avatar_file = os.path.join(UPLOAD_DIR, os.path.basename(avatar_path))
        if os.path.exists(old_avatar_file):
            ext = os.path.splitext(old_avatar_file)[1]
            new_avatar_name = f"{new_name}_avatar{ext}"
            new_avatar_path = os.path.join(UPLOAD_DIR, new_avatar_name)
            os.rename(old_avatar_file, new_avatar_path)
            avatar_path = f"/static/uploads/{new_avatar_name}"


    expressions = old_char.get('attributes', {}).get('expressions', {}).copy()
    if new_name != old_name:
        for emotion, img_path in expressions.items():
            old_file = os.path.join(UPLOAD_DIR, os.path.basename(img_path))
            if os.path.exists(old_file):
                ext = os.path.splitext(old_file)[1]
                new_file_name = f"{new_name}_{emotion}{ext}"
                new_file = os.path.join(UPLOAD_DIR, new_file_name)
                os.rename(old_file, new_file)
                expressions[emotion] = f"/static/uploads/{new_file_name}"


    avatar_file = form.get("avatar")
    if avatar_file and hasattr(avatar_file, 'filename') and avatar_file.filename:
        ext = os.path.splitext(avatar_file.filename)[1]
        new_avatar_name = f"{new_name}_avatar{ext}"
        save_path = os.path.join(UPLOAD_DIR, new_avatar_name)
        with open(save_path, "wb") as f:
            shutil.copyfileobj(avatar_file.file, f)
        avatar_path = f"/static/uploads/{new_avatar_name}"


    for key, file_obj in form.items():
        if key.startswith("expressions_") and file_obj and hasattr(file_obj, 'filename') and file_obj.filename:
            emotion = key.replace("expressions_", "")
            ext = os.path.splitext(file_obj.filename)[1]
            new_file_name = f"{new_name}_{emotion}{ext}"
            save_path = os.path.join(UPLOAD_DIR, new_file_name)
            with open(save_path, "wb") as f:
                shutil.copyfileobj(file_obj.file, f)
            expressions[emotion] = f"/static/uploads/{new_file_name}"


    try:
        behavior_list = json.loads(behavior_tags_json) if behavior_tags_json else None
    except:
        behavior_list = None
    try:
        personality_list = json.loads(personality_tags_json) if personality_tags_json else None
    except:
        personality_list = None
    try:
        matrix = json.loads(personality_matrix_json) if personality_matrix_json else None
    except:
        matrix = None
    try:
        inertia_list = [float(inertia_0 or 0.5), float(inertia_1 or 0.5), float(inertia_2 or 0.5)]
    except:
        inertia_list = [0.5, 0.5, 0.5]

    # attributes
    attributes = {}
    if behavior_list:
        attributes['behavior_tags'] = behavior_list
    if personality_list:
        attributes['personality_tags'] = personality_list
    if story_weight:
        attributes['story_weight'] = int(story_weight)
    if avatar_path:
        attributes['avatar'] = avatar_path
    if expressions:
        attributes['expressions'] = expressions
    if matrix:
        attributes['personality_matrix'] = matrix
    attributes['inertia'] = inertia_list

    # 数据库
    conn = get_db()
    try:
        conn.execute(
            "UPDATE characters SET name = ?, description = ?, prompt = ?, attributes = ? WHERE name = ?",
            (new_name, description or "", prompt, json.dumps(attributes, ensure_ascii=False), old_name)
        )
        conn.commit()
    except Exception as e:
        conn.close()
        return RedirectResponse(url=f"/characters/{old_name}/edit?error=数据库更新失败: {str(e)}", status_code=303)
    conn.close()


    old_json = os.path.join(CHARACTERS_JSON_DIR, f"{old_name}.json")
    new_json = os.path.join(CHARACTERS_JSON_DIR, f"{new_name}.json")
    default_expressions = {
        "neutral": "/static/images/Neutral1.png",
        "shy": "/static/images/Shy.png",
        "happy": "/static/images/Smile1.png",
        "angry": "/static/images/Angry.png",
        "sad": "/static/images/Sad1.png"
    }
    final_expressions = expressions if expressions else default_expressions
    character_json = {
        "character_id": new_name,
        "name": new_name,
        "prompt": prompt,
        "personality_matrix": matrix or [[1,0,0],[0,1,0],[0,0,1]],
        "inertia": inertia_list,
        "default_expression": "neutral",
        "avatar": avatar_path or "/static/images/default.png",
        "expressions": final_expressions
    }
    with open(new_json, "w", encoding="utf-8") as f:
        json.dump(character_json, f, ensure_ascii=False, indent=2)
    if old_name != new_name and os.path.exists(old_json):
        os.remove(old_json)

    return RedirectResponse(url="/characters?success=updated", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)