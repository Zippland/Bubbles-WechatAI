import re
import random
from typing import Optional, Match, Dict, Any
import json # 确保已导入json
from datetime import datetime # 确保已导入datetime
import os # 导入os模块用于文件路径操作
from function.func_duel import DuelRankSystem 

# 导入AI模型
from ai_providers.ai_deepseek import DeepSeek
from ai_providers.ai_chatgpt import ChatGPT  
from ai_providers.ai_chatglm import ChatGLM
from ai_providers.ai_ollama import Ollama

# 前向引用避免循环导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .context import MessageContext

def handle_help(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "帮助" 命令
    
    匹配: info/帮助/指令
    """
    help_text = [
        "🤖 泡泡的指令列表 🤖",
        "",
        "【实用工具】",
        "- 天气/温度 [城市名]",
        "- 天气预报/预报 [城市名]",
        "- 新闻",
        "- ask [问题]",
        "",
        "【决斗 & 偷袭】",
        "- 决斗@XX",
        "- 偷袭@XX",
        "- 决斗排行/排行榜",
        "- 我的战绩/决斗战绩",
        "- 我的装备/查看装备",
        "- 改名 [旧名] [新名]",
        "",
        "【提醒】",
        "- 提醒xxxxx：一次性、每日、每周",
        "- 查看提醒/我的提醒/提醒列表",
        "- 删除提醒 [ID]/all",
        "",
        "【成语】",
        "- #成语：接龙",
        "- ?成语：查询成语释义",
        "",
        "【群聊工具】",
        "- summary/总结",
        "- clearmessages/清除历史",
        "- reset/重置",
        ""
    ]
    help_text = "\n".join(help_text)
    
    # 发送消息
    return ctx.send_text(help_text)

def handle_duel(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "决斗" 命令
    
    匹配: 决斗@XX 或 决斗和XX 等
    """
    if not ctx.is_group:
        ctx.send_text("❌ 决斗功能只支持群聊")
        return True
    
    if not match:
        return False
    
    # 获取对手名称
    opponent_name_input = match.group(1).strip()
    
    if ctx.logger:
        ctx.logger.info(f"决斗指令匹配: 对手={opponent_name_input}, 发起者={ctx.sender_name}")
    
    # 寻找群内对应的成员 (优先完全匹配，其次部分匹配)
    opponent_wxid = None
    opponent_name = None
    
    # 第一次遍历：寻找完全匹配
    for member_wxid, member_name in ctx.room_members.items():
        if opponent_name_input == member_name:
            opponent_wxid = member_wxid
            opponent_name = member_name
            if ctx.logger:
                ctx.logger.info(f"找到完全匹配对手: {opponent_name}")
            break
    
    # 如果没有找到完全匹配，再寻找部分匹配
    if not opponent_wxid:
        for member_wxid, member_name in ctx.room_members.items():
            if opponent_name_input in member_name:
                opponent_wxid = member_wxid
                opponent_name = member_name
                if ctx.logger:
                    ctx.logger.info(f"未找到完全匹配，使用部分匹配对手: {opponent_name}")
                break
    
    if not opponent_wxid:
        ctx.send_text(f"❌ 没有找到名为 {opponent_name_input} 的群成员")
        return True
    
    # 获取挑战者昵称
    challenger_name = ctx.sender_name
    group_id = ctx.msg.roomid

    # --- 新增：决斗资格检查 (包括分数和 Boss 战) ---
    try:
        rank_system = DuelRankSystem(group_id)
        # 获取双方玩家数据和分数
        challenger_data = rank_system.get_player_data(challenger_name)
        opponent_data = rank_system.get_player_data(opponent_name)
        challenger_score = challenger_data.get("score", 0)
        opponent_score = opponent_data.get("score", 0)

        is_boss_battle = (opponent_name == "泡泡")

        # 检查 Boss 战资格 (仅检查挑战者分数)
        if is_boss_battle and challenger_score < 100:
            funny_messages = [
                f"嘿，{challenger_name}！你当前的积分 ({challenger_score}) 还没攒够挑战大魔王 '泡泡' 的勇气呢！先去决斗场练练级吧！💪",
                f"勇士 {challenger_name} ({challenger_score}分)，强大的 '泡泡' 觉得你还需要更多历练才能与之一战。先去赚点积分壮壮胆吧！💰",
                f"({challenger_score}分) 就想挑战 Boss '泡泡'？{challenger_name}，你这是要去送人头吗？'泡泡' 表示太弱了，拒绝接待！🚫",
                f"挑战 Boss '泡泡' 需要至少100积分作为门票，{challenger_name} ({challenger_score}分) 好像还差一点点哦~ 😉",
                f"'泡泡' 正在冥想，感觉到 {challenger_name} 的力量 ({challenger_score}分) 尚不足以撼动祂，让你再修炼修炼。🧘"
            ]
            message = random.choice(funny_messages)
            ctx.send_text(message)
            if ctx.logger:
                ctx.logger.info(f"玩家 {challenger_name} 积分 {challenger_score} 不足100，阻止发起 Boss 战")
            return True # 命令已处理，阻止后续逻辑

        # 检查普通决斗资格 (检查双方分数)
        elif not is_boss_battle and (challenger_score < 100 or opponent_score < 100):
            low_score_player = ""
            low_score_value = 0
            if challenger_score < 100 and opponent_score < 100:
                 low_score_player = f"{challenger_name} ({challenger_score}分) 和 {opponent_name} ({opponent_score}分) 都"
                 low_score_value = min(challenger_score, opponent_score) # 不重要，仅用于日志
            elif challenger_score < 100:
                 low_score_player = f"{challenger_name} ({challenger_score}分)"
                 low_score_value = challenger_score
            else: # opponent_score < 100
                 low_score_player = f"{opponent_name} ({opponent_score}分)"
                 low_score_value = opponent_score
            
            funny_messages = [
                f"哎呀！{low_score_player} 的决斗积分还没到100分呢，好像还没做好上场的准备哦！😅",
                f"等等！根据决斗场规则，{low_score_player} 的积分不足100分，暂时无法参与决斗。先去打打小怪兽吧！👾",
                f"裁判举牌！🚩 {low_score_player} 决斗积分未满100，本场决斗无效！请先提升实力再来挑战！",
                f"看起来 {low_score_player} 还是个决斗新手（积分不足100），先熟悉一下场地，找点低级对手练练手吧！😉",
                f"呜~~~ 决斗场的能量保护罩拒绝了 {low_score_player}（积分不足100）进入！先去充点能（分）吧！⚡"
            ]
            message = random.choice(funny_messages)
            ctx.send_text(message)
            if ctx.logger:
                ctx.logger.info(f"因玩家 {low_score_player} 积分 ({low_score_value}) 不足100，阻止发起普通决斗")
            return True # 命令已处理，阻止后续逻辑

    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"检查决斗资格时出错: {e}", exc_info=True)
        ctx.send_text("⚠️ 检查决斗资格时发生错误，请稍后再试。")
        return True # 出错也阻止后续逻辑
    # --- 决斗资格检查结束 ---

    # 使用决斗管理器启动决斗 (只有通过所有检查才会执行到这里)
    if ctx.robot and hasattr(ctx.robot, "duel_manager"):
        duel_manager = ctx.robot.duel_manager
        # 注意：start_duel_thread 现在只会在资格检查通过后被调用
        if not duel_manager.start_duel_thread(challenger_name, opponent_name, group_id, True):
            ctx.send_text("⚠️ 目前有其他决斗正在进行中，请稍后再试！")
        # 决斗管理器内部会发送消息，所以这里不需要额外发送
        
        # 尝试触发馈赠
        if hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
        return True
    else:
        # 如果没有决斗管理器，返回错误信息
        ctx.send_text("⚠️ 决斗系统未初始化")
        return False

def handle_sneak_attack(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "偷袭" 命令
    
    匹配: 偷袭@XX 或 偷分@XX
    """
    if not ctx.is_group:
        ctx.send_text("❌ 偷袭功能只支持群聊哦。")
        return True
    
    if not match:
        return False
    
    # 获取目标名称
    target_name = match.group(1).strip()
    
    # 获取攻击者昵称
    attacker_name = ctx.sender_name
    
    # 调用偷袭逻辑
    try:
        from function.func_duel import attempt_sneak_attack
        result_message = attempt_sneak_attack(attacker_name, target_name, ctx.msg.roomid)
        
        # 发送结果
        ctx.send_text(result_message)
        
        # 尝试触发馈赠
        if ctx.robot and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
        return True
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"执行偷袭命令出错: {e}")
        ctx.send_text("⚠️ 偷袭功能出现错误")
        return False

def handle_duel_rank(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "决斗排行" 命令
    
    匹配: 决斗排行/决斗排名/排行榜
    """
    if not ctx.is_group:
        ctx.send_text("❌ 决斗排行榜功能只支持群聊")
        return True
    
    try:
        from function.func_duel import get_rank_list
        rank_list = get_rank_list(10, ctx.msg.roomid)  # 获取前10名排行
        ctx.send_text(rank_list)
        
        # 尝试触发馈赠
        if ctx.robot and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
        return True
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"获取决斗排行榜出错: {e}")
        ctx.send_text("⚠️ 获取排行榜失败")
        return False

def handle_duel_stats(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "决斗战绩" 命令
    
    匹配: 决斗战绩/我的战绩/战绩查询 [名字]
    """
    if not ctx.is_group:
        ctx.send_text("❌ 决斗战绩查询功能只支持群聊")
        return True
    
    if not match:
        return False
    
    try:
        from function.func_duel import get_player_stats
        
        # 获取要查询的玩家
        player_name = ""
        if len(match.groups()) > 1 and match.group(2):
            player_name = match.group(2).strip()
        
        if not player_name:  # 如果没有指定名字，则查询发送者
            player_name = ctx.sender_name
        
        stats = get_player_stats(player_name, ctx.msg.roomid)
        ctx.send_text(stats)
        
        # 尝试触发馈赠
        if ctx.robot and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
        return True
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"查询决斗战绩出错: {e}")
        ctx.send_text("⚠️ 查询战绩失败")
        return False

def handle_check_equipment(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "查看装备" 命令
    
    匹配: 我的装备/查看装备
    """
    if not ctx.is_group:
        ctx.send_text("❌ 装备查看功能只支持群聊")
        return True
    
    try:
        from function.func_duel import DuelRankSystem
        
        player_name = ctx.sender_name
        rank_system = DuelRankSystem(ctx.msg.roomid)
        player_data = rank_system.get_player_data(player_name)
        
        if not player_data:
            ctx.send_text(f"⚠️ 没有找到 {player_name} 的数据")
            return True
        
        items = player_data.get("items", {"elder_wand": 0, "magic_stone": 0, "invisibility_cloak": 0})
        result = [
            f"🧙‍♂️ {player_name} 的魔法装备:",
            f"🪄 老魔杖: {items.get('elder_wand', 0)}次 ",
            f"💎 魔法石: {items.get('magic_stone', 0)}次",
            f"🧥 隐身衣: {items.get('invisibility_cloak', 0)}次 "
        ]
        
        ctx.send_text("\n".join(result))
        
        # 尝试触发馈赠
        if ctx.robot and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
        return True
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"查看装备出错: {e}")
        ctx.send_text("⚠️ 查看装备失败")
        return False

def handle_reset_memory(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "重置记忆" 命令
    
    匹配: reset/重置/重置记忆
    """
    chat_id = ctx.get_receiver()
    chat_model = ctx.chat  # 使用上下文中的chat模型
    
    if not chat_model:
        ctx.send_text("⚠️ 未配置AI模型，无需重置")
        return True
        
    try:
        # 检查并调用不同AI模型的清除记忆方法
        if hasattr(chat_model, 'conversation_list') and chat_id in getattr(chat_model, 'conversation_list', {}):
            # 判断是哪种类型的模型并执行相应的重置操作
            model_name = chat_model.__class__.__name__
            
            if isinstance(chat_model, DeepSeek):
                # DeepSeek模型
                del chat_model.conversation_list[chat_id]
                if ctx.logger: ctx.logger.info(f"已重置DeepSeek对话记忆: {chat_id}")
                result = "✅ 已重置DeepSeek对话记忆，开始新的对话"
                
            elif isinstance(chat_model, ChatGPT):
                # ChatGPT模型
                # 保留系统提示，删除其他历史
                if len(chat_model.conversation_list[chat_id]) > 0:
                    system_msgs = [msg for msg in chat_model.conversation_list[chat_id] if msg["role"] == "system"]
                    chat_model.conversation_list[chat_id] = system_msgs
                    if ctx.logger: ctx.logger.info(f"已重置ChatGPT对话记忆(保留系统提示): {chat_id}")
                    result = "✅ 已重置ChatGPT对话记忆，保留系统提示，开始新的对话"
                else:
                    result = f"⚠️ {model_name} 对话记忆已为空，无需重置"
                    
            elif isinstance(chat_model, ChatGLM):
                # ChatGLM模型
                if hasattr(chat_model, 'chat_type') and chat_id in chat_model.chat_type:
                    chat_type = chat_model.chat_type[chat_id]
                    # 保留系统提示，删除对话历史
                    if chat_type in chat_model.conversation_list[chat_id]:
                        chat_model.conversation_list[chat_id][chat_type] = []
                        if ctx.logger: ctx.logger.info(f"已重置ChatGLM对话记忆: {chat_id}")
                        result = "✅ 已重置ChatGLM对话记忆，开始新的对话"
                    else:
                        result = f"⚠️ 未找到与 {model_name} 的对话记忆，无需重置"
                else:
                    result = f"⚠️ 未找到与 {model_name} 的对话记忆，无需重置"
                
            elif isinstance(chat_model, Ollama):
                # Ollama模型
                if chat_id in chat_model.conversation_list:
                    chat_model.conversation_list[chat_id] = []
                    if ctx.logger: ctx.logger.info(f"已重置Ollama对话记忆: {chat_id}")
                    result = "✅ 已重置Ollama对话记忆，开始新的对话"
                else:
                    result = f"⚠️ 未找到与 {model_name} 的对话记忆，无需重置"
            
            else:
                # 通用处理方式：直接删除对话记录
                del chat_model.conversation_list[chat_id]
                if ctx.logger: ctx.logger.info(f"已通过通用方式重置{model_name}对话记忆: {chat_id}")
                result = f"✅ 已重置{model_name}对话记忆，开始新的对话"
        else:
            # 对于没有找到会话记录的情况
            model_name = chat_model.__class__.__name__ if chat_model else "未知模型"
            if ctx.logger: ctx.logger.info(f"未找到{model_name}对话记忆: {chat_id}")
            result = f"⚠️ 未找到与{model_name}的对话记忆，无需重置"
        
        # 发送结果消息
        ctx.send_text(result)
        
        # 群聊中触发馈赠
        if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
        return True
        
    except Exception as e:
        if ctx.logger: ctx.logger.error(f"重置对话记忆失败: {e}")
        ctx.send_text(f"❌ 重置对话记忆失败: {e}")
        return False

def handle_summary(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "消息总结" 命令
    
    匹配: summary/总结
    """
    if not ctx.is_group:
        ctx.send_text("⚠️ 消息总结功能仅支持群聊")
        return True
    
    try:
        # 获取群聊ID
        chat_id = ctx.msg.roomid
        
        # 使用MessageSummary生成总结
        if ctx.robot and hasattr(ctx.robot, "message_summary") and hasattr(ctx.robot, "chat"):
            summary = ctx.robot.message_summary.summarize_messages(chat_id, ctx.robot.chat)
            
            # 发送总结
            ctx.send_text(summary)
            
            # 尝试触发馈赠
            if hasattr(ctx.robot, "goblin_gift_manager"):
                ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
            
            return True
        else:
            ctx.send_text("⚠️ 消息总结功能不可用")
            return False
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"生成消息总结出错: {e}")
        ctx.send_text("⚠️ 生成消息总结失败")
        return False

def handle_clear_messages(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "清除消息历史" 命令
    
    匹配: clearmessages/清除消息/清除历史
    """
    if not ctx.is_group:
        ctx.send_text("⚠️ 消息历史管理功能仅支持群聊")
        return True
    
    try:
        # 获取群聊ID
        chat_id = ctx.msg.roomid
        
        # 清除历史
        if ctx.robot and hasattr(ctx.robot, "message_summary"):
            if ctx.robot.message_summary.clear_message_history(chat_id):
                ctx.send_text("✅ 已清除本群的消息历史记录")
            else:
                ctx.send_text("⚠️ 本群没有消息历史记录")
            
            # 尝试触发馈赠
            if hasattr(ctx.robot, "goblin_gift_manager"):
                ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
            
            return True
        else:
            ctx.send_text("⚠️ 消息历史管理功能不可用")
            return False
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"清除消息历史出错: {e}")
        ctx.send_text("⚠️ 清除消息历史失败")
        return False

def handle_news_request(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "新闻" 命令
    
    匹配: 新闻
    """
    if ctx.logger:
        ctx.logger.info(f"收到来自 {ctx.sender_name} (群聊: {ctx.msg.roomid if ctx.is_group else '无'}) 的新闻请求")
        
    try:
        from function.func_news import News
        news_instance = News()
        # 调用方法，接收返回的元组(is_today, news_content)
        is_today, news_content = news_instance.get_important_news()

        receiver = ctx.get_receiver()
        sender_for_at = ctx.msg.sender if ctx.is_group else "" # 群聊中@请求者

        if is_today:
            # 是当天新闻，直接发送
            ctx.send_text(f"📰 今日要闻来啦：\n{news_content}", sender_for_at)
        else:
            # 不是当天新闻或获取失败
            if news_content:
                # 有内容，说明是旧闻
                prompt = "ℹ️ 今日新闻暂未发布，为您找到最近的一条新闻："
                ctx.send_text(f"{prompt}\n{news_content}", sender_for_at)
            else:
                # 内容为空，说明获取彻底失败
                ctx.send_text("❌ 获取新闻失败，请稍后重试或联系管理员。", sender_for_at)

        # 尝试触发馈赠
        if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)

        return True # 无论结果如何，命令本身算成功处理

    except Exception as e:
        if ctx.logger: ctx.logger.error(f"处理新闻请求时出错: {e}")
        receiver = ctx.get_receiver()
        sender_for_at = ctx.msg.sender if ctx.is_group else ""
        ctx.send_text("❌ 获取新闻时发生错误，请稍后重试。", sender_for_at)
        return False # 处理失败

def handle_rename(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "改名" 命令
    
    匹配: 改名 旧名 新名
    """
    if not ctx.is_group:
        ctx.send_text("❌ 改名功能只支持群聊")
        return True
    
    if not match or len(match.groups()) < 2:
        ctx.send_text("❌ 改名格式不正确，请使用: 改名 旧名 新名")
        return True
    
    old_name = match.group(1)
    new_name = match.group(2)
    
    if not old_name or not new_name:
        ctx.send_text("❌ 请提供有效的旧名和新名")
        return True
    
    try:
        from function.func_duel import change_player_name
        result = change_player_name(old_name, new_name, ctx.msg.roomid)
        ctx.send_text(result)
        
        # 尝试触发馈赠
        if hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
        return True
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"改名出错: {e}")
        ctx.send_text("⚠️ 改名失败")
        return False

def handle_chengyu(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "成语" 命令
    
    匹配: #成语 或 ?成语
    """
    if not match:
        return False
    
    flag = match.group(1)  # '#' 或 '?'
    text = match.group(2)  # 成语文本
    
    try:
        from function.func_chengyu import cy
        
        if flag == "#":  # 接龙
            if cy.isChengyu(text):
                rsp = cy.getNext(text)
                if rsp:
                    ctx.send_text(rsp)
                    
                    # 尝试触发馈赠
                    if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
                        ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
                    
                    return True
        elif flag in ["?", "？"]:  # 查词
            if cy.isChengyu(text):
                rsp = cy.getMeaning(text)
                if rsp:
                    ctx.send_text(rsp)
                    
                    # 尝试触发馈赠
                    if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
                        ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
                    
                    return True
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"处理成语出错: {e}")
    
    return False

def handle_chitchat(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理闲聊，调用AI模型生成回复
    """
    # 获取对应的AI模型
    chat_model = None
    if hasattr(ctx, 'chat'):
        chat_model = ctx.chat
    elif ctx.robot and hasattr(ctx.robot, 'chat'):
        chat_model = ctx.robot.chat
    
    if not chat_model:
        if ctx.logger:
            ctx.logger.error("没有可用的AI模型处理闲聊")
        ctx.send_text("抱歉，我现在无法进行对话。")
        return False
    
    # 获取消息内容
    content = ctx.text
    sender_name = ctx.sender_name
    
    # 使用XML处理器格式化消息
    if ctx.robot and hasattr(ctx.robot, "xml_processor"):
        # 创建格式化的聊天内容（带有引用消息等）
        # 原始代码中是从xml_processor获取的
        if ctx.is_group:
            # 处理群聊消息
            msg_data = ctx.robot.xml_processor.extract_quoted_message(ctx.msg)
            q_with_info = ctx.robot.xml_processor.format_message_for_ai(msg_data, sender_name)
            # 打印详细的消息数据，用于调试
            if ctx.logger:
                ctx.logger.info(f"【调试】群聊消息解析结果: type={ctx.msg.type}")
                ctx.logger.info(f"【调试】提取的卡片信息: {msg_data}")
        else:
            # 处理私聊消息
            msg_data = ctx.robot.xml_processor.extract_private_quoted_message(ctx.msg)
            q_with_info = ctx.robot.xml_processor.format_message_for_ai(msg_data, sender_name)
            # 打印详细的消息数据，用于调试
            if ctx.logger:
                ctx.logger.info(f"【调试】私聊消息解析结果: type={ctx.msg.type}")
                ctx.logger.info(f"【调试】提取的卡片信息: {msg_data}")
        
        if not q_with_info:
            import time
            current_time = time.strftime("%H:%M", time.localtime())
            q_with_info = f"[{current_time}] {sender_name}: {content or '[空内容]'}"
    else:
        # 简单格式化
        import time
        current_time = time.strftime("%H:%M", time.localtime())
        q_with_info = f"[{current_time}] {sender_name}: {content or '[空内容]'}"
    
    # 获取AI回复
    try:
        if ctx.logger:
            ctx.logger.info(f"【发送内容】将以下消息发送给AI: \n{q_with_info}")
        
        rsp = chat_model.get_answer(q_with_info, ctx.get_receiver())
        
        if rsp:
            # 发送回复
            at_list = ctx.msg.sender if ctx.is_group else ""
            ctx.send_text(rsp, at_list)
            
            # 尝试触发馈赠
            if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
                ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
            
            return True
        else:
            if ctx.logger:
                ctx.logger.error("无法从AI获得答案")
            return False
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"获取AI回复时出错: {e}")
        return False

def handle_insult(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "骂人" 命令
    
    匹配: 骂一下@XX
    """
    if not ctx.is_group:
        ctx.send_text("❌ 骂人功能只支持群聊哦~")
        return True
    
    if not match:
        return False
    
    # 获取目标名称
    target_mention_name = match.group(1).strip()
    
    if ctx.logger:
        ctx.logger.info(f"群聊 {ctx.msg.roomid} 中检测到骂人指令，提及目标：{target_mention_name}")
    
    # 默认使用提及的名称
    actual_target_name = target_mention_name  
    target_wxid = None
    
    # 尝试查找实际群成员昵称和wxid
    try:
        found = False
        for wxid, name in ctx.room_members.items():
            # 优先完全匹配，其次部分匹配
            if target_mention_name == name:
                target_wxid = wxid
                actual_target_name = name
                found = True
                break
        if not found:  # 如果完全匹配不到，再尝试部分匹配
            for wxid, name in ctx.room_members.items():
                if target_mention_name in name:
                    target_wxid = wxid
                    actual_target_name = name
                    break
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"查找群成员信息时出错: {e}")
        # 出错时继续使用提及的名称
    
    # 禁止骂机器人自己
    if target_wxid and target_wxid == ctx.robot_wxid:
        ctx.send_text("😅 不行，我不能骂我自己。")
        return True
    
    # 即使找不到wxid，仍然尝试使用提及的名字骂
    try:
        from function.func_insult import generate_random_insult
        insult_text = generate_random_insult(actual_target_name)
        ctx.send_text(insult_text)
        
        if ctx.logger:
            ctx.logger.info(f"已发送骂人消息至群 {ctx.msg.roomid}，目标: {actual_target_name}")
        
        # 尝试触发馈赠
        if ctx.robot and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
        return True
    except ImportError:
        if ctx.logger:
            ctx.logger.error("无法导入 func_insult 模块。")
        ctx.send_text("Oops，我的骂人模块好像坏了...")
        return True
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"生成或发送骂人消息时出错: {e}")
        ctx.send_text("呃，我想骂但出错了...")
        return True

def handle_perplexity_ask(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "ask" 命令，调用 Perplexity AI

    匹配: ask [问题内容]
    """
    if not match:  # 理论上正则匹配成功才会被调用，但加个检查更安全
        return False

    # 1. 尝试从 Robot 实例获取 Perplexity 实例
    perplexity_instance = getattr(ctx.robot, 'perplexity', None)
    
    # 2. 检查 Perplexity 实例是否存在
    if not perplexity_instance:
        if ctx.logger:
            ctx.logger.warning("尝试调用 Perplexity，但实例未初始化或未配置。")
        ctx.send_text("❌ Perplexity 功能当前不可用或未正确配置。")
        return True  # 命令已被处理（错误处理也是处理）

    # 3. 从匹配结果中提取问题内容
    prompt = match.group(1).strip()
    if not prompt:  # 如果 'ask' 后面没有内容
        ctx.send_text("请在 'ask' 后面加上您想问的问题。", ctx.msg.sender if ctx.is_group else None)
        return True  # 命令已被处理

    # 4. 准备调用 Perplexity 实例的 process_message 方法
    if ctx.logger:
        ctx.logger.info(f"检测到 Perplexity 请求，发送者: {ctx.sender_name}, 问题: {prompt[:50]}...")

    # 准备参数并调用 process_message
    # 确保无论用户输入有没有空格，都以标准格式"ask 问题"传给process_message
    content_for_perplexity = f"ask {prompt}"  # 重构包含触发词的内容
    chat_id = ctx.get_receiver()
    sender_wxid = ctx.msg.sender
    room_id = ctx.msg.roomid if ctx.is_group else None
    is_group = ctx.is_group
    
    # 5. 调用 process_message 并返回其结果
    was_handled, fallback_prompt = perplexity_instance.process_message(
        content=content_for_perplexity,
        chat_id=chat_id,
        sender=sender_wxid,
        roomid=room_id,
        from_group=is_group,
        send_text_func=ctx.send_text
    )
    
    # 6. 如果没有被处理且有备选prompt，使用默认AI处理
    if not was_handled and fallback_prompt:
        if ctx.logger:
            ctx.logger.info(f"使用备选prompt '{fallback_prompt[:20]}...' 调用默认AI处理")
        
        # 获取当前选定的AI模型
        chat_model = None
        if hasattr(ctx, 'chat'):
            chat_model = ctx.chat
        elif ctx.robot and hasattr(ctx.robot, 'chat'):
            chat_model = ctx.robot.chat
        
        if chat_model:
            # 使用与 handle_chitchat 类似的逻辑，但使用备选prompt
            try:
                # 格式化消息，与 handle_chitchat 保持一致
                if ctx.robot and hasattr(ctx.robot, "xml_processor"):
                    if ctx.is_group:
                        msg_data = ctx.robot.xml_processor.extract_quoted_message(ctx.msg)
                        q_with_info = ctx.robot.xml_processor.format_message_for_ai(msg_data, ctx.sender_name)
                    else:
                        msg_data = ctx.robot.xml_processor.extract_private_quoted_message(ctx.msg)
                        q_with_info = ctx.robot.xml_processor.format_message_for_ai(msg_data, ctx.sender_name)
                    
                    if not q_with_info:
                        import time
                        current_time = time.strftime("%H:%M", time.localtime())
                        q_with_info = f"[{current_time}] {ctx.sender_name}: {prompt or '[空内容]'}"
                else:
                    import time
                    current_time = time.strftime("%H:%M", time.localtime())
                    q_with_info = f"[{current_time}] {ctx.sender_name}: {prompt or '[空内容]'}"
                
                if ctx.logger:
                    ctx.logger.info(f"发送给默认AI的消息内容: {q_with_info}")
                
                # 调用 AI 模型时传入备选 prompt
                # 需要调整 get_answer 方法以支持 system_prompt_override 参数
                # 这里我们假设已对各AI模型实现了这个参数
                rsp = chat_model.get_answer(q_with_info, ctx.get_receiver(), system_prompt_override=fallback_prompt)
                
                if rsp:
                    # 发送回复
                    at_list = ctx.msg.sender if ctx.is_group else ""
                    ctx.send_text(rsp, at_list)
                    
                    # 尝试触发馈赠
                    if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
                        ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
                    
                    return True
                else:
                    if ctx.logger:
                        ctx.logger.error("无法从默认AI获得答案")
            except Exception as e:
                if ctx.logger:
                    ctx.logger.error(f"使用备选prompt调用默认AI时出错: {e}")
    
    return was_handled 

def handle_reminder(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """处理来自私聊或群聊的 '提醒' 命令"""
    # 2. 获取用户输入的提醒内容（现在包含"提醒"字样）
    raw_text = match.group(1).strip()
    if not raw_text or raw_text == "提醒":
        # 在群聊中@用户回复
        at_list = ctx.msg.sender if ctx.is_group else ""
        ctx.send_text("请告诉我需要提醒什么内容和时间呀~ (例如：提醒 明天下午3点 开会 或 提醒我早上七点起床)", at_list)
        return True

    # 3. 构造给 AI 的 Prompt
    sys_prompt = """
你是提醒解析助手。请分析用户输入的提醒信息，并严格按照以下 JSON 格式输出结果：
{{
  "type": "once" | "daily" | "weekly",                 // 提醒类型: "once" (一次性) 或 "daily" (每日重复) 或 "weekly" (每周重复)
  "time": "YYYY-MM-DD HH:MM" | "HH:MM",     // "once"类型必须是 'YYYY-MM-DD HH:MM' 格式, "daily"与"weekly"类型必须是 'HH:MM' 格式。时间必须是未来的。
  "content": "提醒的具体内容文本",
  "weekday": 0-6,                           // 仅当 type="weekly" 时需要，周一=0, 周二=1, ..., 周日=6
  "extra": {{}}                              // 保留字段，目前为空对象即可
}}
- 分析用户意图判断是 `once`, `daily` 还是 `weekly`。
- 如果是相对时间（如"明天"、"后天"、"下周一"），请计算出精确的 `YYYY-MM-DD HH:MM` 格式。
- 如果只说了时间（如"每天早上9点"），类型设为 `daily`，时间格式为 `HH:MM`。
- 如果是每周特定时间（如"每周一下午3点"），类型设为 `weekly`，提供正确的 weekday 值和 HH:MM 时间。
- 如果无法确定时间或内容，不要猜测，返回错误提示，这样我可以提醒用户提供更明确的信息。
- 输出结果必须是纯 JSON，不包含任何其他说明文字。

当前准确时间是：{current_datetime}
"""
    current_dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_prompt = sys_prompt.format(current_datetime=current_dt_str)

    # 4. 调用AI模型并解析
    q_for_ai = f"请解析以下用户提醒:\n{raw_text}"
    data = None
    try:
        # 检查AI模型
        if not hasattr(ctx, 'chat') or not ctx.chat:
            raise ValueError("当前上下文中没有可用的AI模型")
            
        # 获取AI回答
        at_list = ctx.msg.sender if ctx.is_group else ""
        ai_response = ctx.chat.get_answer(q_for_ai, ctx.get_receiver(), system_prompt_override=formatted_prompt)
        
        # 尝试提取和解析JSON
        json_str = None
        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = ai_response
            
        try:
            data = json.loads(json_str)
        except:
            ctx.send_text("❌ 无法解析AI的回复为有效的JSON格式", at_list)
            return True
            
        # 验证数据
        if not data.get("type") or not data.get("time") or not data.get("content"):
            ctx.send_text("❌ AI返回的数据缺少必要字段(类型/时间/内容)", at_list)
            return True
            
        # 验证内容
        if len(data.get("content", "").strip()) < 2:
            ctx.send_text("❌ 提醒内容太短，请提供更具体的提醒内容", at_list)
            return True
            
        # 验证时间格式
        if data["type"] == "once":
            try:
                dt = datetime.strptime(data["time"], "%Y-%m-%d %H:%M")
                if dt < datetime.now():
                    ctx.send_text("❌ 提醒时间必须是未来的时间", at_list)
                    return True
            except ValueError:
                ctx.send_text("❌ 一次性提醒的时间格式不正确", at_list)
                return True
                
        # 验证周提醒
        if data["type"] == "weekly" and not (isinstance(data.get("weekday"), int) and 0 <= data.get("weekday") <= 6):
            ctx.send_text("❌ 每周提醒需要指定是周几(0-6)", at_list)
            return True
            
        # 记录日志
        if ctx.logger:
            ctx.logger.info(f"成功解析提醒: {data}")
    except Exception as e:
        at_list = ctx.msg.sender if ctx.is_group else ""
        ctx.send_text(f"❌ 处理提醒时出错: {str(e)}", at_list)
        if ctx.logger:
            ctx.logger.error(f"处理提醒出错: {e}", exc_info=True)
        return True

    # 6. 将解析结果交给 ReminderManager 处理
    if not hasattr(ctx.robot, 'reminder_manager'):
        at_list = ctx.msg.sender if ctx.is_group else ""
        ctx.send_text("❌ 内部错误：提醒管理器未初始化。", at_list)
        if ctx.logger: 
            ctx.logger.error("handle_reminder 无法访问 ctx.robot.reminder_manager")
        return True

    # 根据当前环境（群聊或私聊）设置roomid参数
    roomid = ctx.msg.roomid if ctx.is_group else None
    success, result_or_id = ctx.robot.reminder_manager.add_reminder(ctx.msg.sender, data, roomid=roomid)

    # 7. 向用户反馈结果
    # 在群聊中@用户
    at_list = ctx.msg.sender if ctx.is_group else ""
    
    if success:
        reminder_id = result_or_id
        # 构建更友好的回复，根据提醒类型进行定制
        type_str = {
            "once": "一次性",
            "daily": "每日",
            "weekly": "每周"
        }.get(data.get("type"), "未知类型")
        
        # 格式化时间显示，使其更友好
        time_display = data.get("time", "未知时间")
        if data.get("type") == "weekly" and "weekday" in data:
            weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            if 0 <= data["weekday"] <= 6:
                time_display = f"{weekdays[data['weekday']]} {time_display}"
        
        # 添加设置环境提示（群聊/私聊）
        scope_info = f"在本群" if ctx.is_group else "私聊"
        reply_msg = f"✅ 好的，已为您{scope_info}设置{type_str}提醒 (ID: {reminder_id[:6]}):\n" \
                    f"时间: {time_display}\n" \
                    f"内容: {data.get('content', '无')}"
        ctx.send_text(reply_msg, at_list)
        
        # 尝试触发馈赠（如果在群聊中）
        if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
    else:
        error_message = result_or_id # 此时 result_or_id 是错误信息
        ctx.send_text(f"❌ 设置提醒失败: {error_message}", at_list)

    return True # 命令处理流程结束

def handle_list_reminders(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """处理查看提醒命令（支持群聊和私聊）"""
    if not hasattr(ctx.robot, 'reminder_manager'):
        ctx.send_text("❌ 内部错误：提醒管理器未初始化。", ctx.msg.sender if ctx.is_group else "")
        return True

    reminders = ctx.robot.reminder_manager.list_reminders(ctx.msg.sender)
    # 在群聊中@用户
    at_list = ctx.msg.sender if ctx.is_group else ""

    if not reminders:
        ctx.send_text("您还没有设置任何提醒。", at_list)
        return True

    reply_parts = ["📝 您设置的提醒列表（包括私聊和群聊）：\n"]
    for i, r in enumerate(reminders):
        # 格式化星期几（如果存在）
        weekday_str = ""
        if r.get("weekday") is not None:
            weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
            weekday_str = f" (每周{weekdays[r['weekday']]})" if 0 <= r['weekday'] <= 6 else ""

        # 格式化时间
        time_display = r['time_str']
        # 添加设置位置标记（群聊/私聊）
        scope_tag = ""
        if r.get('roomid'):
            # 尝试获取群聊名称，如果获取不到就用 roomid
            room_name = ctx.all_contacts.get(r['roomid']) or r['roomid'][:8]
            scope_tag = f"[群:{room_name}]"
        else:
            scope_tag = "[私聊]"
            
        if r['type'] == 'once':
            # 一次性提醒显示完整日期时间
            time_display = f"{scope_tag}{r['time_str']} (一次性)"
        elif r['type'] == 'daily':
            time_display = f"{scope_tag}每天 {r['time_str']}"
        elif r['type'] == 'weekly':
            if 0 <= r.get('weekday', -1) <= 6:
                time_display = f"{scope_tag}每周{weekdays[r['weekday']]} {r['time_str']}"
            else:
                time_display = f"{scope_tag}每周 {r['time_str']}"

        reply_parts.append(
            f"{i+1}. [ID: {r['id'][:6]}] {time_display}: {r['content']}"
        )
    ctx.send_text("\n".join(reply_parts), at_list)
    
    # 尝试触发馈赠（如果在群聊中）
    if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
        ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
    return True

def handle_delete_reminder(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """处理删除提醒命令（支持群聊和私聊）"""
    if not hasattr(ctx.robot, 'reminder_manager'):
        ctx.send_text("❌ 内部错误：提醒管理器未初始化。", ctx.msg.sender if ctx.is_group else "")
        return True

    user_input_description = match.group(2).strip() # 用户描述要删除哪个提醒
    if not user_input_description:
        ctx.send_text("请告诉我您想删除哪个提醒（例如：删除提醒 开会的那个 / 删除提醒 ID: xxxxxx）", ctx.msg.sender if ctx.is_group else "")
        return True

    # 在群聊中@用户
    at_list = ctx.msg.sender if ctx.is_group else ""
    
    # 检查是否要删除所有提醒
    if user_input_description.lower() == "all" or user_input_description == "所有" or user_input_description == "全部":
        success, message, count = ctx.robot.reminder_manager.delete_all_reminders(ctx.msg.sender)
        ctx.send_text(message, at_list)
        
        # 尝试触发馈赠（如果在群聊中）
        if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
            
        return True

    # 检查用户输入是否直接是 ID (简单可靠)
    potential_id_match = re.match(r"^(?:id[:：\s]*)?([a-f0-9]{6,})$", user_input_description, re.IGNORECASE)
    if potential_id_match:
        partial_id = potential_id_match.group(1)
        # 需要从数据库查找完整的 ID
        reminders = ctx.robot.reminder_manager.list_reminders(ctx.msg.sender)
        found_id = None
        possible_matches = 0
        
        for r in reminders:
            if r['id'].startswith(partial_id):
                found_id = r['id']
                possible_matches += 1

        if possible_matches == 1:
            success, message = ctx.robot.reminder_manager.delete_reminder(ctx.msg.sender, found_id)
            ctx.send_text(message, at_list)
        elif possible_matches > 1:
            ctx.send_text(f"❌ 找到多个以 '{partial_id}' 开头的提醒ID，请提供更完整的ID。", at_list)
        else:
            ctx.send_text(f"❌ 未找到 ID 以 '{partial_id}' 开头的提醒。您可以使用 '查看提醒' 获取完整列表和ID。", at_list)
        
        # 尝试触发馈赠（如果在群聊中）
        if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
            ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
            
        return True
    
    # 如果不是ID，则提示用户先查看提醒列表
    ctx.send_text("请先使用 '查看提醒' 命令获取您的提醒列表，然后使用 '删除提醒 ID:xxxxxx' 的格式删除特定提醒。\n如果要删除所有提醒，请使用 '删除提醒 all'。", at_list)
    
    # 尝试触发馈赠（如果在群聊中）
    if ctx.is_group and hasattr(ctx.robot, "goblin_gift_manager"):
        ctx.robot.goblin_gift_manager.try_trigger(ctx.msg)
        
    return True 

def handle_weather(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "天气" 或 "温度" 命令

    匹配: 天气 [城市名] 或 温度 [城市名]
    """
    if not match:
        return False

    city_name = match.group(1).strip()
    if not city_name:
        ctx.send_text("🤔 请告诉我你想查询哪个城市的天气，例如：天气 北京")
        return True

    if ctx.logger:
        ctx.logger.info(f"天气查询指令匹配: 城市={city_name}")

    # --- 加载城市代码 ---
    city_codes: Dict[str, str] = {}
    city_code_path = os.path.join(os.path.dirname(__file__), '..', 'function', 'main_city.json') # 确保路径正确
    try:
        with open(city_code_path, 'r', encoding='utf-8') as f:
            city_codes = json.load(f)
    except FileNotFoundError:
        if ctx.logger:
            ctx.logger.error(f"城市代码文件未找到: {city_code_path}")
        ctx.send_text("⚠️ 抱歉，天气功能所需的城市列表文件丢失了。")
        return True
    except json.JSONDecodeError:
        if ctx.logger:
            ctx.logger.error(f"无法解析城市代码文件: {city_code_path}")
        ctx.send_text("⚠️ 抱歉，天气功能的城市列表文件格式错误。")
        return True
    except Exception as e:
         if ctx.logger:
            ctx.logger.error(f"加载城市代码时发生未知错误: {e}", exc_info=True)
         ctx.send_text("⚠️ 抱歉，加载城市代码时发生错误。")
         return True
    # --- 城市代码加载完毕 ---

    city_code = city_codes.get(city_name)

    if not city_code:
        # 尝试模糊匹配 (可选，如果需要)
        found = False
        for name, code in city_codes.items():
            if city_name in name: # 如果输入的名字是城市全名的一部分
                city_code = code
                city_name = name # 使用找到的完整城市名
                if ctx.logger:
                    ctx.logger.info(f"城市 '{match.group(1).strip()}' 未精确匹配，使用模糊匹配结果: {city_name} ({city_code})")
                found = True
                break
        if not found:
            ctx.send_text(f"😕 找不到城市 '{city_name}' 的天气信息，请检查城市名称是否正确。")
            return True

    # 获取天气信息
    try:
        from function.func_weather import Weather
        weather_info = Weather(city_code).get_weather()
        ctx.send_text(weather_info)
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"获取城市 {city_name}({city_code}) 天气时出错: {e}", exc_info=True)
        ctx.send_text(f"😥 获取 {city_name} 天气时遇到问题，请稍后再试。")

    return True 

def handle_weather_forecast(ctx: 'MessageContext', match: Optional[Match]) -> bool:
    """
    处理 "天气预报" 或 "预报" 命令

    匹配: 天气预报 [城市名] 或 预报 [城市名]
    """
    if not match:
        return False

    city_name = match.group(1).strip()
    if not city_name:
        ctx.send_text("🤔 请告诉我你想查询哪个城市的天气预报，例如：天气预报 北京")
        return True

    if ctx.logger:
        ctx.logger.info(f"天气预报查询指令匹配: 城市={city_name}")

    # --- 加载城市代码 ---
    city_codes: Dict[str, str] = {}
    city_code_path = os.path.join(os.path.dirname(__file__), '..', 'function', 'main_city.json') # 确保路径正确
    try:
        with open(city_code_path, 'r', encoding='utf-8') as f:
            city_codes = json.load(f)
    except FileNotFoundError:
        if ctx.logger:
            ctx.logger.error(f"城市代码文件未找到: {city_code_path}")
        ctx.send_text("⚠️ 抱歉，天气功能所需的城市列表文件丢失了。")
        return True
    except json.JSONDecodeError:
        if ctx.logger:
            ctx.logger.error(f"无法解析城市代码文件: {city_code_path}")
        ctx.send_text("⚠️ 抱歉，天气功能的城市列表文件格式错误。")
        return True
    except Exception as e:
         if ctx.logger:
            ctx.logger.error(f"加载城市代码时发生未知错误: {e}", exc_info=True)
         ctx.send_text("⚠️ 抱歉，加载城市代码时发生错误。")
         return True
    # --- 城市代码加载完毕 ---

    city_code = city_codes.get(city_name)

    if not city_code:
        # 尝试模糊匹配 (可选，如果需要)
        found = False
        for name, code in city_codes.items():
            if city_name in name: # 如果输入的名字是城市全名的一部分
                city_code = code
                city_name = name # 使用找到的完整城市名
                if ctx.logger:
                    ctx.logger.info(f"城市 '{match.group(1).strip()}' 未精确匹配，使用模糊匹配结果: {city_name} ({city_code})")
                found = True
                break
        if not found:
            ctx.send_text(f"😕 找不到城市 '{city_name}' 的天气信息，请检查城市名称是否正确。")
            return True

    # 获取天气信息 (包含预报)
    try:
        from function.func_weather import Weather
        weather_info = Weather(city_code).get_weather(include_forecast=True)  # 注意这里传入True
        ctx.send_text(weather_info)
    except Exception as e:
        if ctx.logger:
            ctx.logger.error(f"获取城市 {city_name}({city_code}) 天气预报时出错: {e}", exc_info=True)
        ctx.send_text(f"😥 获取 {city_name} 天气预报时遇到问题，请稍后再试。")

    return True 