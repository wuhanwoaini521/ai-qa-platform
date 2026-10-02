from playwright.sync_api import expect


class ShopPage:
    def __init__(self, page, base_url):
        self.page, self.base_url = page, base_url

    def open(self):
        self.page.goto(self.base_url)
        expect(self.page.get_by_role("heading", name="Good things. Simple choices.")).to_be_visible()

    def search(self, term):
        self.page.get_by_role("textbox", name="Search products").fill(term)
        self.page.get_by_role("button", name="Search", exact=True).click()

    def product(self, name="Everyday Tee"):
        self.page.get_by_role("button", name=f"View {name}").click()

    def variant(self, color="Navy", size="M"):
        self.page.get_by_label("Color", exact=True).select_option(color)
        self.page.get_by_label("Size", exact=True).select_option(size)

    def add(self):
        self.page.get_by_role("button", name="Add to cart", exact=True).click()

    def cart(self):
        self.page.get_by_role("button", name="Cart (", exact=False).click()
