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

    def filter(self, category=None, maximum_price=None):
        if category is not None:
            self.page.get_by_label("Category", exact=True).select_option(category)
        if maximum_price is not None:
            self.page.get_by_label("Maximum price", exact=True).fill(str(maximum_price))
        self.page.get_by_role("button", name="Search", exact=True).click()

    def product(self, name="Everyday Tee"):
        self.page.get_by_role("button", name=f"View {name}").click()

    def variant(self, color="Navy", size="M"):
        self.page.get_by_label("Color", exact=True).select_option(color)
        self.page.get_by_label("Size", exact=True).select_option(size)

    def add(self):
        self.page.get_by_role("button", name="Add to cart", exact=True).click()

    def add_with_legacy_locator(self):
        """Retained stale selector for the real failure/repair demonstration."""
        self.page.locator('[data-testid="legacy-add-cart"]').click()

    def cart(self):
        self.page.get_by_role("button", name="Cart (", exact=False).click()
