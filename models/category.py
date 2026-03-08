"""Category and subcategory definitions for expense classification."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Subcategory:
    """A subcategory with its slug and human-readable label."""

    slug: str
    label: str


@dataclass(frozen=True)
class Category:
    """An expense category with its slug, label, and subcategories."""

    slug: str
    label: str
    subcategories: tuple[Subcategory, ...]


# ── Master category registry ────────────────────────────────────────────────

CATEGORIES: tuple[Category, ...] = (
    Category(
        slug="food",
        label="Food & Drinks",
        subcategories=(
            Subcategory("restaurant", "Cafe / Restaurant"),
            Subcategory("grocery", "Grocery (Makro, Lotus)"),
            Subcategory("delivery", "Delivery (GrabFood, LINE MAN)"),
            Subcategory("coffee", "Coffee / Drinks"),
            Subcategory("street_food", "Street Food"),
        ),
    ),
    Category(
        slug="transport",
        label="Transport",
        subcategories=(
            Subcategory("fuel", "Fuel / EV Charging"),
            Subcategory("taxi", "Taxi (Grab, Bolt)"),
            Subcategory("rental", "Bike / Car Rental"),
            Subcategory("flights", "Flights"),
            Subcategory("bus_train", "Bus / Train"),
        ),
    ),
    Category(
        slug="housing",
        label="Housing",
        subcategories=(
            Subcategory("rent", "Rent"),
            Subcategory("utilities", "Utilities (water, electric, internet)"),
            Subcategory("maintenance", "Repair / Cleaning"),
            Subcategory("furniture", "Furniture / Appliances"),
        ),
    ),
    Category(
        slug="health",
        label="Health",
        subcategories=(
            Subcategory("pharmacy", "Pharmacy"),
            Subcategory("gym", "Gym / Fitness"),
            Subcategory("medical", "Doctor / Lab Tests"),
            Subcategory("insurance", "Insurance"),
            Subcategory("dental", "Dental"),
        ),
    ),
    Category(
        slug="entertainment",
        label="Entertainment",
        subcategories=(
            Subcategory("cinema", "Cinema / Theater"),
            Subcategory("sports", "Sports / Activities"),
            Subcategory("bars", "Bars / Clubs"),
            Subcategory("games", "Games"),
            Subcategory("events", "Events / Concerts"),
        ),
    ),
    Category(
        slug="shopping",
        label="Shopping",
        subcategories=(
            Subcategory("clothes", "Clothes / Shoes"),
            Subcategory("electronics", "Electronics"),
            Subcategory("cosmetics", "Cosmetics / Personal Care"),
            Subcategory("gifts", "Gifts"),
            Subcategory("household", "Household Items"),
        ),
    ),
    Category(
        slug="education",
        label="Education",
        subcategories=(
            Subcategory("courses", "Courses / Classes"),
            Subcategory("books", "Books / Materials"),
            Subcategory("tutoring", "Tutoring"),
        ),
    ),
    Category(
        slug="services",
        label="Services",
        subcategories=(
            Subcategory("banking", "Banking / Finance"),
            Subcategory("legal", "Legal / Notary"),
            Subcategory("laundry", "Laundry"),
            Subcategory("postal", "Postal / Courier"),
        ),
    ),
    Category(
        slug="subscriptions",
        label="Subscriptions",
        subcategories=(
            Subcategory("streaming", "Streaming (Netflix, Spotify)"),
            Subcategory("software", "Software / SaaS"),
            Subcategory("cloud", "Cloud Storage"),
            Subcategory("news", "News / Magazines"),
        ),
    ),
    Category(
        slug="travel",
        label="Travel",
        subcategories=(
            Subcategory("accommodation", "Hotel / Hostel / AirBnB"),
            Subcategory("tours", "Tours / Excursions"),
            Subcategory("visa", "Visa / Border Run"),
            Subcategory("luggage", "Luggage"),
        ),
    ),
    Category(
        slug="other",
        label="Other",
        subcategories=(
            Subcategory("cash_withdrawal", "Cash Withdrawal / ATM"),
            Subcategory("transfer", "Transfer / Top-up"),
            Subcategory("charity", "Charity / Donation"),
            Subcategory("misc", "Miscellaneous"),
        ),
    ),
)

# ── Convenience look-ups ────────────────────────────────────────────────────

CATEGORY_BY_SLUG: dict[str, Category] = {c.slug: c for c in CATEGORIES}

CATEGORY_SLUGS: tuple[str, ...] = tuple(c.slug for c in CATEGORIES)

SUBCATEGORY_SLUGS: frozenset[str] = frozenset(
    s.slug for c in CATEGORIES for s in c.subcategories
)


def get_category(slug: str) -> Category | None:
    """Return a Category by slug, or None if not found."""
    return CATEGORY_BY_SLUG.get(slug.lower())


def get_subcategory(category_slug: str, subcategory_slug: str) -> Subcategory | None:
    """Return a Subcategory within a given category, or None."""
    cat = get_category(category_slug)
    if cat is None:
        return None
    for sub in cat.subcategories:
        if sub.slug == subcategory_slug.lower():
            return sub
    return None


def category_label(slug: str) -> str:
    """Return the human-readable label for a category slug."""
    cat = get_category(slug)
    return cat.label if cat else slug.capitalize()


def subcategory_label(category_slug: str, subcategory_slug: str) -> str:
    """Return the human-readable label for a subcategory slug."""
    sub = get_subcategory(category_slug, subcategory_slug)
    return sub.label if sub else subcategory_slug.replace("_", " ").capitalize()
