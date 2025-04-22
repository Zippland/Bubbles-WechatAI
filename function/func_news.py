#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import logging
import time
from datetime import datetime

import requests
from lxml import etree


class News(object):
    def __init__(self) -> None:
        self.LOG = logging.getLogger(__name__)
        self.week = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/110.0"}

    def get_important_news(self):
        """
        获取重要新闻。
        返回一个元组 (is_today, news_content)。
        is_today: 布尔值，True表示是当天新闻，False表示是旧闻或获取失败。
        news_content: 格式化后的新闻字符串，或在失败时为空字符串。
        """
        url = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=7.7.5"
        data = {"type": "telegram", "keyword": "你需要知道的隔夜全球要闻", "page": 0,
                "rn": 1, "os": "web", "sv": "7.7.5", "app": "CailianpressWeb"}
        try:
            rsp = requests.post(url=url, headers=self.headers, data=data)
            data = json.loads(rsp.text)["data"]["telegram"]["data"][0]
            news = data["descr"]
            timestamp = data["time"]
            ts = time.localtime(timestamp)
            weekday_news = datetime(*ts[:6]).weekday()
            
            # 格式化新闻内容
            fmt_time = time.strftime("%Y年%m月%d日", ts)
            news = re.sub(r"(\d{1,2}、)", r"\n\1", news)
            fmt_news = "".join(etree.HTML(news).xpath(" // text()"))
            fmt_news = re.sub(r"周[一|二|三|四|五|六|日]你需要知道的", r"", fmt_news)
            formatted_news = f"{fmt_time} {self.week[weekday_news]}\n{fmt_news}"
            
            # 检查是否是当天新闻
            weekday_now = datetime.now().weekday()
            date_news_str = time.strftime("%Y%m%d", ts)
            date_now_str = time.strftime("%Y%m%d", time.localtime())
            
            # 使用日期字符串比较，而不是仅比较星期
            is_today = (date_news_str == date_now_str)
            
            if is_today:
                return (True, formatted_news)  # 当天新闻
            else:
                self.LOG.info(f"获取到的是旧闻 (发布于 {fmt_time})")
                return (False, formatted_news)  # 旧闻
                
        except Exception as e:
            self.LOG.error(e)
            return (False, "")  # 获取失败


if __name__ == "__main__":
    # 设置测试用的日志配置
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    news = News()
    is_today, content = news.get_important_news()
    logger.info(f"Is Today: {is_today}")
    logger.info(content)
