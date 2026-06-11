import json
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_CHARACTERS = [
    {
        "character_id": "flora",
        "name": "???",
        "summary": "????????????????????",
        "prompt": "???????????????????????????????????????????",
    },
    {
        "character_id": "leon",
        "name": "??",
        "summary": "??????????????????",
        "prompt": "?????????????????????????????????????",
    },
    {
        "character_id": "mora",
        "name": "??",
        "summary": "???????????????????",
        "prompt": "???????????????????????????????????????????",
    },
]


class CharacterStore:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent
        self.character_dir = self.base_dir / "characters"
        self.workspace_dir = self.base_dir.parent

    def list_characters(self) -> List[Dict]:
        characters = self._load_local_characters()
        if not characters:
            characters = DEFAULT_CHARACTERS.copy()
        return characters

    def get_character(self, character_id: Optional[str]) -> Dict:
        characters = self.list_characters()
        if character_id:
            for character in characters:
                if character.get("character_id") == character_id:
                    return character
        return characters[0]

    def get_character_map(self) -> Dict[str, str]:
        return {
            character["character_id"]: character["name"]
            for character in self.list_characters()
            if character.get("character_id") and character.get("name")
        }

    def _load_local_characters(self) -> List[Dict]:
        items: List[Dict] = []
        if not self.character_dir.exists():
            return items

        for path in sorted(self.character_dir.glob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            character_id = str(data.get('character_id') or data.get('id') or '').strip()
            name = str(data.get('name') or '').strip()
            prompt = str(data.get('prompt') or data.get('system_prompt') or '').strip()
            summary = str(data.get('summary') or data.get('description') or '').strip()
            if not character_id or not name or not prompt:
                continue
            items.append({
                'character_id': character_id,
                'name': name,
                'summary': summary or f'{name} ?????',
                'prompt': prompt,
            })
        return items
