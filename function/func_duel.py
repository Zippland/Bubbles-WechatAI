import random
import logging
import time
import json
import os
import sqlite3
from typing import List, Dict, Tuple, Optional, Any
from threading import Thread, Lock

# 获取 Logger 实例
logger_duel = logging.getLogger("DuelRankSystem")

# 排位积分系统
class DuelRankSystem:
    # 使用线程锁确保数据库操作的线程安全
    _db_lock = Lock()
    
    def __init__(self, group_id=None, db_path="data/message_history.db"):
        """
        初始化排位系统
        
        Args:
            group_id: 群组ID
            db_path: 数据库文件路径
        """
        # 确保group_id不为空，现在只支持群聊
        if not group_id:
            raise ValueError("决斗功能只支持群聊")
            
        self.group_id = group_id
        self.db_path = db_path
        self._init_db()  # 初始化数据库
    
    def _get_db_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)
            conn.row_factory = sqlite3.Row  # 让查询结果可以像字典一样访问列
            return conn
        except sqlite3.Error as e:
            logger_duel.error(f"无法连接到 SQLite 数据库 '{self.db_path}': {e}", exc_info=True)
            raise  # 连接失败是严重问题，直接抛出异常
    
    def _init_db(self):
        """初始化数据库，创建表（如果不存在）"""
        sql_create_players = """
        CREATE TABLE IF NOT EXISTS duel_players (
            group_id TEXT NOT NULL,
            player_name TEXT NOT NULL,
            score INTEGER DEFAULT 1000,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            total_matches INTEGER DEFAULT 0,
            elder_wand INTEGER DEFAULT 0,
            magic_stone INTEGER DEFAULT 0,
            invisibility_cloak INTEGER DEFAULT 0,
            last_updated TEXT,
            PRIMARY KEY (group_id, player_name)
        );
        """
        # 移除了 duel_history 表的创建语句
        # 移除了相关索引的创建语句

        try:
            with self._db_lock:
                with self._get_db_conn() as conn:
                    cursor = conn.cursor()
                    cursor.execute(sql_create_players)
                    # 移除了执行创建 duel_history 表和索引的命令
                    conn.commit()
            logger_duel.info("数据库表 'duel_players' 检查/创建 完成。")
        except sqlite3.Error as e:
            logger_duel.error(f"创建/检查数据库表失败: {e}", exc_info=True)
            raise  # 初始化失败是严重问题
    
    def get_player_data(self, player_name: str) -> Dict:
        """获取玩家数据，如果不存在则创建"""
        try:
            with self._db_lock:
                with self._get_db_conn() as conn:
                    cursor = conn.cursor()
                    # 查询玩家数据
                    sql_query = """
                    SELECT * FROM duel_players 
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_query, (self.group_id, player_name))
                    result = cursor.fetchone()
                    
                    if result:
                        # 将 sqlite3.Row 转换为字典
                        player_data = dict(result)
                        # 构造特殊的 items 字典
                        player_data["items"] = {
                            "elder_wand": player_data.pop("elder_wand", 0),
                            "magic_stone": player_data.pop("magic_stone", 0),
                            "invisibility_cloak": player_data.pop("invisibility_cloak", 0)
                        }
                        return player_data
                    else:
                        # 玩家不存在，创建新玩家
                        default_data = {
                            "score": 1000,
                            "wins": 0,
                            "losses": 0,
                            "total_matches": 0,
                            "items": {
                                "elder_wand": 0,
                                "magic_stone": 0,
                                "invisibility_cloak": 0
                            }
                        }
                        
                        # 插入新玩家数据
                        sql_insert = """
                        INSERT INTO duel_players
                        (group_id, player_name, score, wins, losses, total_matches,
                         elder_wand, magic_stone, invisibility_cloak, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                        """
                        cursor.execute(sql_insert, (
                            self.group_id,
                            player_name,
                            default_data["score"],
                            default_data["wins"],
                            default_data["losses"],
                            default_data["total_matches"],
                            default_data["items"]["elder_wand"],
                            default_data["items"]["magic_stone"],
                            default_data["items"]["invisibility_cloak"]
                        ))
                        conn.commit()
                        
                        logger_duel.info(f"创建了新玩家: {player_name} 在群组 {self.group_id}")
                        return default_data
        
        except sqlite3.Error as e:
            logger_duel.error(f"获取玩家数据失败: {e}", exc_info=True)
            # 出错时返回默认数据
            return {
                "score": 1000,
                "wins": 0,
                "losses": 0,
                "total_matches": 0,
                "items": {
                    "elder_wand": 0,
                    "magic_stone": 0,
                    "invisibility_cloak": 0
                }
            }
    
    def update_score(self, winner: str, loser: str, winner_hp: int, rounds: int) -> Tuple[int, int]:
        """更新玩家积分
        
        Args:
            winner: 胜利者名称
            loser: 失败者名称
            winner_hp: 胜利者剩余生命值
            rounds: 决斗回合数
            
        Returns:
            Tuple[int, int]: (胜利者获得积分, 失败者失去积分)
        """
        # 获取玩家数据
        winner_data = self.get_player_data(winner)
        loser_data = self.get_player_data(loser)
        
        # 基础积分计算 - 回合数越少积分越高
        base_points = 100
        if rounds <= 5:  # 速战速决
            base_points = 100
        elif rounds <= 10:
            base_points = 60
        elif rounds >= 15:  # 长时间战斗
            base_points = 40
            
        # 计算总积分变化（剩余生命值作为百分比加成）
        hp_percent_bonus = winner_hp / 100.0  # 血量百分比
        points = int(base_points * (hp_percent_bonus))  # 血量越多，积分越高
        
        try:
            with self._db_lock:
                with self._get_db_conn() as conn:
                    cursor = conn.cursor()
                    
                    # 更新胜利者数据
                    sql_update_winner = """
                    UPDATE duel_players SET 
                    score = score + ?,
                    wins = wins + 1,
                    total_matches = total_matches + 1,
                    last_updated = datetime('now')
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_update_winner, (points, self.group_id, winner))
                    
                    # 更新失败者数据
                    sql_update_loser = """
                    UPDATE duel_players SET 
                    score = MAX(1, score - ?),
                    losses = losses + 1,
                    total_matches = total_matches + 1,
                    last_updated = datetime('now')
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_update_loser, (points, self.group_id, loser))
                    
                    # 移除了记录对战历史的代码
                    
                    conn.commit()
                    logger_duel.info(f"{winner} 击败 {loser}，获得 {points} 积分")
                    
                    return (points, points)  # 返回胜者得分和败者失分（相同）
                    
        except sqlite3.Error as e:
            logger_duel.error(f"更新积分失败: {e}", exc_info=True)
            return (0, 0)  # 出错时返回0分
    
    def get_rank_list(self, top_n: int = 10) -> List[Dict]:
        """获取排行榜
        
        Args:
            top_n: 返回前几名
            
        Returns:
            List[Dict]: 排行榜数据
        """
        try:
            with self._db_lock:
                with self._get_db_conn() as conn:
                    cursor = conn.cursor()
                    sql_query = """
                    SELECT player_name, score, wins, losses, total_matches,
                           elder_wand, magic_stone, invisibility_cloak
                    FROM duel_players
                    WHERE group_id = ?
                    ORDER BY score DESC
                    LIMIT ?
                    """
                    cursor.execute(sql_query, (self.group_id, top_n))
                    results = cursor.fetchall()
                    
                    # 转换结果为字典列表，格式与原JSON格式相同
                    ranked_players = []
                    for row in results:
                        player_dict = dict(row)
                        player_name = player_dict.pop("player_name")
                        
                        # 构造与原格式相同的字典
                        player = {
                            "name": player_name,
                            "score": player_dict["score"],
                            "wins": player_dict["wins"],
                            "losses": player_dict["losses"],
                            "total_matches": player_dict["total_matches"],
                            "items": {
                                "elder_wand": player_dict["elder_wand"],
                                "magic_stone": player_dict["magic_stone"],
                                "invisibility_cloak": player_dict["invisibility_cloak"]
                            }
                        }
                        ranked_players.append(player)
                    
                    return ranked_players
                    
        except sqlite3.Error as e:
            logger_duel.error(f"获取排行榜失败: {e}", exc_info=True)
            return []  # 出错时返回空列表
    
    def get_player_rank(self, player_name: str) -> Tuple[Optional[int], Dict]:
        """获取玩家排名
        
        Args:
            player_name: 玩家名称
            
        Returns:
            Tuple[Optional[int], Dict]: (排名, 玩家数据)
        """
        # 获取玩家数据
        player_data = self.get_player_data(player_name)
        
        try:
            with self._db_lock:
                with self._get_db_conn() as conn:
                    cursor = conn.cursor()
                    
                    # 查询排行榜中有哪些分数比该玩家高
                    sql_rank = """
                    SELECT COUNT(*) + 1 as rank
                    FROM duel_players
                    WHERE group_id = ? AND score > (
                        SELECT score FROM duel_players
                        WHERE group_id = ? AND player_name = ?
                    )
                    """
                    cursor.execute(sql_rank, (self.group_id, self.group_id, player_name))
                    result = cursor.fetchone()
                    
                    if result:
                        rank = result["rank"]
                        return rank, player_data
                    else:
                        # 找不到玩家排名，可能是新玩家
                        return None, player_data
                        
        except sqlite3.Error as e:
            logger_duel.error(f"获取玩家排名失败: {e}", exc_info=True)
            return None, player_data  # 出错时返回None作为排名
    
    def change_player_name(self, old_name: str, new_name: str) -> bool:
        """更改玩家名称
        
        Args:
            old_name: 旧名称
            new_name: 新名称
            
        Returns:
            bool: 是否成功更改
        """
        try:
            with self._db_lock:
                with self._get_db_conn() as conn:
                    cursor = conn.cursor()
                    
                    # 开启事务
                    conn.execute("BEGIN TRANSACTION")
                    
                    # 检查旧名称是否存在
                    sql_check_old = """
                    SELECT COUNT(*) as count FROM duel_players
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_check_old, (self.group_id, old_name))
                    if cursor.fetchone()["count"] == 0:
                        conn.rollback()
                        return False
                    
                    # 检查新名称是否已存在
                    sql_check_new = """
                    SELECT COUNT(*) as count FROM duel_players
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_check_new, (self.group_id, new_name))
                    if cursor.fetchone()["count"] > 0:
                        conn.rollback()
                        return False
                    
                    # 更新玩家表
                    sql_update_player = """
                    UPDATE duel_players SET player_name = ?
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_update_player, (new_name, self.group_id, old_name))
                    
                    # 移除了更新历史记录表中的胜者和败者名称的代码
                    
                    # 提交事务
                    conn.commit()
                    logger_duel.info(f"成功将玩家 {old_name} 改名为 {new_name}")
                    
                    return True
                    
        except sqlite3.Error as e:
            logger_duel.error(f"更改玩家名称失败: {e}", exc_info=True)
            return False  # 出错时返回失败
    
    def update_score_by_magic(self, winner: str, loser: str, magic_power: int) -> Tuple[int, int]:
        """根据魔法分数更新玩家积分
        
        Args:
            winner: 胜利者名称
            loser: 失败者名称
            magic_power: 决斗中所有参与者使用的魔法总分数
            
        Returns:
            Tuple[int, int]: (胜利者获得积分, 失败者失去积分)
        """
        # 获取玩家数据 (这里只是为了确保玩家存在)
        self.get_player_data(winner)
        self.get_player_data(loser)
        
        # 使用魔法总分作为积分变化值
        points = magic_power
        
        try:
            with self._db_lock:
                with self._get_db_conn() as conn:
                    cursor = conn.cursor()
                    
                    # 更新胜利者数据
                    sql_update_winner = """
                    UPDATE duel_players SET 
                    score = score + ?,
                    wins = wins + 1,
                    total_matches = total_matches + 1,
                    last_updated = datetime('now')
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_update_winner, (points, self.group_id, winner))
                    
                    # 更新失败者数据
                    sql_update_loser = """
                    UPDATE duel_players SET 
                    score = MAX(1, score - ?),
                    losses = losses + 1,
                    total_matches = total_matches + 1,
                    last_updated = datetime('now')
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_update_loser, (points, self.group_id, loser))
                    
                    # 移除了记录对战历史的代码
                    
                    conn.commit()
                    logger_duel.info(f"{winner} 使用魔法击败 {loser}，获得 {points} 积分")
                    
                    return (points, points)  # 返回胜者得分和败者失分（相同）
                    
        except sqlite3.Error as e:
            logger_duel.error(f"根据魔法分数更新积分失败: {e}", exc_info=True)
            return (0, 0)  # 出错时返回0分
    
    def record_duel_result(self, winner: str, loser: str, winner_points: int, loser_points: int, total_magic_power: int, used_item: Optional[str] = None) -> Tuple[int, int]:
        """记录决斗结果，更新玩家数据和历史记录
        
        Args:
            winner: 胜利者名称
            loser: 失败者名称
            winner_points: 胜利者获得的积分
            loser_points: 失败者失去的积分
            total_magic_power: 决斗中使用的总魔法力
            used_item: 本次决斗中使用的道具名称 (可选)
                       可能是 "elder_wand"(老魔杖), "magic_stone"(魔法石), "invisibility_cloak"(隐身衣)
            
        Returns:
            Tuple[int, int]: (胜利者实际获得积分, 失败者实际失去积分)
        """
        # 获取玩家数据 (确保玩家存在)
        self.get_player_data(winner)
        self.get_player_data(loser)
        
        # 注意：loser_points 是正数，表示要扣除的分数
        
        try:
            with self._db_lock:
                with self._get_db_conn() as conn:
                    cursor = conn.cursor()
                    
                    # 更新胜利者数据
                    sql_update_winner = """
                    UPDATE duel_players SET 
                    score = score + ?,
                    wins = wins + 1,
                    total_matches = total_matches + 1,
                    last_updated = datetime('now')
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_update_winner, (winner_points, self.group_id, winner))
                    
                    # 更新失败者数据
                    sql_update_loser = """
                    UPDATE duel_players SET 
                    score = MAX(1, score - ?),
                    losses = losses + 1,
                    total_matches = total_matches + 1,
                    last_updated = datetime('now')
                    WHERE group_id = ? AND player_name = ?
                    """
                    cursor.execute(sql_update_loser, (loser_points, self.group_id, loser))

                    # --- 改进处理道具消耗逻辑 ---
                    if used_item == "elder_wand":
                        # 老魔杖是胜利者使用的
                        cursor.execute("UPDATE duel_players SET elder_wand = MAX(0, elder_wand - 1) WHERE group_id = ? AND player_name = ?", (self.group_id, winner))
                        logger_duel.info(f"消耗了 {winner} 的老魔杖 (剩余数量将被更新)")
                    elif used_item == "magic_stone":
                        # 魔法石是失败者使用的
                        cursor.execute("UPDATE duel_players SET magic_stone = MAX(0, magic_stone - 1) WHERE group_id = ? AND player_name = ?", (self.group_id, loser))
                        logger_duel.info(f"消耗了 {loser} 的魔法石 (剩余数量将被更新)")
                    elif used_item == "invisibility_cloak":
                        # 隐身衣由胜利者使用
                        cursor.execute("UPDATE duel_players SET invisibility_cloak = MAX(0, invisibility_cloak - 1) WHERE group_id = ? AND player_name = ?", (self.group_id, winner))
                        logger_duel.info(f"消耗了 {winner} 的隐身衣 (剩余数量将被更新)")
                    # --------------------------

                    # 移除了记录对战历史的代码
                    
                    conn.commit()
                    logger_duel.info(f"{winner} 在决斗中击败 {loser}，胜者积分 +{winner_points}，败者积分 -{loser_points}，使用道具: {used_item or '无'}")
                    
                    return (winner_points, loser_points)  # 返回实际积分变化
                    
        except sqlite3.Error as e:
            logger_duel.error(f"记录决斗结果失败: {e}", exc_info=True)
            return (0, 0)  # 出错时返回0分
        except Exception as e:
            logger_duel.error(f"记录决斗结果时发生未知错误: {e}", exc_info=True)
            return (0, 0)  # 出错时返回0分

class HarryPotterDuel:
    """决斗功能"""
    
    def __init__(self, player1, player2, group_id, player1_is_challenger=True):
        """
        初始化决斗
        :param player1: 玩家1的名称
        :param player2: 玩家2的名称
        :param group_id: 群组ID
        :param player1_is_challenger: 玩家1是否为决斗发起者
        """
        # 确保只在群聊中决斗
        if not group_id:
            raise ValueError("决斗功能只支持群聊")
            
        self.player1 = {
            "name": player1, 
            "hp": 100, 
            "spells": [], 
            "is_challenger": player1_is_challenger
        }
        self.player2 = {
            "name": player2, 
            "hp": 100, 
            "spells": [], 
            "is_challenger": not player1_is_challenger
        }
        self.rounds = 0
        self.steps = []
        self.group_id = group_id  # 记录群组ID
        
        # 检测是否为Boss战（对手是AI"泡泡"）
        self.is_boss_fight = (player2 == "泡泡")
        
        # Boss战特殊设置
        if self.is_boss_fight:
            # Boss战胜率极低，设为10%
            self.player_win_chance = 0.1
            # 添加Boss战提示信息
            self.steps.append("⚔️ Boss战开始 ⚔️\n挑战强大的魔法师泡泡！")
            
        # 设置防御成功率
        self.defense_success_rate = 0.3
        
        # 咒语列表（名称、威力、权重）- 权重越小越稀有
        self.spells = [
            {"name": "除你武器", "power": 10, "weight": 30, "desc": "🪄", 
             "attack_desc": ["挥动魔杖划出一道弧线，魔杖尖端发出红光，释放", "伸手一指对手的魔杖，大声喊道", "用魔杖直指对手，施放缴械咒"],
             "damage_desc": ["被红光击中，魔杖瞬间脱手飞出", "的魔杖被一股无形力量扯离手掌，飞向远处", "手中魔杖突然被击飞，不得不空手应对"]},
            
            {"name": "昏昏倒地", "power": 25, "weight": 25, "desc": "✨", 
             "attack_desc": ["魔杖发出耀眼的红光，发射昏迷咒", "快速挥舞魔杖，释放出一道猩红色闪光", "高声呼喊咒语，杖尖喷射出红色火花"],
             "damage_desc": ["被红光击中，意识开始模糊，几近昏迷", "躲闪不及，被击中后身体摇晃，眼神涣散", "被咒语命中，双腿一软，差点跪倒在地"]},
            
            {"name": "统统石化", "power": 40, "weight": 20, "desc": "💫", 
             "attack_desc": ["直指对手，魔杖尖端射出蓝白色光芒，施放石化咒", "魔杖在空中划过一道蓝光，精准施放", "双目紧盯对手，冷静施展全身束缚咒"],
             "damage_desc": ["身体被蓝光罩住，四肢瞬间变得僵硬如石", "全身突然绷紧，像被无形的绳索紧紧束缚", "动作突然凝固，仿佛变成了一座雕像"]},
            
            {"name": "障碍重重", "power": 55, "weight": 15, "desc": "⚡", 
             "attack_desc": ["魔杖猛地向前一挥，发射出闪亮的紫色光束", "大声念出咒语，同时杖尖射出炫目光芒", "旋转魔杖制造出一道旋转的障碍咒"],
             "damage_desc": ["被一股无形的力量狠狠推开，猛烈撞上后方障碍物", "身体被击中后像断线风筝般飞出数米，重重摔落", "被强大的冲击波掀翻在地，一时无法站起"]},
            
            {"name": "神锋无影", "power": 70, "weight": 10, "desc": "🗡️", 
             "attack_desc": ["低声念诵，魔杖如剑般挥下", "以危险的低沉嗓音念诵咒语，杖尖闪烁着寒光", "用魔杖在空中划出复杂轨迹，释放斯内普的秘咒"],
             "damage_desc": ["身上突然出现多道无形的切割伤口，鲜血喷涌而出", "惨叫一声，胸前与面部浮现出深深的伤痕，鲜血直流", "被无形的刀刃划过全身，衣物和皮肤同时被割裂，伤痕累累"]},
            
            {"name": "钻心剜骨", "power": 85, "weight": 5, "desc": "🔥", 
             "attack_desc": ["眼中闪过一丝狠厉，用尖利的声音喊出不可饶恕咒", "面露残忍笑容，魔杖直指对手施放酷刑咒", "用充满恶意的声音施放黑魔法，享受对方的痛苦"],
             "damage_desc": ["被咒语击中，全身每一根神经都在燃烧般剧痛，倒地挣扎哀嚎", "发出撕心裂肺的惨叫，痛苦地在地上痉挛扭曲", "遭受前所未有的剧痛折磨，脸上血管暴起，痛不欲生"]},
            
            {"name": "阿瓦达索命", "power": 100, "weight": 1, "desc": "💀", 
             "attack_desc": ["用充满杀意的声音念出死咒，魔杖喷射出刺目的绿光", "冷酷无情地发出致命死咒，绿光直射对手", "毫无犹豫地使用了最邪恶的不可饶恕咒，绿光闪耀"],
             "damage_desc": ["被绿光正面击中，生命瞬间被夺走，眼神空洞地倒下", "还未来得及反应，生命便随着绿光的接触戛然而止", "被死咒击中，身体僵直地倒下，生命气息完全消失"]}
        ]
        
        # 防御咒语列表（名称、描述）- 统一使用self.defense_success_rate作为成功率
        self.defense_spells = [
            {"name": "盔甲护身", "desc": "🛡️", 
             "defense_desc": ["迅速在身前制造出一道透明魔法屏障，挡住了攻击", "挥动魔杖在周身形成一道金色防御光幕，抵消了咒语", "大声喊出咒语，召唤出强力的防护盾牌"]},
            
            {"name": "除你武器", "desc": "⚔️", 
             "defense_desc": ["用缴械咒反击，成功击飞对方魔杖", "喊道出魔咒，让对手的魔咒偏离方向", "巧妙反击，用缴械咒化解了对手的攻击"]},
            
            {"name": "呼神护卫", "desc": "🧿", 
             "defense_desc": ["全神贯注地召唤出银色守护神，抵挡住了攻击", "魔杖射出耀眼银光，形成守护屏障吸收了咒语", "集中思念快乐回忆，释放出强大的守护神魔法"]}
        ]
        
        # 设置胜利描述
        self.victory_descriptions = [
            "让对手失去了战斗能力",
            "最终击倒了对手",
            "的魔法取得了胜利",
            "的致命一击决定了结果",
            "的魔法赢得了这场决斗",
            "对魔法的控制带来了胜利",
            "在激烈的对决中占据上风",
            "毫无悬念地获胜"
        ]
        
        # 记录开场信息
        if not self.is_boss_fight:
            self.steps.append(f"⚔️ 决斗开始 ⚔️\n{self.player1['name']} VS {self.player2['name']}")
    
    def select_spell(self):
        """随机选择一个咒语，威力越高出现概率越低"""
        weights = [spell["weight"] for spell in self.spells]
        total_weight = sum(weights)
        normalized_weights = [w/total_weight for w in weights]
        return random.choices(self.spells, weights=normalized_weights, k=1)[0]
    
    def attempt_defense(self):
        """尝试防御，返回是否成功和使用的防御咒语"""
        defense = random.choice(self.defense_spells)
        success = random.random() < self.defense_success_rate
        return success, defense
    
    def start_duel(self):
        """开始决斗，返回决斗过程的步骤列表"""
        # 创建积分系统实例，整个方法中重用
        rank_system = DuelRankSystem(self.group_id)
        
        # --- 修改：提前获取双方玩家数据 ---
        player1_data = rank_system.get_player_data(self.player1["name"])
        player2_data = rank_system.get_player_data(self.player2["name"])
        # ---------------------------------------------
        
        # Boss战特殊处理
        if self.is_boss_fight:
            # 生成随机的Boss战斗过程
            boss_battle_descriptions = [
                f"🔮 强大的Boss泡泡挥动魔杖，释放出一道耀眼的紫色光束，{self.player1['name']}勉强躲开！",
                f"⚡ {self.player1['name']}尝试施放昏昏倒地，但泡泡像预知一般轻松侧身避过！",
                f"🌪️ 泡泡召唤出一阵魔法旋风，将{self.player1['name']}的咒语全部吹散！",
                f"🔥 {self.player1['name']}使出全力施放火焰咒，泡泡却用一道水盾将其熄灭！",
                f"✨ 双方魔杖相对，杖尖迸发出耀眼的金色火花，魔力在空中碰撞！",
                f"🌟 泡泡释放出数十个魔法分身，{self.player1['name']}不知道哪个是真身！",
                f"🧙 {self.player1['name']}召唤出守护神，但在泡泡强大的黑魔法面前迅速消散！",
                f"⚔️ 一连串快速的魔咒交锋，魔法光束在空中交织成绚丽的网！",
                f"🛡️ 泡泡创造出一道几乎无法破解的魔法屏障，{self.player1['name']}的咒语无法穿透！",
                f"💫 {self.player1['name']}施放最强一击，能量波动让整个决斗场地震颤！"
            ]
            
            # 只随机选择一条战斗描述添加（减少刷屏）
            self.steps.append(random.choice(boss_battle_descriptions))
            
            # 检查是否战胜Boss（极低概率）
            if random.random() < self.player_win_chance:  # 玩家赢了
                winner, loser = self.player1, self.player2
                
                # 添加胜利转折点描述
                victory_turn = [
                    f"✨ 关键时刻，{winner['name']}找到了泡泡防御的破绽！",
                    f"🌟 命运女神眷顾了{winner['name']}，一个意外的反弹击中了泡泡的要害！",
                    f"💥 在泡泡即将施放致命一击时，{winner['name']}突然爆发出前所未有的魔法力量！"
                ]
                self.steps.append(random.choice(victory_turn))
                
                # 随机获得一件装备
                items = ["elder_wand", "magic_stone", "invisibility_cloak"]
                item_names = {"elder_wand": "老魔杖", "magic_stone": "魔法石", "invisibility_cloak": "隐身衣"}
                
                try:
                    with rank_system._db_lock:
                        with rank_system._get_db_conn() as conn:
                            cursor = conn.cursor()
                            
                            # 获取当前玩家的道具数量
                            sql_query = """
                            SELECT elder_wand, magic_stone, invisibility_cloak
                            FROM duel_players
                            WHERE group_id = ? AND player_name = ?
                            """
                            cursor.execute(sql_query, (self.group_id, winner["name"]))
                            result = cursor.fetchone()
                            
                            if result:
                                # 更新玩家数据，增加道具
                                sql_update = """
                                UPDATE duel_players SET
                                elder_wand = elder_wand + 1,
                                magic_stone = magic_stone + 1,
                                invisibility_cloak = invisibility_cloak + 1,
                                score = score + ?,
                                wins = wins + 1,
                                total_matches = total_matches + 1,
                                last_updated = datetime('now')
                                WHERE group_id = ? AND player_name = ?
                                """
                                winner_points = 300  # 胜利积分固定为500分
                                cursor.execute(sql_update, (winner_points, self.group_id, winner["name"]))
                                
                                # 移除了记录对战历史的代码
                                
                                conn.commit()
                                
                                # 查询更新后玩家排名
                                sql_rank = """
                                SELECT COUNT(*) + 1 as rank
                                FROM duel_players
                                WHERE group_id = ? AND score > (
                                    SELECT score FROM duel_players
                                    WHERE group_id = ? AND player_name = ?
                                )
                                """
                                cursor.execute(sql_rank, (self.group_id, self.group_id, winner["name"]))
                                rank_result = cursor.fetchone()
                                rank = rank_result["rank"] if rank_result else None
                                
                                rank_text = f"第{rank}名" if rank else "暂无排名"
                                
                                # 添加获得装备的信息
                                result = (
                                    f"🏆 {winner['name']} 以不可思议的实力击败了强大的Boss泡泡！\n\n"
                                    f"获得了三件死亡圣器！\n"
                                    f" 🪄   💎   🧥 \n\n"
                                    f"积分: +{winner_points}分 ({rank_text})"
                                )
                                
                                self.steps.append(result)
                                return self.steps
                            else:
                                # 玩家不存在，这种情况理论上不可能发生，但为安全添加
                                logger_duel.error(f"Boss战获胜但找不到玩家 {winner['name']} 数据")
                except sqlite3.Error as e:
                    logger_duel.error(f"处理Boss战胜利时出错: {e}", exc_info=True)
                    self.steps.append(f"⚠️ 处理战利品时遇到问题: {e}")
                    return self.steps
                
            else:  # 玩家输了
                winner, loser = self.player2, self.player1
                
                # 添加失败结局描述 - 更恐怖、更简洁的描述
                defeat_end = [
                    f"💀 泡泡瞬间爆发出令人胆寒的强大魔力，{loser['name']}甚至来不及反应就被击倒在地！",
                    f"⚰️ 只见泡泡轻轻挥动魔杖，{loser['name']}如遭雷击，整个人被恐怖的魔法能量碾压！",
                    f"☠️ 泡泡展现出真正的实力，一道黑色闪电瞬间击穿{loser['name']}的所有防御！"
                ]
                self.steps.append(random.choice(defeat_end))
                
                try:
                    with rank_system._db_lock:
                        with rank_system._get_db_conn() as conn:
                            cursor = conn.cursor()
                            
                            # 更新失败者数据
                            sql_update = """
                            UPDATE duel_players SET
                            score = MAX(1, score - 100),
                            losses = losses + 1,
                            total_matches = total_matches + 1,
                            last_updated = datetime('now')
                            WHERE group_id = ? AND player_name = ?
                            """
                            cursor.execute(sql_update, (self.group_id, loser["name"]))
                            
                            # 移除了记录对战历史的代码
                            
                            conn.commit()
                except sqlite3.Error as e:
                    logger_duel.error(f"处理Boss战失败时出错: {e}", exc_info=True)
                
                result = (
                    f"💀 {loser['name']} 不敌强大的Boss泡泡！\n\n"
                    f"积分: -100分\n"
                    f"再接再厉，下次挑战吧！"
                )
                
                self.steps.append(result)
                return self.steps
        
        # --- 新增：开局检查双方隐身衣 ---
        p1_cloak = player1_data["items"].get("invisibility_cloak", 0) > 0
        p2_cloak = player2_data["items"].get("invisibility_cloak", 0) > 0

        if p1_cloak and not p2_cloak: # 只有 Player1 有隐身衣
            winner, loser = self.player1, self.player2
            winner_points = 30
            loser_points = 30
            used_item = "invisibility_cloak"
            self.steps.append(f"🧥 {winner['name']} 开局使用了隐身衣，潜行偷袭，直接获胜！")
            # 直接调用记录结果函数处理数据库和返回消息
            return self._handle_direct_win(rank_system, winner, loser, winner_points, loser_points, used_item, player1_data)
        elif not p1_cloak and p2_cloak: # 只有 Player2 有隐身衣
            winner, loser = self.player2, self.player1
            winner_points = 30
            loser_points = 30
            used_item = "invisibility_cloak"
            self.steps.append(f"🧥 {winner['name']} 开局使用了隐身衣，潜行偷袭，直接获胜！")
            # 直接调用记录结果函数处理数据库和返回消息
            return self._handle_direct_win(rank_system, winner, loser, winner_points, loser_points, used_item, player2_data)
        elif p1_cloak and p2_cloak: # 双方都有隐身衣
            self.steps.append(f"🧥 双方都试图使用隐身衣，魔法相互干扰，隐身效果失效！决斗正常进行！")
            # （可选）可以在这里添加消耗双方隐身衣的逻辑，但为了简化，暂时不加
        # --- 隐身衣检查结束 ---
        
        # 普通决斗流程，保持原有逻辑
        # 根据决斗发起者设置先手概率
        if self.player1["is_challenger"]:
            # 获取挑战者的排名和总玩家数
            challenger = self.player1["name"]
            challenger_rank, _ = rank_system.get_player_rank(challenger)
            
            # 获取总玩家数
            all_players = rank_system.get_rank_list(9999)  # 获取所有玩家
            total_players = len(all_players)
            
            # 计算先手概率：基础概率50% + (排名/总人数)*30%
            # 如果没有排名或总玩家数为0，则使用基础概率50%
            if challenger_rank is not None and total_players > 0:
                # 排名越大（越靠后），先手优势越大
                first_attack_prob = 0.5 + (challenger_rank / total_players) * 0.3
            else:
                first_attack_prob = 0.5  # 默认概率
                
            current_attacker = "player1" if random.random() < first_attack_prob else "player2"
        else:
            # 获取挑战者的排名和总玩家数
            challenger = self.player2["name"]
            challenger_rank, _ = rank_system.get_player_rank(challenger)
            
            # 获取总玩家数
            all_players = rank_system.get_rank_list(9999)  # 获取所有玩家
            total_players = len(all_players)
            
            # 计算先手概率：基础概率50% + (排名/总人数)*30%
            # 如果没有排名或总玩家数为0，则使用基础概率50%
            if challenger_rank is not None and total_players > 0:
                # 排名越大（越靠后），先手优势越大
                first_attack_prob = 0.5 + (challenger_rank / total_players) * 0.3
            else:
                first_attack_prob = 0.5  # 默认概率
                
            current_attacker = "player2" if random.random() < first_attack_prob else "player1"
        
        # 随机选择先手介绍语
        first_move_descriptions = [
            "抢先出手，迅速进入战斗状态，",
            "反应更快，抢得先机，",
            "魔杖一挥，率先发动攻击，",
            "眼疾手快，先发制人，",
            "气势如虹，先声夺人，",
            "以迅雷不及掩耳之势抢先出手，"
        ]
        
        # 记录所有魔法分数的总和
        total_magic_power = 0
        
        # 一击必胜模式，只有一回合
        self.rounds = 1
        
        # 确定当前回合的攻击者和防御者
        if current_attacker == "player1":
            attacker = self.player1
            defender = self.player2
        else:
            attacker = self.player2
            defender = self.player1
        
        # 选择咒语
        spell = self.select_spell()
        
        # 记录使用的魔法分数
        total_magic_power += spell["power"]
        attacker["spells"].append(spell)
        
        # 先手介绍与咒语专属攻击描述组合在一起
        first_move_desc = random.choice(first_move_descriptions)
        # 从咒语的专属攻击描述中随机选择一个
        spell_attack_desc = random.choice(spell["attack_desc"])
        attack_info = f"🎲 {attacker['name']} {first_move_desc}{spell_attack_desc} {spell['name']}{spell['desc']}"
        self.steps.append(attack_info)
        
        # 尝试防御
        defense_success, defense = self.attempt_defense()
        
        if defense_success:
            # 防御成功，使用防御咒语的专属描述
            defense_desc = random.choice(defense["defense_desc"])
            defense_info = f"{defender['name']} {defense_desc}，使用 {defense['name']}{defense['desc']} 防御成功！"
            self.steps.append(defense_info)
            
            # 记录防御使用的魔法分数
            for defense_spell in self.defense_spells:
                if defense_spell["name"] == defense["name"]:
                    total_magic_power += 20  # 防御魔法固定20分
                    break
                        
            # 转折描述与反击描述组合
            counter_transition = [
                "防御成功后立即抓住机会反击，",
                "挡下攻击的同时，立刻准备反攻，",
                "借着防御的势头，迅速转为攻势，",
                "一个漂亮的防御后，立刻发起反击，",
                "丝毫不给对手喘息的机会，立即反击，"
            ]
            
            # 反制：防守方变为攻击方
            counter_spell = self.select_spell()
            
            # 记录反制使用的魔法分数
            total_magic_power += counter_spell["power"]
            defender["spells"].append(counter_spell)
                
            # 转折与咒语专属反击描述组合在一起
            counter_transition_desc = random.choice(counter_transition)
            # 从反制咒语的专属攻击描述中随机选择一个
            counter_spell_attack_desc = random.choice(counter_spell["attack_desc"])
            counter_info = f"{defender['name']} {counter_transition_desc}{counter_spell_attack_desc} {counter_spell['name']}{counter_spell['desc']}"
            self.steps.append(counter_info)
            
            # 显示反击造成的伤害描述
            counter_damage_desc = random.choice(counter_spell["damage_desc"])
            if current_attacker == "player1":
                damage_info = f"{self.player1['name']} {counter_damage_desc}！"
            else:
                damage_info = f"{self.player2['name']} {counter_damage_desc}！"
            self.steps.append(damage_info)
            
            # 防御成功并反制，原攻击者直接失败
            if current_attacker == "player1":
                self.player1["hp"] = 0
                winner, loser = self.player2, self.player1
            else:
                self.player2["hp"] = 0
                winner, loser = self.player1, self.player2
        else:
            # 防御失败，直接被击败
            # 从攻击咒语的专属伤害描述中随机选择一个
            damage_desc = random.choice(spell["damage_desc"])
            damage_info = f"{defender['name']} {damage_desc}！"
            self.steps.append(damage_info)
            
            if current_attacker == "player1":
                self.player2["hp"] = 0
                winner, loser = self.player1, self.player2
            else:
                self.player1["hp"] = 0
                winner, loser = self.player2, self.player1
        
        # --- 修改：获取胜利者和失败者的最新数据 ---
        # 在决斗结束后，重新获取双方数据以确保道具数量是当前的
        winner_data = rank_system.get_player_data(winner["name"])
        loser_data = rank_system.get_player_data(loser["name"])
        # ---------------------------------------
        
        # --- 修改：道具效果处理逻辑 ---
        used_item_winner = None # 记录胜利者使用的道具
        used_item_loser = None  # 记录失败者使用的道具
        winner_points = total_magic_power # 基础胜利积分
        loser_points = total_magic_power  # 基础失败扣分
        
        # 检查失败者是否有魔法石 - 失败不扣分
        if loser_data["items"].get("magic_stone", 0) > 0:
            self.steps.append(f"💎 {loser['name']} 使用了魔法石，虽然失败但是痊愈了！")
            used_item_loser = "magic_stone"
            loser_points = 0  # 不扣分
        
        # 检查胜利者是否有老魔杖 - 胜利积分×5 (独立于魔法石判断)
        if winner_data["items"].get("elder_wand", 0) > 0:
            # 如果失败者没用魔法石，才显示胜利加成信息（避免信息重复）
            if used_item_loser != "magic_stone":
                self.steps.append(f"🪄 {winner['name']} 使用了老魔杖，魔法威力增加了五倍！")
            else: # 如果失败者用了魔法石，补充说明胜利者也用了老魔杖
                 self.steps.append(f"🪄 同时，{winner['name']} 使用了老魔杖，得分加倍！")
            used_item_winner = "elder_wand"
            winner_points *= 5 # 积分乘以5
        
        # --- 整合使用的道具信息 ---
        # 注意：record_duel_result 目前只支持记录一个 used_item
        # 为了兼容，优先记录影响积分计算的道具
        final_used_item = used_item_winner or used_item_loser # 优先记录胜利者道具，其次失败者道具
        # --------------------------
        
        # 使用 record_duel_result 方法记录结果并更新数据库
        try:
            # 调用新的记录结果方法，它会处理积分更新、道具消耗和历史记录
            # **注意：需要修改 record_duel_result 来正确处理道具消耗**
            actual_winner_points, actual_loser_points = rank_system.record_duel_result(
                winner=winner["name"],
                loser=loser["name"],
                winner_points=winner_points,
                loser_points=loser_points, # 传递可能为0的扣分值
                total_magic_power=total_magic_power,
                used_item=final_used_item # 传递最终决定的使用道具
            )
            logger_duel.info(f"数据库更新成功: 胜者 {winner['name']} +{actual_winner_points}, 败者 {loser['name']} -{actual_loser_points}")
        except Exception as e:
            logger_duel.error(f"调用 record_duel_result 时发生错误: {e}", exc_info=True)
            self.steps.append(f"⚠️ 保存决斗结果时发生错误: {e}")
        
        # 获取胜利者当前排名
        rank, _ = rank_system.get_player_rank(winner["name"])
        rank_text = f"第{rank}名" if rank else "暂无排名"
        
        # 重新获取玩家数据以显示正确的道具数量 (在调用 record_duel_result 后获取)
        updated_winner_data = rank_system.get_player_data(winner["name"])
        updated_loser_data = rank_system.get_player_data(loser["name"])
        
        # 选择胜利描述
        victory_desc = random.choice(self.victory_descriptions)
        
        # 结果信息
        result = (
            f"🏆 {winner['name']} {victory_desc}！\n\n"
            f"积分: {winner['name']} +{winner_points}分 ({rank_text})\n" # 显示计算出的得分
            f"{loser['name']} -{loser_points}分" # 显示计算出的扣分 (可能为0)
        )
        
        # 如果使用了道具，显示剩余次数
        if used_item_winner == "elder_wand":
            result += f"\n\n📦 {winner['name']} 剩余老魔杖: {updated_winner_data['items'].get('elder_wand', 0)}次"
        if used_item_loser == "magic_stone":
             result += f"\n\n📦 {loser['name']} 剩余魔法石: {updated_loser_data['items'].get('magic_stone', 0)}次"
        # 如果开局隐身衣获胜，这里不会执行
        
        # 添加结果
        self.steps.append(result)
        return self.steps
    
    # --- 新增：处理隐身衣直接获胜的辅助方法 ---
    def _handle_direct_win(self, rank_system, winner, loser, winner_points, loser_points, used_item, winner_original_data):
        """处理因隐身衣直接获胜的情况，更新数据库并格式化消息"""
        try:
            # 直接调用 record_duel_result 来处理数据库更新
            # 注意：这里 total_magic_power 为 0，因为没有进行魔法对决
            rank_system.record_duel_result(
                winner=winner["name"],
                loser=loser["name"],
                winner_points=winner_points,
                loser_points=loser_points,
                total_magic_power=0, # 隐身衣获胜没有魔法力计算
                used_item=used_item
            )
            logger_duel.info(f"{winner['name']} 使用隐身衣击败 {loser['name']}，积分 +{winner_points}")

            # 重新获取更新后的玩家数据以显示剩余道具
            updated_winner_data = rank_system.get_player_data(winner["name"])

        except sqlite3.Error as e:
            logger_duel.error(f"处理隐身衣胜利时数据库出错: {e}", exc_info=True)
            self.steps.append(f"⚠️ 处理隐身衣胜利时遇到数据库问题: {e}")
            # 数据库出错时，仍使用原始数据显示结果，避免程序崩溃
            updated_winner_data = winner_original_data
        except Exception as e: # 捕获其他可能的异常
             logger_duel.error(f"处理隐身衣胜利时发生未知错误: {e}", exc_info=True)
             self.steps.append(f"⚠️ 处理隐身衣胜利时发生内部错误: {e}")
             updated_winner_data = winner_original_data

        # 获取胜利者当前排名
        rank, _ = rank_system.get_player_rank(winner["name"])
        rank_text = f"第{rank}名" if rank else "暂无排名"

        # 添加结果
        result = (
            f"🏆 {winner['name']} 使用隐身衣获胜！\n\n"
            f"积分: {winner['name']} +{winner_points}分 ({rank_text})\n"
            f"{loser['name']} -{loser_points}分\n\n"
            f"📦 剩余隐身衣: {updated_winner_data['items'].get('invisibility_cloak', 0)}次"
        )
        self.steps.append(result)
        return self.steps
    # --- 辅助方法结束 ---

def start_duel(player1: str, player2: str, group_id=None, player1_is_challenger=True) -> List[str]:
    """
    启动一场决斗
    
    Args:
        player1: 玩家1的名称
        player2: 玩家2的名称
        group_id: 群组ID，必须提供
        player1_is_challenger: 玩家1是否为挑战发起者
        
    Returns:
        List[str]: 决斗过程的步骤
    """
    # 确保只在群聊中决斗
    if not group_id:
        return ["❌ 决斗功能只支持群聊"]
        
    try:
        duel = HarryPotterDuel(player1, player2, group_id, player1_is_challenger)
        return duel.start_duel()
    except Exception as e:
        logging.error(f"决斗过程中发生错误: {e}")
        return [f"决斗过程中发生错误: {e}"]

def get_rank_list(top_n: int = 10, group_id=None) -> str:
    """获取排行榜信息
    
    Args:
        top_n: 返回前几名
        group_id: 群组ID，必须提供
    """
    # 确保只在群聊中获取排行榜
    if not group_id:
        return "❌ 决斗排行榜功能只支持群聊"
        
    try:
        rank_system = DuelRankSystem(group_id)
        ranks = rank_system.get_rank_list(top_n)
        
        if not ranks:
            return "📊 决斗排行榜还没有数据"
        
        result = [f"📊 本群决斗排行榜 Top {len(ranks)}"]
        for i, player in enumerate(ranks):
            medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            win_rate = int((player["wins"] / player["total_matches"]) * 100) if player["total_matches"] > 0 else 0
            result.append(f"{medal} {player['name']}: {player['score']}分 ({player['wins']}/{player['losses']}/{win_rate}%)")
            
        return "\n".join(result)
    except Exception as e:
        logging.error(f"获取排行榜失败: {e}")
        return f"获取排行榜失败: {e}"

def get_player_stats(player_name: str, group_id=None) -> str:
    """获取玩家战绩
    
    Args:
        player_name: 玩家名称
        group_id: 群组ID，必须提供
    """
    # 确保只在群聊中获取战绩
    if not group_id:
        return "❌ 决斗战绩查询功能只支持群聊"
        
    try:
        rank_system = DuelRankSystem(group_id)
        rank, player_data = rank_system.get_player_rank(player_name)
        
        win_rate = int((player_data["wins"] / player_data["total_matches"]) * 100) if player_data["total_matches"] > 0 else 0
        
        result = [
            f"📊 {player_name} 的本群决斗战绩",
            f"排名: {rank if rank else '暂无排名'}",
            f"积分: {player_data['score']}",
            f"胜场: {player_data['wins']}",
            f"败场: {player_data['losses']}",
            f"总场次: {player_data['total_matches']}",
            f"胜率: {win_rate}%"
        ]
        
        return "\n".join(result)
    except Exception as e:
        logging.error(f"获取玩家战绩失败: {e}")
        return f"获取玩家战绩失败: {e}"

def change_player_name(old_name: str, new_name: str, group_id=None) -> str:
    """更改玩家名称
    
    Args:
        old_name: 旧名称
        new_name: 新名称
        group_id: 群组ID，必须提供
        
    Returns:
        str: 操作结果消息
    """
    # 确保只在群聊中更改玩家名称
    if not group_id:
        return "❌ 更改玩家名称功能只支持群聊"
        
    try:
        rank_system = DuelRankSystem(group_id)
        result = rank_system.change_player_name(old_name, new_name)
        
        if result:
            return f"✅ 已成功将本群中的玩家 \"{old_name}\" 改名为 \"{new_name}\""
        else:
            return f"❌ 改名失败：请确认 \"{old_name}\" 在本群中有战绩记录，且 \"{new_name}\" 名称未被使用"
    except Exception as e:
        logging.error(f"更改玩家名称失败: {e}")
        return f"❌ 更改玩家名称失败: {e}"

class DuelManager:
    """决斗管理器，处理决斗线程和消息发送"""
    
    def __init__(self, message_sender_func):
        """
        初始化决斗管理器
        
        Args:
            message_sender_func: 消息发送函数，接收(message, receiver)两个参数
        """
        self.message_sender = message_sender_func
        self._duel_thread = None
        self._duel_lock = Lock()
        self.LOG = logging.getLogger("DuelManager")
    
    def send_duel_message(self, msg: str, receiver: str) -> None:
        """发送决斗消息
        
        Args:
            msg: 消息内容
            receiver: 接收者ID（通常是群ID）
        """
        try:
            self.LOG.info(f"发送决斗消息 To {receiver}: {msg[:20]}...")
            self.message_sender(msg, receiver)
        except Exception as e:
            self.LOG.error(f"发送决斗消息失败: {e}")
    
    def run_duel(self, challenger_name, opponent_name, receiver, is_group=False):
        """在单独线程中运行决斗
        
        Args:
            challenger_name: 挑战者名称
            opponent_name: 对手名称
            receiver: 消息接收者(群id)
            is_group: 是否是群聊
        """
        try:
            # 确保只在群聊中运行决斗
            if not is_group:
                self.send_duel_message("❌ 决斗功能只支持群聊", receiver)
                return
                
            # 开始决斗
            # 传递群组ID参数
            group_id = receiver
            duel_steps = start_duel(challenger_name, opponent_name, group_id, True)  # challenger_name是发起者
            
            # 逐步发送决斗过程
            for step in duel_steps:
                self.send_duel_message(step, receiver)
                time.sleep(1.5)  # 每步之间添加适当延迟
        except Exception as e:
            self.LOG.error(f"决斗过程中发生错误: {e}")
            self.send_duel_message(f"决斗过程中发生错误: {e}", receiver)
        finally:
            # 释放决斗线程
            with self._duel_lock:
                self._duel_thread = None
            self.LOG.info("决斗线程已结束并销毁")
    
    def start_duel_thread(self, challenger_name, opponent_name, receiver, is_group=False):
        """启动决斗线程
        
        Args:
            challenger_name: 挑战者名称
            opponent_name: 对手名称
            receiver: 消息接收者
            is_group: 是否是群聊
            
        Returns:
            bool: 是否成功启动决斗线程
        """
        with self._duel_lock:
            if self._duel_thread is not None and self._duel_thread.is_alive():
                return False
            
            self._duel_thread = Thread(
                target=self.run_duel,
                args=(challenger_name, opponent_name, receiver, is_group),
                daemon=True
            )
            self._duel_thread.start()
            return True
    
    def is_duel_running(self):
        """检查是否有决斗正在进行
        
        Returns:
            bool: 是否有决斗正在进行
        """
        with self._duel_lock:
            return self._duel_thread is not None and self._duel_thread.is_alive()

# --- 新增：偷袭成功/失败的随机句子 ---
SNEAK_ATTACK_SUCCESS_MESSAGES = [
    "趁其不备，{attacker} 悄悄从 {target} 的口袋里摸走了 {points} 积分！真是个小机灵鬼！👻",
    "月黑风高夜，正是下手时！{attacker} 成功偷袭 {target}，顺走了 {points} 积分！🌙",
    "{target} 一时大意，被 {attacker} 抓住了破绽，损失了 {points} 积分！💸",
    "神不知鬼不觉，{attacker} 从 {target} 那里\"借\"来了 {points} 积分！🤫",
    "手法娴熟！{attacker} 像一阵风一样掠过，{target} 发现时已经少了 {points} 积分！💨",
]

SNEAK_ATTACK_FAILURE_MESSAGES = [
    "哎呀！{attacker} 的鬼祟行踪被 {target} 发现了，偷袭失败！👀",
    "{target} 警惕性很高，{attacker} 的小动作没能得逞。🛡️",
    "差点就成功了！可惜 {attacker} 不小心弄出了声响，被 {target} 逮个正着！🔔",
    "{target} 哼了一声：\"就这点伎俩？\" {attacker} 的偷袭计划泡汤了。😏",
    "运气不佳，{attacker} 刚伸手就被 {target} 的护身符弹开了，偷袭失败！✨",
    "{attacker} 脚底一滑，在 {target} 面前摔了个狗啃泥，偷袭什么的早就忘光了！🤣",
    "{target} 突然转身，和 {attacker} 对视，场面一度十分尴尬... 偷袭失败！😅",
    "{attacker} 刚准备动手，{target} 的口袋里突然钻出一只嗅嗅，叼走了 {attacker} 的...嗯？偷袭失败！👃",
    "{target} 拍了拍 {attacker} 的肩膀：\"兄弟，想啥呢？\"，{attacker} 只好悻悻收手。🤝",
    "一阵妖风刮过，把 {attacker} 准备用来偷袭的工具吹跑了... 时运不济啊！🌬️",
    "{attacker} 发现 {target} 的口袋是画上去的！可恶，被摆了一道！🖌️",
]

# --- 新增：偷到道具的随机句子 ---
SNEAK_ATTACK_ITEM_SUCCESS_MESSAGES = [
    "趁乱摸鱼！{attacker} 竟然从 {target} 身上摸走了一件 {item_name_cn}！真是妙手空空！👏",
    "运气爆棚！{attacker} 偷袭失败，但顺走了 {target} 的一件 {item_name_cn}！🥳",
    "{target} 光顾着得意，没注意到 {attacker} 悄悄拿走了一件 {item_name_cn}！🤭",
    "失之东隅，收之桑榆。{attacker} 虽然没偷到分，但拐走了一件 {item_name_cn}！🎁",
    "神偷再现！{attacker} 从 {target} 那里顺走了一件 {item_name_cn}！🔮",
]

# --- 新增：道具英文名到中文名的映射 ---
ITEM_NAME_MAP = {
    "elder_wand": "老魔杖 🪄",
    "magic_stone": "魔法石 💎",
    "invisibility_cloak": "隐身衣 🧥"
}

# --- 新增：处理偷袭逻辑的函数 ---
def attempt_sneak_attack(attacker_name: str, target_name: str, group_id: str) -> str:
    """
    处理玩家尝试偷袭另一个玩家的逻辑

    Args:
        attacker_name: 偷袭者名称
        target_name: 被偷袭者名称
        group_id: 群组ID

    Returns:
        str: 偷袭结果的消息
    """
    if not group_id:
        return "❌ 偷袭功能也只支持群聊哦。"

    try:
        rank_system = DuelRankSystem(group_id)

        # 检查玩家是否存在
        with rank_system._db_lock:
            with rank_system._get_db_conn() as conn:
                cursor = conn.cursor()
                
                # 检查偷袭者是否存在
                cursor.execute(
                    "SELECT COUNT(*) as count FROM duel_players WHERE group_id = ? AND player_name = ?",
                    (group_id, attacker_name)
                )
                if cursor.fetchone()["count"] == 0:
                    return f"❌ 偷袭发起者 {attacker_name} 还没有决斗记录。"
                
                # 检查目标是否存在
                cursor.execute(
                    "SELECT COUNT(*) as count FROM duel_players WHERE group_id = ? AND player_name = ?",
                    (group_id, target_name)
                )
                if cursor.fetchone()["count"] == 0:
                    return f"❌ 目标 {target_name} 还没有决斗记录。"
                
                # 获取偷袭者排名
                cursor.execute("""
                SELECT COUNT(*) + 1 as rank FROM duel_players 
                WHERE group_id = ? AND score > (
                    SELECT score FROM duel_players 
                    WHERE group_id = ? AND player_name = ?
                )""", (group_id, group_id, attacker_name))
                attacker_rank_result = cursor.fetchone()
                attacker_rank = attacker_rank_result["rank"] if attacker_rank_result else None
                
                # 获取目标排名
                cursor.execute("""
                SELECT COUNT(*) + 1 as rank FROM duel_players 
                WHERE group_id = ? AND score > (
                    SELECT score FROM duel_players 
                    WHERE group_id = ? AND player_name = ?
                )""", (group_id, group_id, target_name))
                target_rank_result = cursor.fetchone()
                target_rank = target_rank_result["rank"] if target_rank_result else None
                
                # 获取总玩家数
                cursor.execute("SELECT COUNT(*) as count FROM duel_players WHERE group_id = ?", (group_id,))
                total_players = cursor.fetchone()["count"]
                
                # 计算成功率
                success_prob = 0.3  # 基础成功率 30%
                
                # 计算概率加成（仅当双方都有排名且总人数大于0时）
                if attacker_rank is not None and target_rank is not None and total_players > 0:
                    if attacker_rank > target_rank:  # 偷袭者排名更低
                        rank_difference = attacker_rank - target_rank
                        # 排名差值影响概率，最多增加 40%
                        success_prob += min((rank_difference / total_players) * 0.4, 0.4)
                    # else: 偷袭者排名更高或相同，使用基础概率 30%

                # 确保概率在 0 到 1 之间
                success_prob = max(0, min(1, success_prob))

                # 格式化概率显示为0-100%的百分比
                prob_percent = success_prob * 100
                logger_duel.info(f"偷袭计算: {attacker_name}({attacker_rank}) vs {target_name}({target_rank}), 总人数: {total_players}, 成功率: {prob_percent:.1f}%")

                roll_successful = random.random() < success_prob
                points_exchanged_successfully = False  # 标记是否成功转移了分数

                # 决定偷袭是否成功
                if roll_successful:
                    # --- 偷袭概率判定成功，尝试计算分数转移 ---
                    # 获取分数差
                    cursor.execute("""
                    SELECT t1.score as attacker_score, t2.score as target_score
                    FROM duel_players t1, duel_players t2
                    WHERE t1.group_id = ? AND t1.player_name = ? 
                      AND t2.group_id = ? AND t2.player_name = ?
                    """, (group_id, attacker_name, group_id, target_name))
                    result = cursor.fetchone()
                    # 添加检查，以防万一查询不到结果
                    if not result:
                        logger_duel.error(f"偷袭成功后查询分数失败: {attacker_name} vs {target_name}")
                        return "❌ 处理偷袭时发生内部错误：无法获取玩家分数。"
                        
                    attacker_score = result["attacker_score"]
                    target_score = result["target_score"]
                    
                    # 1. 计算潜在偷取分数
                    score_difference = abs(attacker_score - target_score)
                    potential_points_stolen = max(random.randint(10, 50), int(score_difference * 0.1))  # 偷取(10-50)或分数差的10%，取最大值

                    # 2. 计算目标实际能损失的最大分数 (最低保留1分)
                    max_points_target_can_lose = max(0, target_score - 1)

                    # 3. 确定实际交换的分数
                    actual_points_exchanged = min(potential_points_stolen, max_points_target_can_lose)

                    # 只有实际交换分数大于0时才更新数据库和记录历史
                    if actual_points_exchanged > 0:
                        # 更新分数 (零和交换)
                        cursor.execute(
                            "UPDATE duel_players SET score = score + ? WHERE group_id = ? AND player_name = ?",
                            (actual_points_exchanged, group_id, attacker_name)
                        )
                        cursor.execute(
                            "UPDATE duel_players SET score = score - ? WHERE group_id = ? AND player_name = ?",
                            (actual_points_exchanged, group_id, target_name)
                        )
                        
                        # 移除了记录到历史记录的代码
                        
                        # 提交事务
                        conn.commit()
                        logger_duel.info(f"偷袭成功: {attacker_name} 偷取 {target_name} {actual_points_exchanged} 分 (原目标分数: {target_score}, 潜在偷取: {potential_points_stolen})")
                        
                        # 选择并格式化成功消息 (使用 actual_points_exchanged)
                        message_template = random.choice(SNEAK_ATTACK_SUCCESS_MESSAGES)
                        result_message = message_template.format(attacker=attacker_name, target=target_name, points=actual_points_exchanged)
                        
                        points_exchanged_successfully = True  # 标记成功转移了分数
                        return result_message  # 只有在成功转移分数时才直接返回
                    else:
                        # 如果实际交换分数为0 (例如目标只有1分)
                        logger_duel.info(f"偷袭概率判定成功但未发生分数转移: {attacker_name} 偷袭 {target_name} (目标分数: {target_score})，转为尝试偷道具...")
                        # 不设置 points_exchanged_successfully = True
                        # 不返回，继续执行下面的偷道具逻辑
                
                # --- 如果偷袭概率判定失败，或者判定成功但未转移分数，则尝试偷道具 ---
                if not points_exchanged_successfully:  # 这个条件覆盖了概率判定失败和概率判定成功但未转移分数两种情况
                    # 根据情况选择日志消息
                    if not roll_successful:  # 如果是概率判定失败的情况
                        logger_duel.info(f"偷袭分数失败: {attacker_name} 偷袭 {target_name}. 尝试根据目标道具数量计算偷道具概率...")

                    # --- 修改：提前获取目标道具信息以计算概率 ---
                    cursor.execute("""
                    SELECT elder_wand, magic_stone, invisibility_cloak
                    FROM duel_players
                    WHERE group_id = ? AND player_name = ?
                    """, (group_id, target_name))
                    target_items_result = cursor.fetchone() # 使用新变量名避免混淆

                    item_steal_prob = 0.0 # 初始化概率为 0
                    total_items_count = 0

                    if target_items_result:
                        # 计算总道具数量
                        total_items_count = (target_items_result["elder_wand"] +
                                             target_items_result["magic_stone"] +
                                             target_items_result["invisibility_cloak"])

                        # 计算动态概率，每件道具增加 1%
                        item_steal_prob = total_items_count * 0.01
                        logger_duel.info(f"目标共有 {total_items_count} 件道具，计算出的偷道具概率为: {item_steal_prob*100:.1f}% ")
                    else:
                         # 如果查询不到目标道具信息（理论上不应发生，因为前面检查过玩家存在）
                         logger_duel.warning(f"未能查询到目标 {target_name} 的道具信息，无法计算偷道具概率。")
                         item_steal_prob = 0.0 # 无法计算则概率为0

                    # --- 使用计算出的 item_steal_prob 进行判断 ---
                    if total_items_count > 0 and random.random() < item_steal_prob:
                        # --- 概率判定成功，且目标确实有道具可偷 ---
                        logger_duel.info(f"偷道具判定成功 (概率 {item_steal_prob*100:.1f}%)，开始选择道具...")
                        
                        # --- 复用之前获取的 target_items_result 构建列表 ---
                        available_item_names = []
                        item_weights = []
                            
                        if target_items_result["elder_wand"] > 0:
                            available_item_names.append("elder_wand")
                            item_weights.append(target_items_result["elder_wand"])
                        
                        if target_items_result["magic_stone"] > 0:
                            available_item_names.append("magic_stone")
                            item_weights.append(target_items_result["magic_stone"])
                        
                        if target_items_result["invisibility_cloak"] > 0:
                            available_item_names.append("invisibility_cloak")
                            item_weights.append(target_items_result["invisibility_cloak"])
                        
                        # 这个检查理论上可以省略，因为前面 total_items_count > 0 已经保证了列表非空
                        # 但为了代码健壮性可以保留
                        if available_item_names:
                            # 根据权重随机选择一件道具
                            item_stolen = random.choices(available_item_names, weights=item_weights, k=1)[0]
                            item_name_cn = ITEM_NAME_MAP.get(item_stolen, item_stolen)
                            
                            # 更新数据库：目标减道具，攻击者加道具
                            sql_update_target = f"UPDATE duel_players SET {item_stolen} = MAX(0, {item_stolen} - 1) WHERE group_id = ? AND player_name = ?"
                            sql_update_attacker = f"UPDATE duel_players SET {item_stolen} = {item_stolen} + 1 WHERE group_id = ? AND player_name = ?"
                            
                            cursor.execute(sql_update_target, (group_id, target_name))
                            cursor.execute(sql_update_attacker, (group_id, attacker_name))
                            conn.commit() # 偷道具成功，提交事务
                            
                            # 选择并格式化偷道具成功消息
                            message_template = random.choice(SNEAK_ATTACK_ITEM_SUCCESS_MESSAGES)
                            result_message = message_template.format(attacker=attacker_name, target=target_name, item_name_cn=item_name_cn)
                            logger_duel.info(f"偷道具成功: {attacker_name} 偷取了 {target_name} 的 {item_stolen}")
                            # 偷到道具直接返回，不再执行后面的失败逻辑
                            return result_message
                        else:
                             # 如果因为某种原因（例如并发问题），刚才还有道具现在没了
                             logger_duel.warning(f"尝试偷取 {target_name} 道具时发现其道具列表为空，虽然 total_items_count > 0。")
                             # 这里会继续执行下面的通用失败逻辑

                    # --- 偷道具判定失败 或 目标没有任何道具 ---
                    # (包括 total_items_count 为 0 的情况, 以及 random.random() >= item_steal_prob 的情况)
                    message_template = random.choice(SNEAK_ATTACK_FAILURE_MESSAGES)
                    result_message = message_template.format(attacker=attacker_name, target=target_name)
                    if total_items_count == 0:
                         logger_duel.info(f"偷袭完全失败: {attacker_name} 偷袭 {target_name}，且目标没有任何道具。")
                    else:
                         logger_duel.info(f"偷袭完全失败: {attacker_name} 偷袭 {target_name}，未达到偷道具概率 {item_steal_prob*100:.1f}%。")
                    return result_message

    except sqlite3.Error as e:
        logger_duel.error(f"处理偷袭时发生数据库错误: {e}", exc_info=True)
        return f"处理偷袭时发生内部错误: {e}"
    except Exception as e:
        logger_duel.error(f"处理偷袭时发生未知错误: {e}", exc_info=True)
        return f"处理偷袭时发生内部错误: {e}"

