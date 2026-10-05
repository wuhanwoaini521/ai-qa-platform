"""Conservative browser action policy, independent of model output."""

import re
from urllib.parse import unquote


def classify_browser_action(action: str, *, name="", tag="", href="", input_type="") -> str:
    if action in {"observe", "screenshot", "inspect", "read", "back", "scroll", "wait"}:
        return "READ_ONLY"
    text = unquote(f"{name} {href}").lower()
    if re.search(r"delete|remove|destroy|unsubscribe|删除|移除|销户|注销账户", text):
        return "DESTRUCTIVE"
    if re.search(
        r"pay|purchase|checkout|place.?order|submit|send|publish|logout|sign.?out|change.?password|update.?profile|"
        r"delete.?account|account.?settings|subscribe|sign.?up|支付|付款|下单|订单|购买|发送|提交|发布|退出登录|"
        r"修改密码|账户设置|删除账户|注销账户|订阅",
        text,
    ):
        return "STATE_CHANGE"
    if action == "add_to_cart" or re.search(
        r"add.?to.?cart|add.?to.?bag|add.?to.?basket|加入购物车|加入购物袋|添加到购物车|添加到购物袋", text
    ):
        return "SAFE_INTERACTION"
    if input_type == "submit":
        if action in {"filter", "search"} and re.search(r"search|filter|筛选|搜索|查询", text):
            return "SAFE_INTERACTION"
        return "STATE_CHANGE"
    if action in {"open_product", "filter", "choose_variant"}:
        return "SAFE_INTERACTION"
    if action == "hover" or tag == "a" and href and not href.lower().startswith(("javascript:", "mailto:", "tel:")):
        return "SAFE_INTERACTION"
    if action == "click" and re.search(
        r"view|details|help|learn|expand|collapse|next|previous|tab|查看|详情|帮助|展开|收起|下一|上一", text
    ):
        return "SAFE_INTERACTION"
    return "STATE_CHANGE"
