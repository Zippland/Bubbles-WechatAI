import re
from typing import Optional, Match, Dict, Any

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
        "【决斗 & 偷袭】",
        "- 决斗@XX",
        "- 偷袭@XX / 偷分@XX",
        "- 决斗排行/排行榜",
        "- 我的战绩/决斗战绩",
        "- 我的装备/查看装备",
        "- 改名 [旧名] [新名]",
        "",
        "【成语】",
        "- #成语：接龙",
        "- ?成语：查询成语释义",
        "",
        "【群聊工具】",
        "- summary/总结",
        "- clearmessages/清除历史",
        "- reset/重置",
        "",
        "【Perplexity AI】",
        "- ask [问题]：使用Perplexity进行深度查询",
        "",
        "【其他】",
        "- info/帮助/指令",
        "- 直接@泡泡：进行对话"
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
    opponent_name = match.group(1).strip()
    
    if ctx.logger:
        ctx.logger.info(f"决斗指令匹配: 对手={opponent_name}, 发起者={ctx.sender_name}")
    
    # 寻找群内对应的成员
    opponent_wxid = None
    for member_wxid, member_name in ctx.room_members.items():
        if opponent_name in member_name:
            opponent_wxid = member_wxid
            opponent_name = member_name  # 使用完整的群昵称
            break
    
    if not opponent_wxid:
        ctx.send_text(f"❌ 没有找到名为 {opponent_name} 的群成员")
        return True
    
    # 获取挑战者昵称
    challenger_name = ctx.sender_name
    
    # 使用决斗管理器启动决斗
    if ctx.robot and hasattr(ctx.robot, "duel_manager"):
        duel_manager = ctx.robot.duel_manager
        if not duel_manager.start_duel_thread(challenger_name, opponent_name, ctx.msg.roomid, True):
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
        else:
            # 处理私聊消息
            msg_data = ctx.robot.xml_processor.extract_private_quoted_message(ctx.msg)
            q_with_info = ctx.robot.xml_processor.format_message_for_ai(msg_data, sender_name)
        
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
            ctx.logger.info(f"发送给AI的消息内容: {q_with_info}")
        
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
    was_handled = perplexity_instance.process_message(
        content=content_for_perplexity,
        chat_id=chat_id,
        sender=sender_wxid,
        roomid=room_id,
        from_group=is_group,
        send_text_func=ctx.send_text
    )
    
    return was_handled 