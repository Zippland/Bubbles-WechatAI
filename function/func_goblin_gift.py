import random
from typing import TYPE_CHECKING, Callable, Any
from wcferry import WxMsg
from function.func_duel import DuelRankSystem

if TYPE_CHECKING:
    from logging import Logger
    from wcferry import Wcf
    from typing import Dict

class GoblinGiftManager:
    """管理古灵阁妖精的馈赠事件"""

    def __init__(self, config: Any, wcf: 'Wcf', log: 'Logger', send_text_msg: Callable):
        """初始化馈赠管理器

        Args:
            config: 配置对象，包含GOBLIN_GIFT配置项
            wcf: WCF实例，用于获取群聊昵称等信息
            log: 日志记录器
            send_text_msg: 发送文本消息的函数
        """
        self.config = config
        self.wcf = wcf
        self.LOG = log
        self.sendTextMsg = send_text_msg

    def try_trigger(self, msg: WxMsg) -> None:
        """尝试触发古灵阁妖精的馈赠事件

        Args:
            msg: 微信消息对象
        """
        # 检查配置是否存在
        if not hasattr(self.config, 'GOBLIN_GIFT'):
            return

        # 检查全局开关
        if not self.config.GOBLIN_GIFT.get('enable', False):
            return

        # 检查群聊白名单
        allowed_groups = self.config.GOBLIN_GIFT.get('allowed_groups', [])
        if not allowed_groups or msg.roomid not in allowed_groups:
            return

        # 只在群聊中才触发
        if not msg.from_group():
            return

        # 获取触发概率，默认1%
        probability = self.config.GOBLIN_GIFT.get('probability', 0.01)

        # 按概率触发
        if random.random() < probability:
            try:
                # 获取玩家昵称
                player_name = self.wcf.get_alias_in_chatroom(msg.sender, msg.roomid)
                if not player_name:
                    player_name = msg.sender  # 如果获取不到昵称，用wxid代替

                # 初始化对应群聊的积分系统
                rank_system = DuelRankSystem(group_id=msg.roomid)

                # 获取配置的积分范围，默认10-100
                min_points = self.config.GOBLIN_GIFT.get('min_points', 10)
                max_points = self.config.GOBLIN_GIFT.get('max_points', 100)

                # 随机增加积分
                points_added = random.randint(min_points, max_points)

                # 更新玩家数据
                player_data = rank_system.get_player_data(player_name)
                player_data['score'] += points_added

                # 保存数据
                rank_system._save_ranks()

                # 准备随机馈赠消息
                gift_sources = [
                    f"✨ 一只迷路的家养小精灵往 {player_name} 口袋里塞了什么东西！",
                    f"💰 古灵阁的妖精似乎格外青睐 {player_name}，留下了一袋金加隆（折合积分）！",
                    f"🦉 一只送信的猫头鹰丢错了包裹，{player_name} 意外发现了一笔“意外之财”！",
                    f"🍀 {player_name} 踩到了一株幸运四叶草，好运带来了额外的积分！",
                    f"🍄 在禁林的边缘，{player_name} 发现了一簇闪闪发光的魔法蘑菇！",
                    f"❓ {player_name} 捡到了一个有求必应屋掉出来的神秘物品！",
                    f"🔮 временами удача улыбается {player_name}!",  # 偶尔来点不一样的语言增加神秘感
                    f"🎉 费尔奇打瞌睡时掉了一小袋没收来的积分，刚好被 {player_name} 捡到！",
                    f"📜 一张古老的藏宝图碎片指引 {player_name} 找到了一些失落的积分！",
                    f"🧙‍♂️ 邓布利多教授对 {player_name} 的行为表示赞赏，特批“为学院加分”！",
                    f"🧪 {player_name} 的魔药课作业获得了斯拉格霍恩教授的额外加分！",
                    f"🌟 一颗流星划过霍格沃茨上空，{player_name} 许下的愿望成真了！"
                ]
                gift_message = random.choice(gift_sources)
                final_message = f"{gift_message}\n获得积分: +{points_added} 分！"

                # 发送馈赠通知 (@发送者)
                self.sendTextMsg(final_message, msg.roomid, msg.sender)
                self.LOG.info(f"古灵阁馈赠触发: 群 {msg.roomid}, 用户 {player_name}, 获得 {points_added} 积分")

            except Exception as e:
                self.LOG.error(f"触发古灵阁馈赠时出错: {e}") 