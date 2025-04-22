import re
import logging
from typing import List, Optional, Any, Dict, Match
import traceback

from .models import Command
from .context import MessageContext

# 获取模块级 logger
logger = logging.getLogger(__name__)


class CommandRouter:
    """
    命令路由器，负责将消息路由到对应的命令处理函数
    """
    def __init__(self, commands: List[Command], robot_instance: Optional[Any] = None):
        # 按优先级排序命令列表，数字越小优先级越高
        self.commands = sorted(commands, key=lambda cmd: cmd.priority)
        self.robot_instance = robot_instance
        
        # 分析并输出命令注册信息，便于调试
        scope_count = {"group": 0, "private": 0, "both": 0}
        for cmd in commands:
            scope_count[cmd.scope] += 1
        
        logger.info(f"命令路由器初始化成功，共加载 {len(commands)} 个命令")
        logger.info(f"命令作用域分布: 仅群聊 {scope_count['group']}，仅私聊 {scope_count['private']}，两者均可 {scope_count['both']}")
        
        # 按优先级输出命令信息
        for i, cmd in enumerate(self.commands[:10]):  # 只输出前10个
            logger.info(f"{i+1}. [{cmd.priority}] {cmd.name} - {cmd.description or '无描述'}")
        if len(self.commands) > 10:
            logger.info(f"... 共 {len(self.commands)} 个命令")

    def dispatch(self, ctx: MessageContext) -> bool:
        """
        根据消息上下文分发命令
        :param ctx: 消息上下文对象
        :return: 是否有命令成功处理
        """
        # 确保context可以访问到robot实例
        if self.robot_instance and not ctx.robot:
            ctx.robot = self.robot_instance
            # 如果robot有logger属性且ctx没有logger，则使用robot的logger
            if hasattr(self.robot_instance, 'LOG') and not ctx.logger:
                ctx.logger = self.robot_instance.LOG
        
        # 记录日志，便于调试
        if ctx.logger:
            ctx.logger.debug(f"开始路由消息: '{ctx.text}', 来自: {ctx.sender_name}, 群聊: {ctx.is_group}, @机器人: {ctx.is_at_bot}")
        
        # 遍历命令列表，按优先级顺序匹配
        for cmd in self.commands:
            # 1. 检查作用域 (scope)
            if cmd.scope != "both":
                if (cmd.scope == "group" and not ctx.is_group) or \
                   (cmd.scope == "private" and ctx.is_group):
                    continue  # 作用域不匹配，跳过
            
            # 2. 检查是否需要 @ (need_at) - 仅在群聊中有效
            if ctx.is_group and cmd.need_at and not ctx.is_at_bot:
                continue  # 需要@机器人但未被@，跳过
            
            # 3. 执行匹配逻辑
            match_result = None
            try:
                # 根据pattern类型执行匹配
                if callable(cmd.pattern):
                    # 自定义匹配函数
                    match_result = cmd.pattern(ctx)
                else:
                    # 正则表达式匹配
                    match_obj = cmd.pattern.search(ctx.text)
                    match_result = match_obj
                
                # 匹配失败，尝试下一个命令
                if match_result is None:
                    continue
                
                # 匹配成功，记录日志
                if ctx.logger:
                    ctx.logger.info(f"命令 '{cmd.name}' 匹配成功，准备处理")
                
                # 4. 执行命令处理函数
                try:
                    result = cmd.handler(ctx, match_result)
                    if result:
                        if ctx.logger:
                            ctx.logger.info(f"命令 '{cmd.name}' 处理成功")
                        return True
                    else:
                        if ctx.logger:
                            ctx.logger.warning(f"命令 '{cmd.name}' 处理返回False，尝试下一个命令")
                except Exception as e:
                    if ctx.logger:
                        ctx.logger.error(f"执行命令 '{cmd.name}' 处理函数时出错: {e}")
                        ctx.logger.error(traceback.format_exc())
                    else:
                        logger.error(f"执行命令 '{cmd.name}' 处理函数时出错: {e}", exc_info=True)
                    # 出错后继续尝试下一个命令
            except Exception as e:
                # 匹配过程出错，记录并继续
                if ctx.logger:
                    ctx.logger.error(f"匹配命令 '{cmd.name}' 时出错: {e}")
                else:
                    logger.error(f"匹配命令 '{cmd.name}' 时出错: {e}", exc_info=True)
                continue
        
        # 所有命令都未匹配或处理失败
        if ctx.logger:
            ctx.logger.debug("所有命令匹配失败或处理失败")
        return False
    
    def get_command_descriptions(self) -> Dict[str, str]:
        """获取所有命令的描述，用于生成帮助信息"""
        return {cmd.name: cmd.description for cmd in self.commands if cmd.description} 