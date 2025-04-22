#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import signal
import logging
import sys  # 导入 sys 模块
import os
from argparse import ArgumentParser

# 确保日志目录存在
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 配置 logging
log_format = '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
logging.basicConfig(
    level=logging.INFO,  # 设置日志级别为 INFO，意味着 INFO, WARNING, ERROR, CRITICAL 都会被记录
    format=log_format,
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "app.log"), encoding='utf-8'), # 将日志写入文件
        logging.StreamHandler(sys.stdout) # 同时输出到控制台
    ]
)

# 如果想让某些第三方库的日志不那么详细，可以单独设置它们的日志级别
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

from function.func_report_reminder import ReportReminder
from configuration import Config
from constants import ChatType
from robot import Robot, __version__
from wcferry import Wcf

def main(chat_type: int):
    config = Config()
    wcf = Wcf(debug=True)
    
    # 定义全局变量robot，使其在handler中可访问
    global robot
    robot = Robot(config, wcf, chat_type)

    def handler(sig, frame):
        # 先清理机器人资源（包括关闭数据库连接）
        if 'robot' in globals() and robot:
            robot.LOG.info("程序退出，开始清理资源...")
            robot.cleanup()
            
        # 再清理wcf环境
        wcf.cleanup()  # 退出前清理环境
        exit(0)

    signal.signal(signal.SIGINT, handler)

    robot.LOG.info(f"WeChatRobot【{__version__}】成功启动···")

    # 机器人启动发送测试消息
    robot.sendTextMsg("机器人启动成功！", "filehelper")

    # 接收消息
    # robot.enableRecvMsg()     # 可能会丢消息？
    robot.enableReceivingMsg()  # 加队列

    # 每天 7 点发送天气预报
    robot.onEveryTime("07:00", robot.weatherReport)

    # 每天 7:30 发送新闻
    robot.onEveryTime("07:30", robot.newsReport)

    # 每天 16:30 提醒发日报周报月报
    robot.onEveryTime("16:30", ReportReminder.remind, robot=robot)

    # 让机器人一直跑
    robot.keepRunningAndBlockProcess()


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('-c', type=int, default=0, 
                        help=f'选择默认模型参数序号: {ChatType.help_hint()}（可通过配置文件为不同群指定模型）')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='启用调试模式，输出更详细的日志信息')
    args = parser.parse_args()
    
    # 如果启用了调试模式，则将日志级别设置为 DEBUG
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.info("已启用调试模式，将显示详细日志信息")
    
    main(args.c)
