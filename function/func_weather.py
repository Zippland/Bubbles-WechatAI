import requests, json
import logging
import re  # 导入正则表达式模块，用于提取数字

class Weather:
    def __init__(self, city_code: str) -> None:
        self.city_code = city_code
        self.LOG = logging.getLogger("Weather")
        
    def _extract_temp(self, temp_str: str) -> str:
        """从高温/低温字符串中提取温度数值"""
        if not temp_str:
            return ""
        # 匹配温度数字部分
        match = re.search(r"(\d+(?:\.\d+)?)", temp_str)
        if match:
            return match.group(1)
        return ""

    def get_weather(self, include_forecast: bool = False) -> str:
        # api地址
        url = 'http://t.weather.sojson.com/api/weather/city/'

        # 网络请求，传入请求api+城市代码
        self.LOG.info(f"获取天气: {url + str(self.city_code)}")
        try:
            response = requests.get(url + str(self.city_code))
            self.LOG.info(f"获取天气成功: 状态码={response.status_code}")
            if response.status_code != 200:
                self.LOG.error(f"API返回非200状态码: {response.status_code}")
                return f"获取天气失败: 服务器返回状态码 {response.status_code}"
        except Exception as e:
            self.LOG.error(f"获取天气失败: {str(e)}")
            return "由于网络原因，获取天气失败"

        try:
            # 将数据以json形式返回，这个d就是返回的json数据
            d = response.json()
        except json.JSONDecodeError as e:
            self.LOG.error(f"解析JSON失败: {str(e)}")
            return "获取天气失败: 返回数据格式错误"

        # 当返回状态码为200，输出天气状况
        if(d.get('status') == 200):
            city_info = d.get('cityInfo', {})
            data = d.get('data', {})
            forecast = data.get('forecast', [])
            
            if not forecast:
                self.LOG.warning("API返回的数据中没有forecast字段")
                return "获取天气失败: 数据不完整"
                
            today = forecast[0] if forecast else {}
            
            # 提取今日温度
            low_temp = self._extract_temp(today.get('low', ''))
            high_temp = self._extract_temp(today.get('high', ''))
            temp_range = f"{low_temp}~{high_temp}℃" if low_temp and high_temp else "N/A"
            
            # 基础天气信息（当天）
            result = [
                f"城市：{city_info.get('parent', '')}/{city_info.get('city', '')}",
                f"时间：{d.get('time', '')} {today.get('week', '')}",
                f"温度：{temp_range}",
                f"天气：{today.get('type', '')}"
            ]
            
            # 如果需要预报信息，添加未来几天的天气
            if include_forecast and len(forecast) > 1:
                result.append("\n📅 天气预报:")  # 修改标题
                # 显示未来4天的预报 (索引 1, 2, 3, 4)
                for day in forecast[1:5]:  # 增加到4天预报
                    # 提取星期的最后一个字
                    week_day = day.get('week', '')
                    week_char = week_day[-1] if week_day else ''
                    
                    # 提取温度数值
                    low_temp = self._extract_temp(day.get('low', ''))
                    high_temp = self._extract_temp(day.get('high', ''))
                    temp_range = f"{low_temp}~{high_temp}℃" if low_temp and high_temp else "N/A"
                    
                    # 天气类型
                    weather_type = day.get('type', '未知')
                    
                    # 简化格式：只显示周几、温度范围和天气类型
                    result.append(f"- 周{week_char} {temp_range} {weather_type}")
            
            return "\n".join(result)
        else:
            return "获取天气失败"

if __name__ == "__main__":
    # 设置测试用的日志配置
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # 测试当天天气
    w = Weather("101010100")  # 北京
    logger.info(w.get_weather())  # 不带预报
    
    # 测试天气预报
    logger.info(w.get_weather(include_forecast=True))  # 带预报
