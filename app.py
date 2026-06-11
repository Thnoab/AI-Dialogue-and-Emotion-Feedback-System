import os
import json
from flask import Flask, request, render_template, redirect, url_for, flash
from models import db, Character


app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key'  
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.instance_path, 'tavern.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db.init_app(app)




# 确保 instance 
with app.app_context():
    os.makedirs(app.instance_path, exist_ok=True)
    db.create_all()

#角色表单
@app.route('/characters/new')
def new_character():
    return render_template('new_character.html')

@app.route('/characters', methods=['POST'])
def create_character():
    name = request.form.get('name')
    description = request.form.get('description')
    prompt = request.form.get('prompt')
    

    behavior_tags_json = request.form.get('behavior_tags')

    personality_tags_json = request.form.get('personality_tags')

    portrait_base64 = request.form.get('portrait_base64')

    story_weight = request.form.get('story_weight', type=int, default=5)


    if not name or not prompt:
        flash('角色名称和提示词为必填项！', 'error')
        return redirect(url_for('new_character'))


    existing = Character.query.filter_by(name=name).first()
    if existing:
        flash(f'角色名 "{name}" 已存在，请使用其他名称。', 'error')
        return redirect(url_for('new_character'))





    # 解析JSON 
    attributes = {}
    if behavior_tags_json:
        try:
            attributes['behavior_tags'] = json.loads(behavior_tags_json)
        except json.JSONDecodeError:
            flash('行为标签数据格式错误，请重试。', 'error')
            return redirect(url_for('new_character'))
    
    if personality_tags_json:
        try:
            attributes['personality_tags'] = json.loads(personality_tags_json)
        except json.JSONDecodeError:
            flash('性格标签数据格式错误，请重试。', 'error')
            return redirect(url_for('new_character'))

    if portrait_base64:

        attributes['portrait'] = portrait_base64

    if story_weight is not None:
        attributes['story_weight'] = story_weight


    character = Character(
        name=name,
        description=description,
        prompt=prompt,
        attributes=attributes if attributes else None
    )
    db.session.add(character)

    db.session.commit()

    flash(f'角色 "{name}" 创建成功！', 'success')
    return redirect(url_for('new_character'))

# 角色列表
@app.route('/characters')
def list_characters():

    characters = Character.query.all()
    return render_template('characters.html', characters=characters)

if __name__ == '__main__':
    app.run(debug=True)