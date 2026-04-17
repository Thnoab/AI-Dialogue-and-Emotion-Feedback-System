from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Character(db.Model):
    __tablename__ = 'characters'
    

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(200), nullable=True)
    prompt = db.Column(db.Text, nullable=False)         
    attributes = db.Column(db.JSON, nullable=True)     
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Character {self.name}>'