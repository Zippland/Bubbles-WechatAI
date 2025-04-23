import re
from .models import Command
from .handlers import (
    handle_help, handle_duel, handle_sneak_attack, handle_duel_rank,
    handle_duel_stats, handle_check_equipment, handle_reset_memory,
    handle_summary, handle_clear_messages, handle_news_request,
    handle_rename, handle_chengyu, handle_chitchat, handle_insult,
    handle_perplexity_ask, handle_reminder, handle_list_reminders, handle_delete_reminder,
    handle_weather, handle_weather_forecast
)

# 命令列表，按优先级排序
# 优先级越小越先匹配
COMMANDS = [
    # ======== 基础系统命令 ========
    Command(
        name="help",
        pattern=re.compile(r"^(info|帮助|指令)$", re.IGNORECASE),
        scope="both",       # 群聊和私聊都支持
        need_at=False,      # 不需要@机器人
        priority=10,        # 优先级较高
        handler=handle_help,
        description="显示机器人的帮助信息"
    ),
    
    # 添加骂人命令
    Command(
        name="insult",
        pattern=re.compile(r"骂一下\s*@([^\s@]+)"),
        scope="group",      # 仅群聊支持
        need_at=True,       # 需要@机器人
        priority=15,        # 优先级较高
        handler=handle_insult,
        description="骂指定用户"
    ),
    
    Command(
        name="reset_memory",
        pattern=re.compile(r"^(reset|重置)$", re.IGNORECASE),
        scope="both",       # 群聊和私聊都支持
        need_at=True,       # 需要@机器人
        priority=20,        # 优先级较高
        handler=handle_reset_memory,
        description="重置机器人缓存里的上下文历史"
    ),
    
    # ======== Perplexity AI 命令 ========
    Command(
        name="perplexity_ask",
        pattern=re.compile(r"^ask\s*(.+)", re.IGNORECASE | re.DOTALL),
        scope="both",       # 群聊和私聊都支持
        need_at=True,      # 需要@机器人
        priority=25,        # 较高优先级，确保在闲聊之前处理
        handler=handle_perplexity_ask,
        description="使用 Perplexity AI 进行深度查询"
    ),
    
    # ======== 消息管理命令 ========
    Command(
        name="summary",
        pattern=re.compile(r"^(summary|总结)$", re.IGNORECASE),
        scope="group",      # 仅群聊支持
        need_at=True,       # 需要@机器人
        priority=30,        # 优先级一般
        handler=handle_summary,
        description="总结群聊最近的消息"
    ),
    
    Command(
        name="clear_messages",
        pattern=re.compile(r"^(clearmessages|清除历史)$", re.IGNORECASE),
        scope="group",      # 仅群聊支持
        need_at=True,       # 需要@机器人
        priority=31,        # 优先级一般
        handler=handle_clear_messages,
        description="从数据库中清除群聊的历史消息记录"
    ),
    
    # ======== 新闻和实用工具 ========
    Command(
        name="weather_forecast",
        pattern=re.compile(r"^(?:天气预报|预报)\s+(.+)$"), # 匹配 天气预报/预报 城市名
        scope="both",      # 群聊和私聊都支持
        need_at=True,      # 需要@机器人
        priority=38,       # 优先级比天气高一点
        handler=handle_weather_forecast,
        description="查询指定城市未来几天的天气预报 (例如：天气预报 北京)"
    ),
    
    Command(
        name="weather",
        pattern=re.compile(r"^(?:天气|温度)\s+(.+)$"), # 匹配 天气/温度 城市名
        scope="both",      # 群聊和私聊都支持
        need_at=True,      # 需要@机器人
        priority=39,       # 优先级设置在新闻命令前
        handler=handle_weather,
        description="查询指定城市的天气 (例如：天气 北京)"
    ),
    
    Command(
        name="news",
        pattern=re.compile(r"^新闻$"),
        scope="both",       # 群聊和私聊都支持
        need_at=True,      # 需要@机器人
        priority=40,        # 优先级一般
        handler=handle_news_request,
        description="获取最新新闻"
    ),
    
    # ======== 决斗系统命令 ========
    Command(
        name="duel",
        pattern=re.compile(r"决斗.*?(?:@|[与和])\s*([^\s@]+)"),
        scope="group",      # 仅群聊支持
        need_at=False,      # 不需要@机器人
        priority=50,        # 优先级较低
        handler=handle_duel,
        description="发起决斗"
    ),
    
    Command(
        name="sneak_attack",
        pattern=re.compile(r"(?:偷袭|偷分).*?@([^\s@]+)"),
        scope="group",      # 仅群聊支持
        need_at=False,      # 不需要@机器人
        priority=51,        # 优先级较低
        handler=handle_sneak_attack,
        description="偷袭其他玩家"
    ),
    
    Command(
        name="duel_rank",
        pattern=re.compile(r"^(决斗排行|决斗排名|排行榜)$"),
        scope="group",      # 仅群聊支持
        need_at=True,      # 不需要@机器人
        priority=52,        # 优先级较低
        handler=handle_duel_rank,
        description="查看决斗排行榜"
    ),
    
    Command(
        name="duel_stats",
        pattern=re.compile(r"^(决斗战绩|我的战绩|战绩查询)(.*)$"),
        scope="group",      # 仅群聊支持
        need_at=True,      # 不需要@机器人
        priority=53,        # 优先级较低
        handler=handle_duel_stats,
        description="查看决斗战绩"
    ),
    
    Command(
        name="check_equipment",
        pattern=re.compile(r"^(我的装备|查看装备)$"),
        scope="group",      # 仅群聊支持
        need_at=True,      # 不需要@机器人
        priority=54,        # 优先级较低
        handler=handle_check_equipment,
        description="查看我的装备"
    ),
    
    Command(
        name="rename",
        pattern=re.compile(r"^改名\s+([^\s]+)\s+([^\s]+)$"),
        scope="group",      # 仅群聊支持
        need_at=True,      # 不需要@机器人
        priority=55,        # 优先级较低
        handler=handle_rename,
        description="更改昵称"
    ),
    
    # ======== 成语系统命令 ========
    Command(
        name="chengyu",
        pattern=re.compile(r"^([#?？])(.+)$"),
        scope="both",       # 群聊和私聊都支持
        need_at=False,      # 不需要@机器人
        priority=60,        # 优先级较低
        handler=handle_chengyu,
        description="成语接龙与查询"
    ),
    
    # ======== 提醒功能 ========
    Command(
        name="reminder",
        pattern=re.compile(r"^(提醒\s*.+)$", re.IGNORECASE | re.DOTALL), # 匹配"提醒"开头（可无空格），捕获包括"提醒"在内的完整内容
        scope="both",    # 支持群聊和私聊
        need_at=True,    # 在群聊中需要@机器人
        priority=35,        # 优先级适中，在基础命令后，复杂功能或闲聊前
        handler=handle_reminder,
        description="设置一个提醒 (例如：提醒 明天下午3点 开会 或 提醒我早上七点起床)"
    ),
    
    Command(
        name="list_reminders",
        pattern=re.compile(r"^(查看提醒|我的提醒|提醒列表)$", re.IGNORECASE),
        scope="both",    # 支持群聊和私聊
        need_at=True,    # 在群聊中需要@机器人
        priority=36, # 优先级略低于设置提醒
        handler=handle_list_reminders,
        description="查看您设置的所有提醒"
    ),
    
    Command(
        name="delete_reminder",
        # 匹配 "删除提醒 " 后跟任意内容，用于删除特定提醒
        pattern=re.compile(r"^(删除提醒|取消提醒)\s+(.+)$", re.IGNORECASE | re.DOTALL),
        scope="both",    # 支持群聊和私聊
        need_at=True,    # 在群聊中需要@机器人
        priority=37,
        handler=handle_delete_reminder,
        description="删除指定的提醒 (例如：删除提醒 ID:xxxxxx)"
    ),
]

# 可以添加一个函数，获取命令列表的简单描述
def get_commands_info():
    """获取所有命令的简要信息，用于调试"""
    info = []
    for i, cmd in enumerate(COMMANDS):
        scope_str = {"group": "仅群聊", "private": "仅私聊", "both": "群聊私聊"}[cmd.scope]
        at_str = "需要@" if cmd.need_at else "不需@"
        info.append(f"{i+1}. [{cmd.priority}] {cmd.name} ({scope_str},{at_str}) - {cmd.description or '无描述'}")
    return "\n".join(info)

# 导出所有命令
__all__ = ["COMMANDS", "get_commands_info"] 