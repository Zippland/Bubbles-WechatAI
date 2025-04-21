import random
import re
from wcferry import Wcf
from typing import Callable, Optional

class InsultGenerator:
    """
    生成贴吧风格的骂人话术
    """
    
    # 贴吧风格骂人话术模板
    INSULT_TEMPLATES = [
        "{target}，你这想法属实有点抽象，建议回炉重造。",
        "不是吧，{target}，这都能说出来？大脑是用来思考的，不是用来长个儿的。",
        "乐，{target} 你成功逗笑了我，就像看猴戏一样。",
        "我说 {target} 啊，网上吵架没赢过，现实打架没输过是吧？",
        "{target}，听君一席话，浪费十分钟。",
        "给你个梯子，{target}，下个台阶吧，别搁这丢人现眼了。",
        "就这？{target}，就这？我还以为多大事呢。",
        "{target}，你是不是网线直连马桶的？味儿有点冲。",
        "讲道理，{target}，你这发言水平，在贴吧都活不过三楼。",
        "{target}，建议你去买两斤猪脑子煲汤喝，补补智商。",
        "说真的，{target}，你这智商要是放在好声音能把那四把椅子都转回来。",
        "{target}，放着好端端的智商不用，非得秀下限是吧？",
        "我看你是典型的脑子搭错弦，{target}，说话一套一套的。",
        "{target}，别整天搁这儿水经验了，你这水平也就适合到幼儿园门口卖糖水。",
        "你这句话水平跟你智商一样，{target}，都在地平线以下。",
        "就你这个水平，{target}，看王者荣耀的视频都能让你买错装备。",
        "{target}，整天叫唤啥呢？我没看《西游记》的时候真不知道猴子能说人话。",
        "我听懂了，{target}，你说的都对，可是能不能先把脑子装回去再说话？",
        "给{target}鼓个掌，成功把我逗乐了，这么多年的乐子人，今天是栽你手里了。",
        "{target}，我看你是孔子放屁——闻（文）所未闻（闻）啊。",
        "收敛点吧，{target}，你这智商余额明显不足了。",
        "{target}，你要是没话说可以咬个打火机，大家爱看那个。",
        "{target}，知道你急，但你先别急，喝口水慢慢说。",
        "{target}，你这发言跟你长相一样，突出一个随心所欲。",
        "不是，{target}，你这脑回路是盘山公路吗？九曲十八弯啊？",
        "{target}，太平洋没加盖，觉得委屈可以跳下去。",
        "搁这儿装啥大尾巴狼呢 {target}？尾巴都快摇断了吧？",
        "{target}，我看你不是脑子进水，是脑子被驴踢了吧？",
        "给你脸了是吧 {target}？真以为自己是个人物了？",
        "{target}，少在这里狺狺狂吠，影响市容。",
        "你这智商，{target}，二维码扫出来都得是付款码。",
        "乐死我了，{target}，哪来的自信在这里指点江山？",
        "{target}，回去多读两年书吧，省得出来丢人现眼。",
        "赶紧爬吧 {target}，别在这污染空气了。",
        "我看你是没挨过打，{target}，这么嚣张。",
        "给你个键盘，{target}，你能敲出一部《圣经》来是吧？",
        "脑子是个好东西，{target}，希望你也有一个。",
        "{target}，少在这里秀你的智商下限。",
        "就这？{target}？我还以为多牛逼呢，原来是个憨批。",
        "{target}，你这理解能力，怕不是胎教没做好。",
        "{target}，我看你像个小丑，上蹿下跳的。",
        "你这逻辑，{target}，体育老师教的吧？",
        "你这发言，{target}，堪称当代迷惑行为大赏。",
        "{target}，你这狗叫声能不能小点？",
        "你是猴子请来的救兵吗？{target}？",
        "{target}，你这脑容量，怕是连条草履虫都不如。",
        "给你个杆子你就往上爬是吧？{target}？",
        "{target}，你这嘴跟开了光似的，叭叭个没完。",
        "省省吧 {target}，你的智商税已经交得够多了。",
        "{target}，你这发言如同老太太的裹脚布，又臭又长。",
        "{target}，我看你是真的皮痒了。",
        "少在这里妖言惑众，{target}，滚回你的老鼠洞去。",
        "{target}，你就像个苍蝇一样，嗡嗡嗡烦死人。"
    ]
    
    @staticmethod
    def generate_insult(target_name: str) -> str:
        """
        随机生成一句针对目标用户的骂人话术（贴吧风格）
        
        Args:
            target_name (str): 被骂的人的名字
            
        Returns:
            str: 生成的骂人语句
        """
        if not target_name or target_name.strip() == "":
            target_name = "那个谁"  # 兜底，防止名字为空
        
        template = random.choice(InsultGenerator.INSULT_TEMPLATES)
        return template.format(target=target_name)


def generate_random_insult(target_name: str) -> str:
    """
    随机生成一句针对目标用户的骂人话术（贴吧风格）
    函数封装，方便直接调用
    
    Args:
        target_name (str): 被骂的人的名字
        
    Returns:
        str: 生成的骂人语句
    """
    return InsultGenerator.generate_insult(target_name)


def handle_insult_request(
    wcf: Wcf, 
    logger, 
    bot_wxid: str, 
    send_text_func: Callable[[str, str, Optional[str]], None], 
    trigger_goblin_gift_func: Callable[[object], None],
    msg,
    target_mention_name: str
) -> bool:
    """
    处理群聊中的"骂一下"请求。

    Args:
        wcf: Wcf 实例。
        logger: 日志记录器。
        bot_wxid: 机器人自身的 wxid。
        send_text_func: 发送文本消息的函数 (content, receiver, at_list=None)。
        trigger_goblin_gift_func: 触发哥布林馈赠的函数。
        msg: 原始消息对象 (需要 .roomid 属性)。
        target_mention_name: 从消息中提取的被@用户的名称。

    Returns:
        bool: 如果处理了该请求（无论成功失败），返回 True，否则返回 False。
    """
    logger.info(f"群聊 {msg.roomid} 中处理骂人指令，提及目标：{target_mention_name}")

    actual_target_name = target_mention_name
    target_wxid = None
    
    try:
        room_members = wcf.get_chatroom_members(msg.roomid)
        found = False
        for wxid, name in room_members.items():
            if target_mention_name == name:
                target_wxid = wxid
                actual_target_name = name
                found = True
                break
        if not found: 
            for wxid, name in room_members.items():
                if target_mention_name in name and wxid != bot_wxid: 
                    target_wxid = wxid
                    actual_target_name = name
                    logger.info(f"部分匹配到用户: {name} ({wxid})")
                    break 
    except Exception as e:
        logger.error(f"查找群成员信息时出错: {e}")

    if target_wxid and target_wxid == bot_wxid:
        send_text_func("😅 不行，我不能骂我自己。", msg.roomid)
        return True

    try:
        insult_text = generate_random_insult(actual_target_name)
        send_text_func(insult_text, msg.roomid)
        logger.info(f"已发送骂人消息至群 {msg.roomid}，目标: {actual_target_name}")
        
        if trigger_goblin_gift_func:
             trigger_goblin_gift_func(msg)
        
    except Exception as e:
         logger.error(f"生成或发送骂人消息时出错: {e}")
         send_text_func("呃，我想骂但出错了...", msg.roomid)
         
    return True