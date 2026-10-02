"""Conservative browser action policy, independent of model output."""

import re
from urllib.parse import unquote


def classify_browser_action(action: str, *, name="", tag="", href="", input_type="") -> str:
    if action in {"observe", "screenshot", "inspect", "read"}:
        return "READ_ONLY"
    text = unquote(f"{name} {href}").lower()
    if re.search(r"delete|remove|destroy|unsubscribe|删除|移除|销户|注销账户", text):
        return "DESTRUCTIVE"
    if (
        re.search(
            r"pay|purchase|checkout|place.?order|submit|send|publish|logout|sign.?out|支付|付款|下单|订单|购买|发送|提交|发布|退出登录",
            text,
        )
        or input_type == "submit"
    ):
        return "STATE_CHANGE"
    if action == "hover" or tag == "a" and href and not href.lower().startswith(("javascript:", "mailto:", "tel:")):
        return "SAFE_INTERACTION"
    if action == "click" and re.search(
        r"view|details|help|learn|expand|collapse|next|previous|tab|查看|详情|帮助|展开|收起|下一|上一", text
    ):
        return "SAFE_INTERACTION"
    return "STATE_CHANGE"
