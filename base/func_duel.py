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
            group_id: 群组ID
            data_file: 数据文件路径
        """
        # 确保group_id不为空，现在只支持群聊
        if not group_id:
            raise ValueError("决斗功能只支持群聊")
            
        self.group_id = group_id
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
                "total_matches": 0,
                "items": {  # 新增道具字段
                    "elder_wand": 0,  # 老魔杖次数
                    "magic_stone": 0,  # 魔法石次数
                    "invisibility_cloak": 0  # 隐身衣次数
                }
            }
        # 兼容旧数据，确保有items字段
        if "items" not in players[player_name]:
            players[player_name]["items"] = {
                "elder_wand": 0,
                "magic_stone": 0,
                "invisibility_cloak": 0
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
    
    def update_score_by_magic(self, winner: str, loser: str, magic_power: int) -> Tuple[int, int]:
        """根据魔法分数更新玩家积分
        
        Args:
            winner: 胜利者名称
            loser: 失败者名称
            magic_power: 决斗中所有参与者使用的魔法总分数
            
        Returns:
            Tuple[int, int]: (胜利者获得积分, 失败者失去积分)
        """
        # 获取玩家数据
        winner_data = self.get_player_data(winner)
        loser_data = self.get_player_data(loser)
        
        # 使用魔法总分作为积分变化值
        points = magic_power
        
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
            "magic_power": magic_power,
            "points": points
        }
        self.ranks["groups"][self.group_id]["history"].append(match_record)
        
        # 如果历史记录太多，保留最近的100条
        if len(self.ranks["groups"][self.group_id]["history"]) > 100:
            self.ranks["groups"][self.group_id]["history"] = self.ranks["groups"][self.group_id]["history"][-100:]
        
        # 保存数据
        self._save_ranks()
        
        return (points, points)  # 返回胜者得分和败者失分（相同）

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
            # Boss战胜率极低，设为1%
            self.player_win_chance = 0.01
            # 添加Boss战提示信息
            self.steps.append("⚠️ Boss战开始！挑战强大的魔法师泡泡！")
            self.steps.append("胜率极低，失败将扣除10分，但如果获胜，将获得一件珍贵的魔法装备！")
            
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
                
                # 获取积分系统实例
                rank_system = DuelRankSystem(self.group_id)
                
                # 随机获得一件装备
                items = ["elder_wand", "magic_stone", "invisibility_cloak"]
                item_names = {"elder_wand": "老魔杖", "magic_stone": "魔法石", "invisibility_cloak": "隐身衣"}
                
                # 更新玩家装备，获得所有三种死亡圣器各一次使用机会
                player_data = rank_system.get_player_data(winner["name"])
                player_data["items"]["elder_wand"] += 1
                player_data["items"]["magic_stone"] += 1
                player_data["items"]["invisibility_cloak"] += 1
                
                # 胜利积分固定为200分
                winner_points = 200
                
                # 更新玩家数据
                player_data["score"] += winner_points
                player_data["wins"] += 1
                player_data["total_matches"] += 1
                
                # 记录对战历史
                match_record = {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "winner": winner["name"],
                    "loser": loser["name"],
                    "is_boss_fight": True,
                    "points": winner_points,
                    "items_gained": items  # 记录获得了所有道具
                }
                rank_system.ranks["groups"][self.group_id]["history"].append(match_record)
                
                # 保存数据
                rank_system._save_ranks()
                
                # 获取胜利者当前排名
                rank, _ = rank_system.get_player_rank(winner["name"])
                rank_text = f"第{rank}名" if rank else "暂无排名"
                
                # 添加获得装备的信息
                result = (
                    f"🏆 {winner['name']} 以不可思议的实力击败了强大的Boss泡泡！\n\n"
                    f"获得了三件死亡圣器！\n"
                    f"🪄 老魔杖：下次决斗获胜时积分×5\n"
                    f"💎 魔法石：下次决斗失败时不扣分\n"
                    f"🧥 隐身衣：下次决斗自动获胜\n\n"
                    f"积分: +{winner_points}分 ({rank_text})"
                )
                
                self.steps.append(result)
                return self.steps
                
            else:  # 玩家输了
                winner, loser = self.player2, self.player1
                
                # 添加失败结局描述
                defeat_end = [
                    f"💀 最终，泡泡施放了一道无法抵挡的魔法，{loser['name']}被击倒在地！",
                    f"⚰️ 泡泡展现出真正的实力，一击定胜负，{loser['name']}被魔法能量淹没！",
                    f"☠️ {loser['name']}的魔杖被击飞，不得不认输，泡泡的强大实力不容小觑！"
                ]
                self.steps.append(random.choice(defeat_end))
                
                # 获取积分系统实例
                rank_system = DuelRankSystem(self.group_id)
                
                # 特殊的积分扣除
                player_data = rank_system.get_player_data(loser["name"])
                player_data["score"] = max(1, player_data["score"] - 10)  # 固定扣10分
                player_data["losses"] += 1
                player_data["total_matches"] += 1
                
                # 记录对战历史
                match_record = {
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "winner": winner["name"],
                    "loser": loser["name"],
                    "is_boss_fight": True,
                    "points": 10  # 扣10分
                }
                rank_system.ranks["groups"][self.group_id]["history"].append(match_record)
                
                # 保存数据
                rank_system._save_ranks()
                
                result = (
                    f"💀 {loser['name']} 不敌强大的Boss泡泡！\n\n"
                    f"积分: -10分\n"
                    f"再接再厉，下次挑战吧！"
                )
                
                self.steps.append(result)
                return self.steps
        
        # 普通决斗流程，保持原有逻辑
        # 根据决斗发起者设置先手概率
        if self.player1["is_challenger"]:
            first_attack_prob = 0.6 if self.player1["is_challenger"] else 0.4
            current_attacker = "player1" if random.random() < first_attack_prob else "player2"
        else:
            first_attack_prob = 0.6 if self.player2["is_challenger"] else 0.4
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
        
        # 获取积分系统实例
        rank_system = DuelRankSystem(self.group_id)
        
        # 检查player1是否有隐身衣 - 直接获胜
        player1_data = rank_system.get_player_data(self.player1["name"])
        if player1_data["items"]["invisibility_cloak"] > 0:
            # 使用隐身衣
            player1_data["items"]["invisibility_cloak"] -= 1
            rank_system._save_ranks()
            self.steps.append(f"🧥 {self.player1['name']} 使用了隐身衣，潜行偷袭，直接获胜！")
            
            # 更新积分
            winner, loser = self.player1, self.player2
            
            # 固定积分变化
            winner_points = 30
            
            # 更新积分
            player1_data["score"] += winner_points
            player1_data["wins"] += 1
            player1_data["total_matches"] += 1
            
            player2_data = rank_system.get_player_data(self.player2["name"])
            player2_data["score"] = max(1, player2_data["score"] - winner_points)
            player2_data["losses"] += 1
            player2_data["total_matches"] += 1
            
            # 记录对战历史
            match_record = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "winner": winner["name"],
                "loser": loser["name"],
                "used_item": "invisibility_cloak",
                "points": winner_points
            }
            rank_system.ranks["groups"][self.group_id]["history"].append(match_record)
            
            # 保存数据
            rank_system._save_ranks()
            
            # 获取胜利者当前排名
            rank, _ = rank_system.get_player_rank(winner["name"])
            rank_text = f"第{rank}名" if rank else "暂无排名"
            
            # 添加结果
            result = (
                f"🏆 {winner['name']} 使用隐身衣获胜！\n\n"
                f"积分: {winner['name']} +{winner_points}分 ({rank_text})\n"
                f"{loser['name']} -{winner_points}分\n\n"
                f"📦 剩余隐身衣: {player1_data['items']['invisibility_cloak']}次"
            )
            self.steps.append(result)
            return self.steps
        
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
        
        # 获取玩家数据用于道具处理
        winner_data = rank_system.get_player_data(winner["name"])
        loser_data = rank_system.get_player_data(loser["name"])
        
        # 道具效果处理
        used_item = None
        
        # 检查失败者是否有魔法石 - 失败不扣分
        if winner["name"] != self.player1["name"] and loser_data["items"]["magic_stone"] > 0:
            # 使用魔法石
            self.steps.append(f"💎 {loser['name']} 使用了魔法石，虽然失败但是痊愈了！")
            loser_data["items"]["magic_stone"] -= 1
            used_item = "magic_stone"
            # 不扣分，但仍然记录胜负
            winner_points = total_magic_power
            loser_points = 0  # 不扣分
        # 检查胜利者是否有老魔杖 - 胜利积分×5
        elif winner["name"] == self.player1["name"] and winner_data["items"]["elder_wand"] > 0:
            # 使用老魔杖
            self.steps.append(f"🪄 {winner['name']} 使用了老魔杖，魔法威力增加了五倍！")
            winner_data["items"]["elder_wand"] -= 1
            used_item = "elder_wand"
            # 积分×5
            winner_points = total_magic_power * 5
            loser_points = total_magic_power  # 常规扣分
        else:
            # 正常积分计算
            winner_points = total_magic_power
            loser_points = total_magic_power  # 常规扣分
        
        # 更新积分
        winner_data["score"] += winner_points
        winner_data["wins"] += 1
        winner_data["total_matches"] += 1
        
        loser_data["score"] = max(1, loser_data["score"] - loser_points)  # 防止积分小于1
        loser_data["losses"] += 1
        loser_data["total_matches"] += 1
        
        # 记录对战历史
        match_record = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "winner": winner["name"],
            "loser": loser["name"],
            "magic_power": total_magic_power,
            "points": winner_points
        }
        
        # 如果使用了道具，记录在历史中
        if used_item:
            match_record["used_item"] = used_item
        
        rank_system.ranks["groups"][self.group_id]["history"].append(match_record)
        
        # 如果历史记录太多，保留最近的100条
        if len(rank_system.ranks["groups"][self.group_id]["history"]) > 100:
            rank_system.ranks["groups"][self.group_id]["history"] = rank_system.ranks["groups"][self.group_id]["history"][-100:]
        
        # 保存数据
        rank_system._save_ranks()
        
        # 获取胜利者当前排名
        rank, _ = rank_system.get_player_rank(winner["name"])
        rank_text = f"第{rank}名" if rank else "暂无排名"
        
        # 选择胜利描述
        victory_desc = random.choice(self.victory_descriptions)
        
        # 结果信息
        result = (
            f"🏆 {winner['name']} {victory_desc}！\n\n"
            f"积分: {winner['name']} +{winner_points}分 ({rank_text})\n"
            f"{loser['name']} -{loser_points}分"
        )
        
        # 如果使用了道具，显示剩余次数
        if used_item == "elder_wand":
            result += f"\n\n📦 剩余老魔杖: {winner_data['items']['elder_wand']}次"
        elif used_item == "magic_stone":
            result += f"\n\n📦 剩余魔法石: {loser_data['items']['magic_stone']}次"
        
        # 添加结果
        self.steps.append(result)
        return self.steps

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
            return f"✅ 已成功将本群中的玩家 \"{old_name}\" 改名为 \"{new_name}\"，历史战绩已保留"
        else:
            return f"❌ 改名失败：请确认 \"{old_name}\" 在本群中有战绩记录，且 \"{new_name}\" 名称未被使用"
    except Exception as e:
        logging.error(f"更改玩家名称失败: {e}")
        return f"❌ 更改玩家名称失败: {e}"
