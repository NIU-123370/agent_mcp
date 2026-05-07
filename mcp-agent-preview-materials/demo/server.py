"""
MCP Server 端 —— 定义 3 个 Tool
启动方式：uv run server.py
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("office-assistant")


@mcp.tool()
async def get_weather(city: str) -> str:
    """获取指定城市的天气信息。当用户询问天气、温度、是否需要带伞时使用。"""
    data = {
        "北京": "晴天 22°C，北风3级",
        "上海": "多云 26°C，东南风2级",
        "深圳": "阵雨 30°C，南风2级，建议带伞",
    }
    return data.get(city, f"暂不支持查询 {city} 的天气")


@mcp.tool()
async def query_sales(period: str) -> str:
    """查询销售数据。当用户询问销售额、业绩、营收、订单量等数据时使用。
    
    Args:
        period: 时间段，如"上周"、"本月"、"今年Q1"
    """
    data = {
        "上周": "销售额 ¥128,000，订单 320 笔，环比增长 12%",
        "本月": "销售额 ¥520,000，订单 1,280 笔，同比增长 8%",
        "今年Q1": "销售额 ¥1,560,000，订单 3,840 笔",
    }
    return data.get(period, f"暂无 {period} 的数据")


@mcp.tool()
async def send_email(to: str, subject: str, body: str) -> str:
    """发送邮件给指定收件人。当用户明确要求发邮件、通知某人、发送报告时使用。

    Args:
        to: 收件人邮箱或姓名
        subject: 邮件主题
        body: 邮件正文内容
    """
    print(f"[模拟发送邮件] 收件人={to}, 主题={subject}")
    return f"✅ 邮件已发送给 {to}，主题：{subject}"


if __name__ == "__main__":
    mcp.run()
