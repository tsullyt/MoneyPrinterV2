import schedule
import subprocess
import threading
import time

from art import *
from cache import *
from utils import *
from config import *
from status import *
from uuid import uuid4
from constants import *
from classes.Tts import TTS
from termcolor import colored
from classes.Twitter import Twitter
from classes.YouTube import YouTube
from prettytable import PrettyTable
from classes.Outreach import Outreach
from classes.AFM import AffiliateMarketing
from price_client import get_price_status
from llm_provider import list_models, select_model, get_active_model

def main():
    """Main entry point for the application, providing a menu-driven interface
    to manage YouTube, Twitter bots, Affiliate Marketing, and Outreach tasks.

    This function allows users to:
    1. Start the YouTube Shorts Automater to manage YouTube accounts, 
       generate and upload videos, and set up CRON jobs.
    2. Start a Twitter Bot to manage Twitter accounts, post tweets, and 
       schedule posts using CRON jobs.
    3. Manage Affiliate Marketing by creating pitches and sharing them via 
       Twitter accounts.
    4. Initiate an Outreach process for engagement and promotion tasks.
    5. Exit the application.

    The function continuously prompts users for input, validates it, and 
    executes the selected option until the user chooses to quit.

    Args:
        None

    Returns:
        None"""

    # Get user input
    # user_input = int(question("Select an option: "))
    valid_input = False
    while not valid_input:
        try:
    # Show user options
            info("\n============ OPTIONS ============", False)

            for idx, option in enumerate(OPTIONS):
                print(colored(f" {idx + 1}. {option}", "cyan"))

            info("=================================\n", False)
            user_input = input("Select an option: ").strip()
            if user_input == '':
                print("\n" * 100)
                raise ValueError("Empty input is not allowed.")
            user_input = int(user_input)
            valid_input = True
        except ValueError as e:
            print("\n" * 100)
            print(f"Invalid input: {e}")


    # Start the selected option
    if user_input == 1:
        info("Starting YT Shorts Automater...")

        cached_accounts = get_accounts("youtube")

        if len(cached_accounts) == 0:
            warning("No accounts found in cache. Create one now?")
            user_input = question("Yes/No: ")

            if user_input.lower() == "yes":
                generated_uuid = str(uuid4())

                success(f" => Generated ID: {generated_uuid}")
                nickname = question(" => Enter a nickname for this account: ")
                fp_profile = question(" => Enter the path to the Firefox profile: ")
                niche = question(" => Enter the account niche: ")
                language = question(" => Enter the account language: ")

                account_data = {
                    "id": generated_uuid,
                    "nickname": nickname,
                    "firefox_profile": fp_profile,
                    "niche": niche,
                    "language": language,
                    "videos": [],
                }

                add_account("youtube", account_data)

                success("Account configured successfully!")
        else:
            table = PrettyTable()
            table.field_names = ["ID", "UUID", "Nickname", "Niche"]

            for account in cached_accounts:
                table.add_row([cached_accounts.index(account) + 1, colored(account["id"], "cyan"), colored(account["nickname"], "blue"), colored(account["niche"], "green")])

            print(table)
            info("Type 'd' to delete an account.", False)

            user_input = question("Select an account to start (or 'd' to delete): ").strip()

            if user_input.lower() == "d":
                delete_input = question("Enter account number to delete: ").strip()
                account_to_delete = None

                for account in cached_accounts:
                    if str(cached_accounts.index(account) + 1) == delete_input:
                        account_to_delete = account
                        break

                if account_to_delete is None:
                    error("Invalid account selected. Please try again.", "red")
                else:
                    confirm = question(f"Are you sure you want to delete '{account_to_delete['nickname']}'? (Yes/No): ").strip().lower()

                    if confirm == "yes":
                        remove_account("youtube", account_to_delete["id"])
                        success("Account removed successfully!")
                    else:
                        warning("Account deletion canceled.", False)

                return

            selected_account = None

            for account in cached_accounts:
                if str(cached_accounts.index(account) + 1) == user_input:
                    selected_account = account

            if selected_account is None:
                error("Invalid account selected. Please try again.", "red")
                main()
            else:
                youtube = YouTube(
                    selected_account["id"],
                    selected_account["nickname"],
                    selected_account["firefox_profile"],
                    selected_account["niche"],
                    selected_account["language"]
                )

                while True:
                    rem_temp_files()
                    info("\n============ OPTIONS ============", False)

                    for idx, youtube_option in enumerate(YOUTUBE_OPTIONS):
                        print(colored(f" {idx + 1}. {youtube_option}", "cyan"))

                    info("=================================\n", False)

                    # Get user input
                    user_input = int(question("Select an option: "))
                    tts = TTS()

                    if user_input == 1:
                        youtube.generate_video(tts)
                        upload_to_yt = question("Do you want to upload this video to YouTube? (Yes/No): ")
                        if upload_to_yt.lower() == "yes":
                            if not youtube.upload_video():
                                warning("Upload failed — check the error above for details.")
                    elif user_input == 2:
                        youtube.generate_news_video(tts)
                        upload_to_yt = question("Do you want to upload this news video to YouTube? (Yes/No): ")
                        if upload_to_yt.lower() == "yes":
                            if not youtube.upload_video():
                                warning("Upload failed — check the error above for details.")
                    elif user_input == 3:
                        videos = youtube.get_videos()

                        if len(videos) > 0:
                            videos_table = PrettyTable()
                            videos_table.field_names = ["ID", "Date", "Title"]

                            for video in videos:
                                videos_table.add_row([
                                    videos.index(video) + 1,
                                    colored(video["date"], "blue"),
                                    colored(video["title"][:60] + "...", "green")
                                ])

                            print(videos_table)
                        else:
                            warning(" No videos found.")
                    elif user_input == 4:
                        info("What type of content do you want to schedule?")

                        info("\n============ OPTIONS ============", False)
                        for idx, ct_option in enumerate(YOUTUBE_CONTENT_TYPE_OPTIONS):
                            print(colored(f" {idx + 1}. {ct_option}", "cyan"))
                        info("=================================\n", False)

                        content_type_input = int(question("Select a type: "))

                        if content_type_input == 3:
                            break

                        cron_purpose = "youtube" if content_type_input == 1 else "youtube_news"

                        info("How often do you want to upload?")
                        info("\n============ OPTIONS ============", False)
                        for idx, cron_option in enumerate(YOUTUBE_CRON_OPTIONS):
                            print(colored(f" {idx + 1}. {cron_option}", "cyan"))
                        info("=================================\n", False)

                        user_input = int(question("Select an Option: "))

                        cron_script_path = os.path.join(ROOT_DIR, "src", "cron.py")
                        command = ["python", cron_script_path, cron_purpose, selected_account['id'], get_active_model()]

                        def job():
                            subprocess.run(command)

                        if user_input == 1:
                            schedule.every(1).day.do(job)
                            success("Set up CRON Job.")
                        elif user_input == 2:
                            schedule.every().day.at("10:00").do(job)
                            schedule.every().day.at("16:00").do(job)
                            success("Set up CRON Job.")
                        elif user_input == 3:
                            schedule.every().day.at("08:00").do(job)
                            schedule.every().day.at("12:00").do(job)
                            schedule.every().day.at("18:00").do(job)
                            success("Set up CRON Job.")
                        else:
                            break
                    elif user_input == 5:
                        if get_verbose():
                            info(" => Climbing Options Ladder...", False)
                        break
    elif user_input == 2:
        info("Starting Auto Deal Tweet...")

        cached_accounts = get_accounts("twitter")

        if len(cached_accounts) == 0:
            warning("No Twitter accounts found. Add one via the Twitter Bot menu first.")
        else:
            table = PrettyTable()
            table.field_names = ["ID", "UUID", "Nickname", "Topic"]

            for account in cached_accounts:
                table.add_row([
                    cached_accounts.index(account) + 1,
                    colored(account["id"], "cyan"),
                    colored(account["nickname"], "blue"),
                    colored(account["topic"], "green")
                ])

            print(table)
            user_input = question("Select a Twitter account to post from: ").strip()

            selected_account = None
            for account in cached_accounts:
                if str(cached_accounts.index(account) + 1) == user_input:
                    selected_account = account

            if selected_account is None:
                error("Invalid account selected. Please try again.", "red")
                main()
            else:
                from scrapers.amazon_deals import scrape_top_deals
                from classes.AFM import generate_deal_tweet
                import random

                info("Scraping Amazon deals (this may take a moment)...")
                deals = scrape_top_deals(selected_account["firefox_profile"], limit=20)

                if not deals:
                    error("No deals found. Try again later.")
                else:
                    posted_content = " ".join(p["content"] for p in selected_account.get("posts", []))
                    fresh_deals = [d for d in deals if d["url"] not in posted_content]
                    if not fresh_deals:
                        warning("All scraped deals have already been posted. Try again later for new deals.")
                        return
                    product = random.choice(fresh_deals)
                    info(f"Selected deal: {product['title'][:80]}")
                    tweet_text = generate_deal_tweet(product)
                    info("Generated tweet:")
                    print(colored(tweet_text, "cyan"))

                    post_now = question("Post this tweet now? (Yes/No): ")
                    if post_now.lower() == "yes":
                        twitter = Twitter(
                            selected_account["id"],
                            selected_account["nickname"],
                            selected_account["firefox_profile"],
                            selected_account["topic"]
                        )
                        twitter.post(tweet_text)

                    setup_cron = question("Set up automated deal tweeting? (Yes/No): ")
                    if setup_cron.lower() == "yes":
                        info("How often do you want to post?")
                        info("\n============ OPTIONS ============", False)
                        for idx, cron_option in enumerate(TWITTER_CRON_OPTIONS):
                            print(colored(f" {idx + 1}. {cron_option}", "cyan"))
                        info("=================================\n", False)

                        cron_choice = int(question("Select an Option: "))
                        cron_script_path = os.path.join(ROOT_DIR, "src", "cron.py")
                        command = ["python", cron_script_path, "afm_twitter", selected_account["id"], get_active_model()]

                        def deal_job():
                            subprocess.run(command)

                        if cron_choice == 1:
                            schedule.every(1).day.do(deal_job)
                            success("Set up daily deal tweet CRON Job.")
                        elif cron_choice == 2:
                            schedule.every().day.at("10:00").do(deal_job)
                            schedule.every().day.at("16:00").do(deal_job)
                            success("Set up twice-daily deal tweet CRON Job.")
                        elif cron_choice == 3:
                            schedule.every().day.at("08:00").do(deal_job)
                            schedule.every().day.at("12:00").do(deal_job)
                            schedule.every().day.at("18:00").do(deal_job)
                            success("Set up thrice-daily deal tweet CRON Job.")

    elif user_input == 3:
        if get_verbose():
            print(colored(" => Quitting...", "blue"))
        sys.exit(0)
    else:
        error("Invalid option selected. Please try again.", "red")
        main()
    

if __name__ == "__main__":
    # Print ASCII Banner
    print_banner()

    first_time = get_first_time_running()

    if first_time:
        print(colored("Hey! It looks like you're running MoneyPrinter V2 for the first time. Let's get you setup first!", "yellow"))

    # Setup file tree
    assert_folder_structure()

    # Remove temporary files
    rem_temp_files()

    # Fetch MP3 Files
    fetch_songs()

    # Select Ollama model — use config value if set, otherwise pick interactively
    configured_model = get_ollama_model()
    if configured_model:
        select_model(configured_model)
        success(f"Using configured model: {configured_model}")
    else:
        try:
            models = list_models()
        except Exception as e:
            error(f"Could not connect to Ollama: {e}")
            sys.exit(1)

        if not models:
            error("No models found on Ollama. Pull a model first (e.g. 'ollama pull llama3.2:3b').")
            sys.exit(1)

        info("\n========== OLLAMA MODELS =========", False)
        for idx, model_name in enumerate(models):
            print(colored(f" {idx + 1}. {model_name}", "cyan"))
        info("==================================\n", False)

        model_choice = None
        while model_choice is None:
            raw = input(colored("Select a model: ", "magenta")).strip()
            try:
                choice_idx = int(raw) - 1
                if 0 <= choice_idx < len(models):
                    model_choice = models[choice_idx]
                else:
                    warning("Invalid selection. Try again.")
            except ValueError:
                warning("Please enter a number.")

        select_model(model_choice)
        success(f"Using model: {model_choice}")

    def _run_scheduler():
        while True:
            schedule.run_pending()
            time.sleep(30)

    scheduler_thread = threading.Thread(target=_run_scheduler, daemon=True)
    scheduler_thread.start()

    while True:
        main()
