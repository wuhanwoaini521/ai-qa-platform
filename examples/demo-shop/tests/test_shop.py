"""TC-001..005: real user flows with independent UI and data oracles."""

from pages.shop import ShopPage
from playwright.sync_api import expect


def test_search(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.search(shop_data["query"])
    expect(page.get_by_role("heading", name=shop_data["product"], exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="View Canvas Tote")).to_have_count(0)


def test_product_detail(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.product(shop_data["product"])
    expect(page.get_by_role("heading", name=shop_data["product"], exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Add to cart", exact=True)).to_be_enabled()


def test_select_variant(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.product()
    shop.variant(shop_data["color"], shop_data["size"])
    expect(page.get_by_label("Color", exact=True)).to_have_value(shop_data["color"])
    expect(page.get_by_label("Size", exact=True)).to_have_value(shop_data["size"])


def test_add_to_cart(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.product()
    shop.variant(shop_data["color"], shop_data["size"])
    shop.add()
    shop.cart()
    item = page.get_by_test_id("cart-item")
    expect(item).to_contain_text(shop_data["product"])
    expect(item).to_contain_text(f"{shop_data['color']} · {shop_data['size']} · Quantity: 1")
    expect(page.get_by_test_id("cart-total")).to_have_text(f"Total: ${shop_data['price']}.00")


def test_empty_search(page, shop_url):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.search("nonexistent-qa-product")
    expect(page.get_by_role("status")).to_have_text("No products found. Try another search.")
    expect(page.get_by_role("button", name="View", exact=False)).to_have_count(0)


def test_category_and_price_filters(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.filter(shop_data["category"], shop_data["maximum_price"])
    expect(page.get_by_role("heading", name=shop_data["product"], exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="View Canvas Tote")).to_have_count(0)
    expect(page.get_by_role("button", name="View Trail Bottle")).to_have_count(0)


def test_repeated_add_merges_quantity_and_total(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.product()
    shop.variant(shop_data["color"], shop_data["size"])
    shop.add()
    shop.add()
    shop.cart()
    expect(page.get_by_test_id("cart-item")).to_contain_text(
        f"{shop_data['color']} · {shop_data['size']} · Quantity: 2"
    )
    expect(page.get_by_test_id("cart-total")).to_have_text(f"Total: ${shop_data['price'] * 2}.00")


def test_cart_quantity_controls_and_remove(page, shop_url, shop_data):
    shop = ShopPage(page, shop_url)
    shop.open()
    shop.product()
    shop.variant(shop_data["color"], shop_data["size"])
    shop.add()
    shop.cart()

    page.get_by_role("button", name=f"Increase quantity of {shop_data['product']}").click()
    expect(page.get_by_test_id("cart-total")).to_have_text(f"Total: ${shop_data['price'] * 2}.00")
    page.get_by_role("button", name=f"Decrease quantity of {shop_data['product']}").click()
    expect(page.get_by_test_id("cart-total")).to_have_text(f"Total: ${shop_data['price']}.00")
    page.get_by_role("button", name=f"Remove {shop_data['product']}").click()
    expect(page.get_by_role("status")).to_have_text("Your cart is empty.")
    expect(page.get_by_test_id("cart-total")).to_have_text("Total: $0.00")
