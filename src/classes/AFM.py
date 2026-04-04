import os
import random
from urllib.parse import urlparse
from typing import Any

from status import *
from config import *
from constants import *
from utils import clear_firefox_profile_lock
from llm_provider import generate_text
from price_client import extract_asin, fetch_price_data, format_price_context
from .Twitter import Twitter
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from webdriver_manager.firefox import GeckoDriverManager


def generate_deal_tweet(product: dict) -> str:
    """
    Generates a story-style tweet for an Amazon deal product.
    Randomly alternates between first-person anecdote and casual recommendation
    to keep the account's post history varied.

    Args:
        product (dict): Deal with keys: title, url (and optional price).

    Returns:
        str: Tweet text including the product URL, under 280 chars total.
    """
    title = product["title"]
    url = product["url"]
    tone = random.choice(["anecdote", "casual"])

    if tone == "anecdote":
        prompt = (
            f"Write a short, realistic first-person tweet (under 220 characters, NOT counting the URL) "
            f"about personally needing or wanting a product like this: \"{title}\". "
            f"Sound like a real person, not a marketer. No hashtags. No asterisks. "
            f"Do not wrap the tweet in quotes. Return only the tweet text."
        )
    else:
        prompt = (
            f"Write a short, casual tweet (under 220 characters, NOT counting the URL) "
            f"casually mentioning this product deal to someone who might be shopping for it: \"{title}\". "
            f"Sound like a real person, not an ad. No hashtags. No asterisks. "
            f"Do not wrap the tweet in quotes. Return only the tweet text."
        )

    tweet_body = generate_text(prompt).strip().strip('"').strip("'").strip()

    # Enforce length so URL fits within 280 chars
    max_body = 257 - len(url)  # 280 - 1 newline - 2 buffer
    if len(tweet_body) > max_body:
        tweet_body = tweet_body[:max_body - 3] + "..."

    return f"{tweet_body}\n{url}"


class AffiliateMarketing:
    """
    This class will be used to handle all the affiliate marketing related operations.
    """

    def __init__(
        self,
        affiliate_link: str,
        fp_profile_path: str,
        twitter_account_uuid: str,
        account_nickname: str,
        topic: str,
    ) -> None:
        """
        Initializes the Affiliate Marketing class.

        Args:
            affiliate_link (str): The affiliate link
            fp_profile_path (str): The path to the Firefox profile
            twitter_account_uuid (str): The Twitter account UUID
            account_nickname (str): The account nickname
            topic (str): The topic of the product

        Returns:
            None
        """
        self._fp_profile_path: str = fp_profile_path

        # Initialize the Firefox profile
        self.options: Options = Options()

        # Set headless state of browser
        if get_headless():
            self.options.add_argument("--headless")

        if not os.path.isdir(fp_profile_path):
            raise ValueError(
                f"Firefox profile path does not exist or is not a directory: {fp_profile_path}"
            )

        # Set the profile path
        self.options.add_argument("-profile")
        self.options.add_argument(fp_profile_path)

        # Clear stale profile locks and open browser
        clear_firefox_profile_lock(fp_profile_path)
        service = Service(GeckoDriverManager().install())
        self.browser: webdriver.Firefox = webdriver.Firefox(
            service=service, options=self.options
        )

        # Set the affiliate link
        self.affiliate_link: str = affiliate_link

        parsed_link = urlparse(self.affiliate_link)
        if parsed_link.scheme not in ["http", "https"] or not parsed_link.netloc:
            raise ValueError(
                f"Affiliate link is invalid. Expected a full URL, got: {self.affiliate_link}"
            )

        # Set the Twitter account UUID
        self.account_uuid: str = twitter_account_uuid

        # Set the Twitter account nickname
        self.account_nickname: str = account_nickname

        # Set the Twitter topic
        self.topic: str = topic

        # Scrape the product information
        self.scrape_product_information()

        # Enrich with Keepa price history (uses resolved URL after page load)
        asin = extract_asin(self.browser.current_url)
        price_data = fetch_price_data(asin) if asin else None
        self.price_context: str = format_price_context(price_data)

    def scrape_product_information(self) -> None:
        """
        This method will be used to scrape the product
        information from the affiliate link.
        """
        # Open the affiliate link
        self.browser.get(self.affiliate_link)

        # Get the product name
        product_title: str = self.browser.find_element(
            By.ID, AMAZON_PRODUCT_TITLE_ID
        ).text

        # Get the features of the product
        features: Any = self.browser.find_elements(By.ID, AMAZON_FEATURE_BULLETS_ID)

        if get_verbose():
            info(f"Product Title: {product_title}")

        if get_verbose():
            info(f"Features: {features}")

        # Set the product title
        self.product_title: str = product_title

        # Set the features
        self.features: Any = features

    def generate_response(self, prompt: str) -> str:
        """
        This method will be used to generate the response for the user.

        Args:
            prompt (str): The prompt for the user.

        Returns:
            response (str): The response for the user.
        """
        return generate_text(prompt)

    def generate_pitch(self) -> str:
        """
        This method will be used to generate a pitch for the product.

        Returns:
            pitch (str): The pitch for the product.
        """
        # Build prompt, optionally enriched with Keepa price context
        price_section = f'\nPrice History: "{self.price_context}"' if self.price_context else ""
        prompt = (
            f'I want to promote this product on my website. Generate a brief pitch about this product, '
            f'return nothing else except the pitch. Information:\n'
            f'Title: "{self.product_title}"\n'
            f'Features: "{str(self.features)}"{price_section}\n'
            f'{"If price history is provided, mention whether it is a good time to buy." if self.price_context else ""}'
        )

        # Generate the response
        pitch: str = (
            self.generate_response(prompt)
            + "\nYou can buy the product here: "
            + self.affiliate_link
        )

        self.pitch: str = pitch

        # Return the response
        return pitch

    def share_pitch(self, where: str) -> None:
        """
        This method will be used to share the pitch on the specified platform.

        Args:
            where (str): The platform where the pitch will be shared.
        """
        if where == "twitter":
            # Initialize the Twitter class
            twitter: Twitter = Twitter(
                self.account_uuid,
                self.account_nickname,
                self._fp_profile_path,
                self.topic,
            )

            # Share the pitch
            twitter.post(self.pitch)

    def quit(self) -> None:
        """
        This method will be used to quit the browser.
        """
        # Quit the browser
        self.browser.quit()
