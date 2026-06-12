import sqlite3
import json
import os

class Memorize:
    def __init__(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, "Memory_ConverContent.db")
        self.conn = sqlite3.connect('Memory_ConverContent.db', check_same_thread=False)
        self.cor = self.conn.cursor()
        self.cor.execute("""
        CREATE TABLE IF NOT EXISTS memory(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT DEFAULT 'guest',
        character_id TEXT DEFAULT 'single',
        mode TEXT DEFAULT 'normal',
        session_id TEXT DEFAULT 'default',
        submit TEXT NOT NULL,
        reply TEXT,
        summary TEXT NOT NULL,
        motto TEXT,
        emotion TEXT,
        history TEXT,
        keywords TEXT DEFAULT '[]')
        """)
        self.cor.execute("PRAGMA table_info(memory)")
        columns = [row[1] for row in self.cor.fetchall()]
        if "user_id" not in columns:
            self.cor.execute("ALTER TABLE memory ADD COLUMN user_id TEXT DEFAULT 'guest'")
        self.conn.commit()

    def communicate(self, user_id, session_id, character_id, msg, abr):
        print("communicate开始, character_id =", character_id)
        self.cor.execute(
            '''
            INSERT INTO memory(user_id, session_id, character_id, mode, submit, summary)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (user_id, session_id, character_id, "single_daily", msg, abr)
        )
        self.conn.commit()
        row_id = self.cor.lastrowid
        print("communicate完成, row_id =", row_id)
        return row_id

    def reply(self, ret, abr, emt, row_id):
        print("reply开始, row_id =", row_id)
        self.cor.execute(
            'UPDATE memory SET reply = ?, motto = ?, emotion = ? WHERE id = ?',
            (ret, abr, emt, row_id)
        )
        self.conn.commit()
        print("reply完成")

    def calcu_result(self,his,row_id):
        print("calcu_result开始, row_id =", row_id)
        self.cor.execute(
            'UPDATE memory SET history = ? WHERE id = ?',
            (his,row_id)
        )
        self.conn.commit()

    def request(self, user_id, session_id, character_id, msg, abr1, ret, abr2, emt, his):
        print("request开始, character_id =", character_id)
        row_id = self.communicate(user_id, session_id, character_id, msg, abr1)
        self.reply(ret, abr2, emt, row_id)
        print("request完成")
        self.calcu_result(his, row_id)
        print("calcu_result完成")

    # 这里不是存储数据的，是打开上一个history，即先前的向量总值的，应该用在request前面的代码中的
    def quote(self, user_id, session_id, character_id):
        print('quote开始, session_id =', session_id, 'character_id =', character_id)
        self.cor.execute(
            '''
            SELECT history
            FROM memory
            WHERE user_id = ?
            AND session_id = ?
            AND character_id = ?
            AND mode = ?
            AND history IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            ''',
            (user_id, session_id, character_id, "single_daily")
        )
        row = self.cor.fetchone()
        if row is None:
            return None
        return row[0]
    
    # 这里是打开新存入的缩略内容，即两个abbreviation
    def rappelez(self, user_id, session_id, character_id, n):
        print('rappelez开始, session_id =', session_id, 'character_id =', character_id)
        if n < 0 or n > 20:
            raise ValueError("n 必须在 0 到 20 之间")
        mode = "single_daily"
        m = 20 - n
        self.cor.execute(
            '''
            SELECT COUNT(*)
            FROM memory
            WHERE user_id = ?
            AND session_id = ?
            AND character_id = ?
            AND mode = ?
            ''',
            (user_id, session_id, character_id, mode)
        )
        count = self.cor.fetchone()[0]
        if count == 0:
            print(f"{session_id} / {character_id} 的单人数据库为空（冷启动）")
            return {
                "status": "empty",
                "recent_submit": [],
                "recent_reply": [],
                "old_summary": [],
                "old_motto": []
            }
        recent_submit = []
        recent_reply = []
        old_summary = []
        old_motto = []
        # 最近 n 条：取完整 submit + reply
        if n > 0:
            self.cor.execute(
                '''
                SELECT id
                FROM memory
                WHERE user_id = ?
                AND session_id = ?
                AND character_id = ?
                AND mode = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (user_id, session_id, character_id, mode, n)
            )
            recent_ids = [row[0] for row in self.cor.fetchall()]
        else:
            recent_ids = []
        if recent_ids:
            placeholders = ",".join(["?"] * len(recent_ids))
            self.cor.execute(
                f'''
                SELECT submit, reply
                FROM memory
                WHERE user_id = ?
                AND session_id = ?
                AND character_id = ?
                AND mode = ?
                AND id IN ({placeholders})
                ORDER BY id ASC
                ''',
                [user_id, session_id, character_id, mode] + recent_ids
            )
            rows = self.cor.fetchall()
            recent_submit = [row[0] for row in rows if row[0] is not None]
            recent_reply = [row[1] for row in rows if row[1] is not None]
        # 更早 m 条：取 summary + motto
        if m > 0:
            if recent_ids:
                placeholders = ",".join(["?"] * len(recent_ids))
                params = [user_id, session_id, character_id, mode] + recent_ids + [m]
                self.cor.execute(
                    f'''
                    SELECT summary, motto
                    FROM memory
                    WHERE user_id = ?
                    AND session_id = ?
                    AND character_id = ?
                    AND mode = ?
                    AND id NOT IN ({placeholders})
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    params
                )
            else:
                self.cor.execute(
                    '''
                    SELECT summary, motto
                    FROM memory
                    WHERE user_id = ?
                    AND session_id = ?
                    AND character_id = ?
                    AND mode = ?
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    (user_id, session_id, character_id, mode, m)
                )
            old_rows = self.cor.fetchall()
            old_rows.reverse()
            old_summary = [row[0] for row in old_rows if row[0] is not None]
            old_motto = [row[1] for row in old_rows if row[1] is not None]
        print('rappelez结束, session_id =', session_id, 'character_id =', character_id)
        return {
            "status": "fine",
            "recent_submit": recent_submit,
            "recent_reply": recent_reply,
            "old_summary": old_summary,
            "old_motto": old_motto
        }
    
# ==================== 多人模式 ====================
# =================================================
    def communicate_multi(self, user_id, session_id, character_id, msg, abr):
        self.cor.execute(
            '''
            INSERT INTO memory(user_id, session_id, character_id, mode, submit, summary)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (user_id, session_id, character_id, "group_tavern", msg, abr)
        )
        self.conn.commit()
        return self.cor.lastrowid
    
    def request_multi(self, user_id, session_id, character_id, msg, abr1, ret, abr2, emt, his):
        row_id = self.communicate_multi(user_id, session_id, character_id, msg, abr1)
        self.reply(ret, abr2, emt, row_id)
        self.calcu_result(his, row_id)

    def quote_multi(self, user_id, session_id, character_id):
        self.cor.execute(
            '''
            SELECT history
            FROM memory
            WHERE user_id = ?
            AND session_id = ?
            AND character_id = ?
            AND mode = ?
            AND history IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            ''',
            (user_id, session_id, character_id, "group_tavern")
        )
        row = self.cor.fetchone()
        if row is None:
            return None
        return row[0]

    def rappellent(self, user_id, session_id, character_id, n):
        print('rappellent开始, session_id =', session_id, 'character_id =', character_id)
        if n < 0 or n > 20:
            raise ValueError("n 必须在 0 到 20 之间")
        mode = "group_tavern"
        m = 20 - n
        self.cor.execute(
            '''
            SELECT COUNT(*)
            FROM memory
            WHERE user_id = ?
            AND session_id = ?
            AND character_id = ?
            AND mode = ?
            ''',
            (user_id, session_id, character_id, mode)
        )
        count = self.cor.fetchone()[0]
        if count == 0:
            print(f"{session_id} / {character_id} 的多人数据库为空（冷启动）")
            return {
                "status": "empty",
                "recent_submit": [],
                "recent_reply": [],
                "old_summary": [],
                "old_motto": []
            }
        recent_submit = []
        recent_reply = []
        old_summary = []
        old_motto = []
        # 最近 n 条：取完整 submit + reply
        if n > 0:
            self.cor.execute(
                '''
                SELECT id
                FROM memory
                WHERE user_id = ?
                AND session_id = ?
                AND character_id = ?
                AND mode = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (user_id, session_id, character_id, mode, n)
            )
            recent_ids = [row[0] for row in self.cor.fetchall()]
        else:
            recent_ids = []
        if recent_ids:
            placeholders = ",".join(["?"] * len(recent_ids))

            self.cor.execute(
                f'''
                SELECT submit, reply
                FROM memory
                WHERE user_id = ?
                AND session_id = ?
                AND character_id = ?
                AND mode = ?
                AND id IN ({placeholders})
                ORDER BY id ASC
                ''',
                [user_id, session_id, character_id, mode] + recent_ids
            )
            rows = self.cor.fetchall()
            recent_submit = [row[0] for row in rows if row[0] is not None]
            recent_reply = [row[1] for row in rows if row[1] is not None]
        # 更早 m 条：取 summary + motto
        if m > 0:
            if recent_ids:
                placeholders = ",".join(["?"] * len(recent_ids))
                params = [user_id, session_id, character_id, mode] + recent_ids + [m]
                self.cor.execute(
                    f'''
                    SELECT summary, motto
                    FROM memory
                    WHERE user_id = ?
                    AND session_id = ?
                    AND character_id = ?
                    AND mode = ?
                    AND id NOT IN ({placeholders})
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    params
                )
            else:
                self.cor.execute(
                    '''
                    SELECT summary, motto
                    FROM memory
                    WHERE user_id = ?
                    AND session_id = ?
                    AND character_id = ?
                    AND mode = ?
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    (user_id, session_id, character_id, mode, m)
                )
            old_rows = self.cor.fetchall()
            old_rows.reverse()
            old_summary = [row[0] for row in old_rows if row[0] is not None]
            old_motto = [row[1] for row in old_rows if row[1] is not None]
        print('rappellent结束, session_id =', session_id, 'character_id =', character_id)
        return {
            "status": "fine",
            "recent_submit": recent_submit,
            "recent_reply": recent_reply,
            "old_summary": old_summary,
            "old_motto": old_motto
        }
# =================================================
# DS8 新增，多人跑团模式
    def rappeler(self, user_id, session_id, character_id, current_keywords=None, fixed_memory="", n=25, total=65, relevant_limit=5):
        """
        跑团模式专属记忆算法。
        按 session_id + character_id + mode = group_trpg 隔离。
        """
        print("rappeler开始, session_id =", session_id, "character_id =", character_id)
        if current_keywords is None:
            current_keywords = []
        if not isinstance(current_keywords, list):
            current_keywords = []
        if n < 0 or n > total:
            raise ValueError("n 必须在 0 到 total 之间")
        mode = "group_trpg"
        m = total - n
        recent_submit = []
        recent_reply = []
        old_summary = []
        old_motto = []
        self.cor.execute(
            '''
            SELECT COUNT(*)
            FROM memory
            WHERE user_id = ?
            AND session_id = ?
            AND character_id = ?
            AND mode = ?
            ''',
            (user_id, session_id, character_id, mode)
        )
        count = self.cor.fetchone()[0]
        if count == 0:
            print(f"{session_id} / {character_id} 的跑团数据库为空（冷启动）")
            return {
                "status": "empty",
                "fixed_memory": fixed_memory,
                "recent_submit": [],
                "recent_reply": [],
                "old_summary": [],
                "old_motto": [],
                "relevant_memory": [],
                "keywords": current_keywords
            }
        if n > 0:
            self.cor.execute(
                '''
                SELECT id
                FROM memory
                WHERE user_id = ?
                AND session_id = ?
                AND character_id = ?
                AND mode = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (user_id, session_id, character_id, mode, n)
            )
            recent_ids = [row[0] for row in self.cor.fetchall()]
        else:
            recent_ids = []
        if recent_ids:
            placeholders = ",".join(["?"] * len(recent_ids))
            self.cor.execute(
                f'''
                SELECT submit, reply
                FROM memory
                WHERE user_id = ?
                AND session_id = ?
                AND character_id = ?
                AND mode = ?
                AND id IN ({placeholders})
                ORDER BY id ASC
                ''',
                [user_id, session_id, character_id, mode] + recent_ids
            )
            rows = self.cor.fetchall()
            recent_submit = [row[0] for row in rows if row[0] is not None]
            recent_reply = [row[1] for row in rows if row[1] is not None]
        if m > 0:
            if recent_ids:
                placeholders = ",".join(["?"] * len(recent_ids))
                params = [user_id, session_id, character_id, mode] + recent_ids + [m]
                self.cor.execute(
                    f'''
                    SELECT summary, motto
                    FROM memory
                    WHERE user_id = ?
                    AND session_id = ?
                    AND character_id = ?
                    AND mode = ?
                    AND id NOT IN ({placeholders})
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    params
                )
            else:
                self.cor.execute(
                    '''
                    SELECT summary, motto
                    FROM memory
                    WHERE user_id = ?
                    AND session_id = ?
                    AND character_id = ?
                    AND mode = ?
                    ORDER BY id DESC
                    LIMIT ?
                    ''',
                    (user_id, session_id, character_id, mode, m)
                )
            old_rows = self.cor.fetchall()
            old_rows.reverse()
            old_summary = [row[0] for row in old_rows if row[0] is not None]
            old_motto = [row[1] for row in old_rows if row[1] is not None]
        relevant_memory = self.anaklisi(
            user_id=user_id,
            session_id=session_id,
            character_id=character_id,
            keywords=current_keywords,
            limit=relevant_limit
        )
        print("rappeler结束, session_id =", session_id, "character_id =", character_id)
        return {
            "status": "fine",
            "fixed_memory": fixed_memory,
            "recent_submit": recent_submit,
            "recent_reply": recent_reply,
            "old_summary": old_summary,
            "old_motto": old_motto,
            "relevant_memory": relevant_memory,
            "keywords": current_keywords
        }
    
    def anaklisi(self, user_id, session_id, character_id, keywords, limit=5):
        """
        跑团模式相关旧记忆召回。
        用关键词比对完整记忆 submit/reply/summary/motto/keywords，
        但返回时只返回 summary 和 motto，避免 prompt 太长。
        按 session_id + character_id + group_trpg 隔离。
        """
        print("anaklisi开始, session_id =", session_id, "character_id =", character_id)
        if not keywords:
            return []
        clean_keywords = []
        for kw in keywords:
            if isinstance(kw, str):
                kw = kw.strip()
                if kw:
                    clean_keywords.append(kw)
        if not clean_keywords:
            return []
        mode = "group_trpg"
        self.cor.execute(
            '''
            SELECT id, submit, reply, summary, motto, keywords
            FROM memory
            WHERE user_id = ?
            AND session_id = ?
            AND character_id = ?
            AND mode = ?
            ORDER BY id DESC
            LIMIT 300
            ''',
            (user_id, session_id, character_id, mode)
        )
        rows = self.cor.fetchall()
        results = []
        for row in rows:
            row_id, submit, reply, summary, motto, keywords_text = row
            searchable = "\n".join([
                submit or "",
                reply or "",
                summary or "",
                motto or "",
                keywords_text or ""
            ])
            score = 0
            for kw in clean_keywords:
                if kw in searchable:
                    score += 1
            if score > 0:
                results.append({
                    "id": row_id,
                    "score": score,
                    "summary": summary or "",
                    "motto": motto or ""
                })
        results.sort(key=lambda item: item["score"], reverse=True)
        print("anaklisi结束, session_id =", session_id, "character_id =", character_id)
        return results[:limit]
    
    def request_trpg(self, user_id, session_id, character_id, submit, reply, summary, motto, emotion, history, keywords):
        """
        跑团模式写入数据库。
        按 session_id + character_id + mode = group_trpg 保存。
        """
        print("request_trpg开始, session_id =", session_id, "character_id =", character_id)
        mode = "group_trpg"
        if keywords is None:
            keywords = []
        keywords_text = json.dumps(keywords, ensure_ascii=False)
        self.cor.execute(
            '''
            INSERT INTO memory
            (user_id, session_id, character_id, mode, submit, reply, summary, motto, emotion, history, keywords)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                user_id,
                session_id,
                character_id,
                mode,
                submit,
                reply,
                summary,
                motto,
                emotion,
                history,
                keywords_text
            )
        )
        self.conn.commit()
        row_id = self.cor.lastrowid
        print("request_trpg完成, row_id =", row_id)
        return row_id
    
    def quote_trpg(self, user_id, session_id, character_id):
        """
        读取指定 session + 指定角色在跑团模式下最近一次 history。
        """
        print("quote_trpg开始, session_id =", session_id, "character_id =", character_id)
        self.cor.execute(
            '''
            SELECT history
            FROM memory
            WHERE user_id = ?
            AND session_id = ?
            AND character_id = ?
            AND mode = ?
            AND history IS NOT NULL
            ORDER BY id DESC
            LIMIT 1
            ''',
            (user_id, session_id, character_id, "group_trpg")
        )
        row = self.cor.fetchone()
        print("quote_trpg结束, session_id =", session_id, "character_id =", character_id)
        if row is None:
            return None
        return row[0]
# =================================================
# DS11 新增，所有模式清空记录
    def obliviscere(self, user_id, session_id, mode):
        """
        删除某一个 session_id + mode 对应的全部数据库记忆。
        single_daily：删除某个单人对话
        group_tavern：删除某个多人酒馆对话
        group_trpg：删除某个跑团对话
        """
        print("delete_session_records开始, session_id =", session_id, "mode =", mode)
        self.cor.execute(
            '''
            DELETE FROM memory
            WHERE user_id = ?
            AND session_id = ?
            AND mode = ?
            ''',
            (user_id, session_id, mode)
        )
        deleted_rows = self.cor.rowcount
        self.conn.commit()
        print("delete_session_records完成, deleted_rows =", deleted_rows)
        return deleted_rows
# =================================================
    def close(self):
        self.conn.close()

    def show_all(self):
        self.cor.execute('SELECT * FROM memory')
        return self.cor.fetchall()