import re
from dataclasses import dataclass
from typing import Pattern, Callable, Literal, Optional, Any, Union, Match

# 导入 MessageContext，使用前向引用避免循环导入
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .context import MessageContext


@dataclass
class Command:
    """
    命令定义类，封装命令的匹配条件和处理函数
    """
    name: str                 # 命令名称，用于日志和调试
    pattern: Union[Pattern, Callable[['MessageContext'], Optional[Match]]]  # 匹配规则：正则表达式或自定义匹配函数
    scope: Literal["group", "private", "both"]  # 生效范围: "group"-仅群聊, "private"-仅私聊, "both"-两者都可
    handler: Callable[['MessageContext', Optional[Match]], bool]  # 处理函数
    need_at: bool = False     # 在群聊中是否必须@机器人才能触发
    priority: int = 100       # 优先级，数字越小越先匹配
    description: str = ""     # 命令的描述，用于生成帮助信息

    def __post_init__(self):
        """验证命令配置的有效性"""
        if self.scope not in ["group", "private", "both"]:
            raise ValueError(f"无效的作用域: {self.scope}，必须是 'group', 'private' 或 'both'")
        
        # 检查pattern是否为正则表达式或可调用对象
        if not isinstance(self.pattern, (Pattern, Callable)):
            # 如果是字符串，尝试转换为正则表达式
            if isinstance(self.pattern, str):
                try:
                    self.pattern = re.compile(self.pattern)
                except re.error:
                    raise ValueError(f"无效的正则表达式: {self.pattern}")
            else:
                raise TypeError(f"pattern 必须是正则表达式或可调用对象，而不是 {type(self.pattern)}") 