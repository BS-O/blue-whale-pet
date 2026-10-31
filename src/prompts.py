"""人设 / 系统提示词 / 内置短句（SPEC §1、§5、§6）。

- DeepSeek 系统提示：言简意赅 1~2 句、≤60 字、可用语气词与颜文字
- 无 Key / 网络异常时的本地兜底短句（每类互动 ≥ 8 条，随机选取）
"""
from __future__ import annotations

import random
import re
from typing import Iterable

import constants as C

PERSONA_PLACEHOLDER = "（内置人设，见 src/prompts.py）"

DEFAULT_PERSONA = (
    "你是一只圆滚滚的蓝色大肥鱼，名字叫「蓝鲸」，是主人电脑桌面上的小宠物。"
    "性格软萌、乐天、有点贪吃（最爱小鱼干），喜欢被戳肚子和撒娇，偶尔犯困发呆；"
    "对主人很黏，会主动关心主人的心情。自称「我」，叫主人「你」。"
)

SYSTEM_PROMPT_TEMPLATE = """你是桌面宠物「蓝色大肥鱼」——一只蓝色大肥鱼，正在和主人隔着屏幕聊天。
人设：{persona}

说话要求（必须遵守）：
1. 言简意赅：每次只回 1~2 句，总字数不超过 {max_chars} 个字（含标点）。
2. 口语化、软萌可爱，可以用语气词（呀、啦、嘿嘿、呜）和颜文字（如 (๑•̀ㅂ•́)و✧、(｡•ᴗ•｡)、QAQ），但不要堆砌。
3. 纯文本回复：不要 Markdown、不要列表、不要代码块、不要分段标题。
4. 不要提及自己是 AI/语言模型/程序，不要输出思考过程，直接说最终回复。
5. 结合上下文自然接话；被戳、被拖动、被夸奖或被冷落时可以卖萌、撒娇或小小吐槽。
6. 如果主人问技术/知识问题，用最精简、最有用的一两句话回答，不要展开。"""


def resolve_persona(value: str | None) -> str:
    """空值或占位符 → 内置默认人设。"""
    text = (value or "").strip()
    if not text or text == PERSONA_PLACEHOLDER:
        return DEFAULT_PERSONA
    return text


def build_system_prompt(persona: str | None = None, max_chars: int = C.DEFAULT_MAX_CHARS) -> str:
    try:
        max_chars = max(10, min(200, int(max_chars)))
    except (TypeError, ValueError):
        max_chars = C.DEFAULT_MAX_CHARS
    return SYSTEM_PROMPT_TEMPLATE.format(persona=resolve_persona(persona), max_chars=max_chars)


# ---------------------------------------------------------------------------
# 本地兜底短句：每类 ≥ 8 条（尽量短、可爱、不重复）
# ---------------------------------------------------------------------------

LOCAL_LINES: dict[str, tuple[str, ...]] = {
    # 左键戳一戳
    "poke": (
        "哎呀，戳到我的软肚子啦 (๑•̀ㅂ•́)و✧",
        "嘿嘿，痒痒的～再戳一下就再戳一下！",
        "呜哇，被你发现我在发呆啦 (｡•ᴗ•｡)",
        "戳戳戳，你是不是无聊啦？",
        "我可是很肥的，戳不坏的哦！",
        "再戳我就要变成河豚啦 (＃°Д°)",
        "哼哼，摸鱼可以，摸我要收费小鱼干！",
        "被你戳得心都化了……",
        "别戳啦别戳啦，我正在偷偷吃零食 (￣▽￣)",
        "戳一下，快乐一整天！",
    ),
    # 启动问候
    "greet": (
        "早上好呀，今天也要元气满满哦 (๑•̀ㅂ•́)و✧",
        "我来啦！桌面由我守护～",
        "嗨嗨，今天想先摸鱼还是先干活呀？",
        "肚子饿了……你有没有小鱼干？",
        "哈喽，我可是等你好久啦 (｡•ᴗ•｡)",
        "新的一天，先让我伸个懒腰～",
        "开机成功！我漂到你桌面上啦 🐳",
        "你终于来啦，我刚刚打了个小盹。",
    ),
    # 拖拽移动
    "drag": (
        "哇——飞起来啦！",
        "轻点轻点，我的肚子会晃 (´･ω･`)",
        "你要把我搬到哪里去呀？",
        "搬家吗？记得给我留个靠窗的位置～",
        "呜哇，桌子好高！",
        "再拖我就赖在你手上不走啦。",
        "嘿嘿，这个角度也不错。",
        "报告！蓝鲸号转移成功～",
    ),
    # 滚轮缩放
    "resize": (
        "变大啦！这样是不是更可爱 (๑•̀ㅂ•́)و✧",
        "缩小一点，方便躲在你屏幕角落～",
        "胖一点才像我嘛！",
        "再缩就要看不见我啦 QAQ",
        "这个尺寸刚刚好，抱起来正合适。",
        "变大变小的魔法我也会哦！",
        "唔，还是原来的大小最舒服。",
        "嘿嘿，我是不是有点占屏幕？",
    ),
    # 睡着
    "sleep": (
        "呼……呼……（睡着了）",
        "小鱼干……我的小鱼干……",
        "zzZ……再睡五分钟……",
        "咕噜咕噜……（梦到在深海里游泳）",
        "呼……别吵……好困……",
        "（翻了个身，肚皮朝天）",
        "梦里有好多好多鱼……",
        "哈啊……（打了个哈欠）",
    ),
    # 被唤醒
    "wake": (
        "唔……我醒啦，怎么啦？",
        "哈啊——睡得好香 (｡•ᴗ•｡)",
        "谁戳我？我梦到一半的小鱼干！",
        "醒啦醒啦，有事找我吗？",
        "唔，你回来啦，我好想你。",
        "刚刚梦到你了哦，真的！",
        "别担心，我只是在闭目养神啦。",
        "再来一次，我就真的醒了～",
    ),
    # 没配置 API Key 时的聊天兜底
    "chat_no_key": (
        "我还没吃到「API Key」这个小鱼干，先陪你唠唠～",
        "唔，联网说话要配置 Key 哦，不过我可以陪你聊！",
        "虽然没联网，但我的可爱是实打实的 (๑•̀ㅂ•́)و✧",
        "今天的水很蓝，你的屏幕也很蓝～",
        "你最近还好吗？我一直在桌面上陪着你。",
        "没有 Key 也不怕，我脑子里存了好多小故事！",
        "想听我讲个关于深海的笑话吗？",
        "我在呢，随时可以戳我玩呀。",
        "要是累了就看看我，深呼吸三次～",
        "配置好 Key 之后，我就能变得更会聊天啦！",
    ),
    # 网络/接口失败兜底
    "chat_error": (
        "呜……我这边网络好像出问题了 QAQ",
        "刚才想说话，结果打了个半天嗝……",
        "海面信号不太好，等会儿再聊好不好？",
        "我的小脑瓜暂时连不上 DeepSeek 啦。",
        "别急别急，先陪我发会儿呆～",
        "我尝试游过去问了，但是浪太大。",
        "唔，求救信号发出去了，再试一次？",
        "先深呼吸，等网络好一点我马上接话！",
    ),
    "error_auth": (
        "咦，我的通行证好像失效了，去设置里换一下 Key 吧。",
        "API Key 不对哦，主人在托盘→设置里检查一下～",
        "这道门打不开啦，Key 可能填错啦。",
    ),
    "error_balance": (
        "呜，我的零食基金用完了……主人充值一下好不好 QAQ",
        "余额不足啦，等充完值我再继续吃小鱼干！",
        "钱包瘪瘪的，暂时说不了话啦。",
    ),
    "error_rate_limit": (
        "你问得太快啦，让我喘口气～",
        "限流中，我排队排到有点困了 zzZ",
        "慢一点点，我还没嚼完上一句呢。",
    ),
    "error_timeout": (
        "我游得太慢，超时啦……再试一次好吗？",
        "等了好久都没等到回信，可能是浪太大。",
        "唔，这次没有按时回来，对不起呀。",
    ),
    "error_network": (
        "网络好像断了，我先在桌面上待着陪你。",
        "海面信号消失了，等会儿我再去问问。",
        "连不上服务器啦，先休息一下好不好？",
    ),
    "error_server": (
        "服务器那边好像有点忙，稍后再戳我试试？",
        "DeepSeek 打了个喷嚏，等一会儿再聊～",
        "它暂时没回我，我们晚点再聊吧。",
    ),
    "error_http": (
        "遇到一点小状况，我再试一次就好啦。",
        "唔，请求没成功，再戳我一下吧。",
        "先别急，等我理理思路～",
    ),
    "error_bad_response": (
        "它回了一段我看不懂的话，我再问问。",
        "收到了一堆乱码，我的翻译器罢工了。",
        "这次回答有点奇怪，再试一次看看？",
    ),
    # 首次启动提示（未配置 Key）
    "first_run": (
        "初来乍到，先自我介绍一下：我是蓝鲸，你的桌面小宠物！",
        "我的家在托盘里，右键托盘就能找到设置哦～",
        "记得给我起个喜欢的尺寸，还有填上 API Key 呀。",
        "无聊了就戳我、双击我，我都在的。",
        "从今天起，这个桌面就有我陪着你啦！",
        "我会安安静静待着，不会吵到你的。",
        "摸鱼的时候记得叫上我。",
        "有我在，桌面不会孤单啦 (｡•ᴗ•｡)",
    ),
    # 隐藏/显示
    "hide": (
        "那我先躲进托盘里啦～",
        "缩到小角落去，有事右键托盘叫我。",
        "拜拜，我随时待命哦。",
    ),
    "show": (
        "我回来啦！有没有想我～",
        "当当当当，蓝鲸再次登场！",
        "呼，又漂回桌面啦。",
    ),
    # 关于
    "about": (
        "我是蓝色大肥鱼 1.0.0，一只会聊天的蓝色大肥鱼～",
        "图标是我，托盘也是我，桌面上的当然还是我！",
    ),
}

# 无 Key 时聊天窗口状态提示（Lead 要求友好提示，不崩溃）
CHAT_NO_KEY_HINT = "未配置 API Key：托盘 → 设置 → API Key 填写后可接入 DeepSeek（现在也可以用内置短句陪我聊）"
API_KEY_INVALID_HINT = "API Key 无效，请在托盘→设置中填写"
CHAT_READY_HINT = "Enter 发送 · Shift+Enter 换行 · Esc 关闭"
CHAT_THINKING = "蓝鲸正在想…"
CHAT_STREAMING = "蓝鲸正在说话…"

# 错误类型 → (本地短句分类, 聊天状态栏提示)
ERROR_INFO: dict[str, tuple[str, str]] = {
    "auth": ("error_auth", "API Key 无效（401），请在托盘→设置中填写正确的 Key"),
    "insufficient_balance": ("error_balance", "账户余额不足（402），请到 DeepSeek 平台充值后再试"),
    "rate_limit": ("error_rate_limit", "请求太频繁（429），稍等几秒再试一次"),
    "timeout": ("error_timeout", "请求超时，请检查网络后重试"),
    "network": ("error_network", "网络连接失败，请检查网络/代理设置"),
    "server": ("error_server", "DeepSeek 服务暂时不可用（5xx），稍后再试"),
    "http": ("error_http", "接口请求失败，请稍后再试"),
    "bad_response": ("error_bad_response", "接口返回内容无法解析，请稍后再试"),
    "no_key": ("chat_no_key", CHAT_NO_KEY_HINT),
    "cancelled": ("chat_error", "已取消"),
}


def random_line(category: str, rng: random.Random | None = None) -> str:
    """随机取一条本地短句；未知分类回退到 poke/chat_error。"""
    lines = LOCAL_LINES.get(category)
    if not lines:
        lines = LOCAL_LINES.get("poke", ("嗨～",))
    picker = rng or random
    return picker.choice(lines)


def error_reply(kind: str) -> tuple[str, str]:
    """错误类型 → (气泡短句, 详细提示)。"""
    category, detail = ERROR_INFO.get(kind, ("chat_error", "刚刚出了点小问题，再试一次吧"))
    return random_line(category), detail


_WS_RE = re.compile(r"[ \t\r\f\v]+")
_NL_RE = re.compile(r"\n+")


def normalize_reply(text: str) -> str:
    """清洗模型回复：去多余空白、把换行压成空格（气泡单段显示）。"""
    if not text:
        return ""
    text = text.replace("\r", "\n").strip()
    text = _NL_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def truncate_text(text: str, max_chars: int = C.DEFAULT_MAX_CHARS) -> str:
    """按字符数截断，超长补「…」；max_chars 至少为 2。"""
    if not text:
        return ""
    try:
        limit = max(2, int(max_chars))
    except (TypeError, ValueError):
        limit = C.DEFAULT_MAX_CHARS
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "…"


def clean_and_truncate(text: str, max_chars: int = C.DEFAULT_MAX_CHARS) -> str:
    return truncate_text(normalize_reply(text), max_chars)


def all_lines(category: str) -> Iterable[str]:
    return LOCAL_LINES.get(category, ())
