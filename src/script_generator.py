import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def clean_percentage(val):
    """Format float percentage (e.g., -0.012 -> 1.2)."""
    return abs(round(val * 100, 1))


def format_currency(val):
    """Format integer price to currency string (e.g., 540000 -> $540,000)."""
    return f"${val:,}"


def generate_script(stats_data):
    """
    Generate a punchy 45-55 second YouTube Shorts voiceover script.
    Rules:
    - Hook question or shocking stat opener
    - Short sentences (max 12 words each)
    - Exactly 3 key data points
    - End with CTA: "Follow for daily real estate updates"
    - Target word count: 90-110 words (~50 seconds at normal pace)
    """
    city = stats_data["city"]
    price = format_currency(stats_data["medianPrice"])
    rent = format_currency(stats_data["medianRent"])

    sale_mom = stats_data["saleMoM"]
    rent_mom = stats_data["rentalMoM"]

    sale_change_val = clean_percentage(sale_mom)
    rent_change_val = clean_percentage(rent_mom)

    sale_dir = "up" if sale_mom >= 0 else "down"
    rent_dir = "up" if rent_mom >= 0 else "down"
    sale_action = "rising" if sale_mom >= 0 else "dropping"
    rent_action = "rose" if rent_mom >= 0 else "dropped"
    rent_signal = "Renters are facing higher costs." if rent_mom >= 0 else "Renters are getting some relief."
    price_signal = "Sellers still hold the edge here." if sale_mom >= 0 else "Buyers may find more negotiating power now."

    new_listings = stats_data["newListings"]
    total_listings = stats_data["totalListings"]

    # A/B testing: alternate templates based on day of year
    yday = datetime.now().timetuple().tm_yday

    if yday % 2 == 0:
        # Template A: Shocking Stat Hook (~100 words)
        script = (
            f"Rents in {city} just {rent_action} {rent_change_val} percent. "
            f"Here is exactly what that means for you. "
            f"Let us break down the latest market data right now. "
            f"Data point one. Median rent is {rent} per month. "
            f"That is {rent_dir} {rent_change_val} percent month over month. "
            f"{rent_signal} "
            f"Data point two. Median home price is now {price}. "
            f"Prices are {sale_action} {sale_change_val} percent recently. "
            f"{price_signal} "
            f"Data point three. There are {total_listings:,} active listings right now. "
            f"That includes {new_listings:,} brand new listings this week alone. "
            f"Is {city} the right market for you right now? "
            f"Follow for daily real estate updates."
        )
        logger.info("Using Script Template A (Shocking Stat Hook)")
    else:
        # Template B: Question Hook (~100 words)
        script = (
            f"Is the {city} housing market about to crash? "
            f"Or is this actually your best buying opportunity? "
            f"Let us look at three key numbers right now. "
            f"Number one. The median home price is {price}. "
            f"That is {sale_action} {sale_change_val} percent month over month. "
            f"{price_signal} "
            f"Number two. Median rent sits at {rent} per month. "
            f"Rent is {rent_dir} {rent_change_val} percent compared to last month. "
            f"{rent_signal} "
            f"Number three. There are {total_listings:,} active listings in {city}. "
            f"And {new_listings:,} new listings just hit the market this week. "
            f"So what is your next move in {city}? "
            f"Follow for daily real estate updates."
        )
        logger.info("Using Script Template B (Question Hook)")

    word_count = len(script.split())
    logger.info(f"Generated script ({word_count} words):\n{script}")

    # Warn on out-of-range word count
    if word_count < 85 or word_count > 115:
        logger.warning(f"Script word count {word_count} is outside 85-115 range.")

    return script


def get_hook_stat(stats_data):
    """Generate a clean hook stat string for the video title."""
    rent_mom = stats_data["rentalMoM"]
    sale_mom = stats_data["saleMoM"]
    rent_change_val = clean_percentage(rent_mom)
    sale_change_val = clean_percentage(sale_mom)
    rent_dir = "up" if rent_mom >= 0 else "down"
    sale_dir = "up" if sale_mom >= 0 else "down"
    # Alternate between rent and price hook based on which is more dramatic
    if abs(rent_mom) >= abs(sale_mom):
        return f"Rent {rent_dir} {rent_change_val}%"
    else:
        return f"Prices {sale_dir} {sale_change_val}%"
