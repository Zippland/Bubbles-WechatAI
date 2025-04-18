import random
import logging
import time
import json
import os
from typing import List, Dict, Tuple, Optional, Any

# 排位积分系统
class DuelRankSystem:
    def __init__(self, group_id=None, data_file="duel_ranks.json"):
        """
        初始化排位系统
        
        Args:
            group_id: 群组ID，默认为None表示私聊
            data_file: 数据文件路径
        """
        self.group_id = group_id if group_id else "private"  # 使用"private"作为私聊标识
        self.data_file = data_file
        self.ranks = self._load_ranks()
        
        # 确保当前群组存在于数据中
        if self.group_id not in self.ranks["groups"]:
            self.ranks["groups"][self.group_id] = {
                "players": {},
                "history": []
            }
    
    def _load_ranks(self) -> Dict:
        """加载排位数据"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # 兼容旧版数据结构
                    if "groups" not in data:
                        # 转换旧数据到新格式
                        new_data = {
                            "groups": {
                                "private": {  # 旧版数据全部归入私聊组
                                    "players": data.get("players", {}),
                                    "history": data.get("history", [])
                                }
                            }
                        }
                        return new_data
                    return data
            except Exception as e:
                logging.error(f"加载排位数据失败: {e}")
                return {"groups": {}}
        return {"groups": {}}
    
    def _save_ranks(self) -> bool:
        """保存排位数据"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.ranks, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logging.error(f"保存排位数据失败: {e}")
            return False
    
    def get_player_data(self, player_name: str) -> Dict:
        """获取玩家数据，如果不存在则创建"""
        group_data = self.ranks["groups"][self.group_id]
        players = group_data["players"]
        if player_name not in players:
            players[player_name] = {
                "score": 1000,  # 初始积分
                "wins": 0,
                "losses": 0,
                "total_matches": 0
            }
        return players[player_name]
    
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
        
        # 确保为零和游戏 - 胜者得到的积分等于败者失去的积分
        winner_data["score"] += points
        winner_data["wins"] += 1
        winner_data["total_matches"] += 1
        
        loser_data["score"] = max(1, loser_data["score"] - points)  # 防止积分小于1
        loser_data["losses"] += 1
        loser_data["total_matches"] += 1
        
        # 记录对战历史
        match_record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "winner": winner,
            "loser": loser,
            "winner_hp": winner_hp,
            "rounds": rounds,
            "points": points
        }
        self.ranks["groups"][self.group_id]["history"].append(match_record)
        
        # 如果历史记录太多，保留最近的100条
        if len(self.ranks["groups"][self.group_id]["history"]) > 100:
            self.ranks["groups"][self.group_id]["history"] = self.ranks["groups"][self.group_id]["history"][-100:]
        
        # 保存数据
        self._save_ranks()
        
        return (points, points)  # 返回胜者得分和败者失分（相同）
    
    def get_rank_list(self, top_n: int = 10) -> List[Dict]:
        """获取排行榜
        
        Args:
            top_n: 返回前几名
            
        Returns:
            List[Dict]: 排行榜数据
        """
        players = self.ranks["groups"][self.group_id]["players"]
        # 按积分排序
        ranked_players = sorted(
            [{"name": name, **data} for name, data in players.items()],
            key=lambda x: x["score"],
            reverse=True
        )
        return ranked_players[:top_n]
    
    def get_player_rank(self, player_name: str) -> Tuple[Optional[int], Dict]:
        """获取玩家排名
        
        Args:
            player_name: 玩家名称
            
        Returns:
            Tuple[Optional[int], Dict]: (排名, 玩家数据)
        """
        if player_name not in self.ranks["groups"][self.group_id]["players"]:
            return None, self.get_player_data(player_name)
            
        player_data = self.ranks["groups"][self.group_id]["players"][player_name]
        rank_list = self.get_rank_list(9999)  # 获取完整排名
        
        for i, player in enumerate(rank_list):
            if player["name"] == player_name:
                return i + 1, player_data  # 排名从1开始
                
        return None, player_data  # 理论上不会到这里
    
    def change_player_name(self, old_name: str, new_name: str) -> bool:
        """更改玩家名称，保留历史战绩
        
        Args:
            old_name: 旧名称
            new_name: 新名称
            
        Returns:
            bool: 是否成功更改
        """
        group_data = self.ranks["groups"][self.group_id]
        players = group_data["players"]
        
        # 检查旧名称是否存在
        if old_name not in players:
            return False
            
        # 检查新名称是否已存在
        if new_name in players:
            return False
            
        # 复制玩家数据到新名称
        players[new_name] = players[old_name].copy()
        
        # 删除旧名称数据
        del players[old_name]
        
        # 更新历史记录中的名称
        for record in group_data["history"]:
            if record["winner"] == old_name:
                record["winner"] = new_name
            if record["loser"] == old_name:
                record["loser"] = new_name
        
        # 保存更改
        self._save_ranks()
        return True

class HarryPotterDuel:
    """决斗功能"""
    
    def __init__(self, player1, player2, group_id=None):
        """
        初始化决斗
        :param player1: 玩家1的名称
        :param player2: 玩家2的名称
        :param group_id: 群组ID，默认为None表示私聊
        """
        self.p1_name = player1
        self.p2_name = player2
        self.p1_hp = 100
        self.p2_hp = 100
        self.rounds = 0
        self.steps = []
        self.group_id = group_id  # 记录群组ID
        
        # 使用红方和蓝方替代名字
        self.red_player = {"name": self.p1_name, "hp": self.p1_hp, "emoji": "🔴"}
        self.blue_player = {"name": self.p2_name, "hp": self.p2_hp, "emoji": "🔵"}
        
        # 记录开场信息
        self.steps.append(f"⚔️ {self.red_player['emoji']} {self.red_player['name']} \nVS \n⚔️ {self.blue_player['emoji']} {self.blue_player['name']}")
        
        # 咒语列表（名称、威力、权重）- 权重越小越稀有
        self.spells = [
            {"name": "除你武器", "power": 10, "weight": 30, "desc": "🪄"},
            {"name": "昏昏倒地", "power": 15, "weight": 25, "desc": "✨"},
            {"name": "统统石化", "power": 20, "weight": 20, "desc": "💫"},
            {"name": "障碍重重", "power": 25, "weight": 15, "desc": "⚡"},
            {"name": "神锋无影", "power": 35, "weight": 10, "desc": "🗡️"},
            {"name": "钻心剜骨", "power": 45, "weight": 5, "desc": "🔥"},
            {"name": "阿瓦达索命", "power": 100, "weight": 1, "desc": "💀"}
        ]
        
        # 防御咒语列表（名称、成功率）
        self.defense_spells = [
            {"name": "盔甲护身", "success_rate": 0.3, "desc": "🛡️"},
            {"name": "除你武器", "success_rate": 0.2, "desc": "⚔️"},
            {"name": "呼神护卫", "success_rate": 0.1, "desc": "🧿"}
        ]
    
    def select_spell(self):
        """随机选择一个咒语，威力越高出现概率越低"""
        weights = [spell["weight"] for spell in self.spells]
        total_weight = sum(weights)
        normalized_weights = [w/total_weight for w in weights]
        return random.choices(self.spells, weights=normalized_weights, k=1)[0]
    
    def attempt_defense(self):
        """尝试防御，返回是否成功和使用的防御咒语"""
        defense = random.choice(self.defense_spells)
        success = random.random() < defense["success_rate"]
        return success, defense
    
    def start_duel(self):
        """开始决斗，返回决斗过程的步骤列表"""
        current_attacker = "red" if random.random() < 0.5 else "blue"
        
        battle_round_buffer = []
        round_count = 0
        
        # 持续战斗直到一方生命值为零
        while self.red_player["hp"] > 0 and self.blue_player["hp"] > 0:
            self.rounds += 1
            round_count += 1
            
            # 确定当前回合的攻击者和防御者
            if current_attacker == "red":
                attacker = self.red_player
                defender = self.blue_player
            else:
                attacker = self.blue_player
                defender = self.red_player
            
            # 选择咒语
            spell = self.select_spell()
            
            # 构建回合信息
            round_info = f"{attacker['emoji']} {spell['name']}{spell['desc']} → "
            
            # 尝试防御
            defense_success, defense = self.attempt_defense()
            
            if defense_success:
                round_info += f"{defender['emoji']} {defense['name']}{defense['desc']}"
            else:
                # 计算伤害
                damage = spell["power"]
                
                # 阿瓦达索命一击必杀
                if spell["name"] == "阿瓦达索命":
                    if current_attacker == "red":
                        self.blue_player["hp"] = 0
                    else:
                        self.red_player["hp"] = 0
                    round_info += f"{defender['emoji']} 💀 致命一击！"
                else:
                    # 伤害浮动范围1-1.5倍
                    damage = int(damage * (1 + (random.random() * 0.5)))
                    
                    # 造成伤害
                    if current_attacker == "red":
                        self.blue_player["hp"] = max(0, self.blue_player["hp"] - damage)
                    else:
                        self.red_player["hp"] = max(0, self.red_player["hp"] - damage)
                    
                    round_info += f"{defender['emoji']} 💥{damage}"
            
            # 添加到缓冲区
            battle_round_buffer.append(round_info)
            
            # 每2回合或者战斗结束时发送汇总消息
            if round_count >= 2 or self.red_player["hp"] <= 0 or self.blue_player["hp"] <= 0:
                summary = "\n".join(battle_round_buffer)
                self.steps.append(f"{summary}")
                battle_round_buffer = []
                round_count = 0
            
            # 切换攻击者
            current_attacker = "blue" if current_attacker == "red" else "red"
        
        # 决斗结束，确定赢家和积分变化
        rank_system = DuelRankSystem(self.group_id)
        
        if self.red_player["hp"] <= 0:
            winner, loser = self.blue_player, self.red_player
        else:
            winner, loser = self.red_player, self.blue_player
        
        # 更新积分
        winner_points, loser_points = rank_system.update_score(
            winner["name"], 
            loser["name"], 
            winner["hp"],
            self.rounds
        )
        
        # 获取胜利者当前排名
        rank, player_data = rank_system.get_player_rank(winner["name"])
        rank_text = f"当前排名: 第{rank}位" if rank else "暂无排名"
        
        # 本场地点
        location_text = "私聊决斗" if self.group_id is None else f"群聊决斗"
        
        # 结果信息
        result = (
            f"🏆 {winner['emoji']} {winner['name']} 获胜！\n"
            f"剩余生命值: ❤️ {winner['hp']} | 回合数: {self.rounds}\n\n"
            f"📊 积分变化 ({location_text}):\n"
            f"{winner['emoji']} {winner['name']} +{winner_points} 分 ({player_data['score']}分)\n"
            f"{loser['emoji']} {loser['name']} -{loser_points} 分\n"
            f"{rank_text}"
        )
        
        # 添加结果
        self.steps.append(result)
        return self.steps

def start_duel(player1: str, player2: str, group_id=None) -> List[str]:
    """
    启动一场决斗
    
    Args:
        player1: 玩家1的名称
        player2: 玩家2的名称
        group_id: 群组ID，默认为None表示私聊
        
    Returns:
        List[str]: 决斗过程的步骤
    """
    try:
        duel = HarryPotterDuel(player1, player2, group_id)
        return duel.start_duel()
    except Exception as e:
        logging.error(f"决斗过程中发生错误: {e}")
        return [f"决斗过程中发生错误: {e}"]

def get_rank_list(top_n: int = 10, group_id=None) -> str:
    """获取排行榜信息
    
    Args:
        top_n: 返回前几名
        group_id: 群组ID，默认为None表示私聊
    """
    try:
        rank_system = DuelRankSystem(group_id)
        ranks = rank_system.get_rank_list(top_n)
        
        if not ranks:
            return "📊 决斗排行榜还没有数据"
        
        location_text = "私聊" if group_id is None else "本群"
        result = [f"📊 {location_text}决斗排行榜 Top {len(ranks)}"]
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
        group_id: 群组ID，默认为None表示私聊
    """
    try:
        rank_system = DuelRankSystem(group_id)
        rank, player_data = rank_system.get_player_rank(player_name)
        
        win_rate = int((player_data["wins"] / player_data["total_matches"]) * 100) if player_data["total_matches"] > 0 else 0
        
        location_text = "私聊" if group_id is None else "本群"
        result = [
            f"📊 {player_name} 的{location_text}决斗战绩",
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
        group_id: 群组ID，默认为None表示私聊
        
    Returns:
        str: 操作结果消息
    """
    try:
        rank_system = DuelRankSystem(group_id)
        result = rank_system.change_player_name(old_name, new_name)
        
        location_text = "私聊" if group_id is None else "本群"
        
        if result:
            return f"✅ 已成功将{location_text}中的玩家 \"{old_name}\" 改名为 \"{new_name}\"，历史战绩已保留"
        else:
            return f"❌ 改名失败：请确认 \"{old_name}\" 在{location_text}中有战绩记录，且 \"{new_name}\" 名称未被使用"
    except Exception as e:
        logging.error(f"更改玩家名称失败: {e}")
        return f"❌ 更改玩家名称失败: {e}"
