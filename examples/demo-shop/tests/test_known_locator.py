"""TC-006: intentionally obsolete selector. Repair must preserve the cart assertions."""

from pages.shop import ShopPage
from playwright.sync_api import expect


def test_known_locator_change(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.product()
    shop.variant(shop_data["color"], shop_data["size"])
    shop.add_with_legacy_locator()
    shop.cart()
    expect(page.get_by_test_id("cart-item")).to_contain_text(shop_data["product"])
    expect(page.get_by_test_id("cart-total")).to_have_text(f"Total: ${shop_data['price']}.00")
