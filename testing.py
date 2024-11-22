from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
import os
import time
import json
from urllib.parse import urlparse
import shutil
import re


def create_game_download_directory(base_download_dir, game_name):
    safe_game_name = "".join(c for c in game_name if c.isalnum() or c in [' ', '-', '_']).rstrip()
    safe_game_name = safe_game_name[:50]
    game_download_dir = os.path.join(base_download_dir, safe_game_name)

    if os.path.exists(game_download_dir):
        shutil.rmtree(game_download_dir)

    os.makedirs(game_download_dir, exist_ok=True)
    return game_download_dir


def get_download_percentage(driver):
    try:
        logs = driver.get_log('performance')
        total_size = None
        downloaded_size = 0

        for entry in logs:
            try:
                message = json.loads(entry['message'])['message']

                if 'Network.responseReceivedExtraInfo' in str(message):
                    headers = message.get('params', {}).get('headers', {})
                    size_match = re.search(r'Content-Length: (\d+)', str(headers), re.IGNORECASE)
                    if size_match:
                        total_size = int(size_match.group(1))

                if message.get('method') == 'Network.dataReceived':
                    downloaded_size += message['params'].get('dataLength', 0)
            except (KeyError, json.JSONDecodeError, ValueError):
                continue

        if total_size and total_size > 0:
            percentage = min(100, (downloaded_size / total_size) * 100)
            return round(percentage, 2)
        return None
    except Exception:
        return None


def create_driver_with_extension(download_dir, extension_path):
    options = Options()

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "safebrowsing.disable_download_protection": True
    }
    options.add_experimental_option("prefs", prefs)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-infobars")
    options.add_argument("--no-sandbox")
    #options.add_argument("--headless")  # Uncomment for headless mode
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")

    if extension_path and os.path.exists(extension_path):
        options.add_extension(extension_path)

    caps = DesiredCapabilities.CHROME
    caps['goog:loggingPrefs'] = {'performance': 'ALL'}
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    service = Service(r"C:\chromedriver-win64\chromedriver.exe")
    return webdriver.Chrome(service=service, options=options)


def wait_for_download_to_complete(download_dir, timeout=600):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not any(file.endswith('.crdownload') for file in os.listdir(download_dir)):
            return True
        time.sleep(1)
    return False


def handle_redirect_and_click(driver, download_button, download_dir):
    main_tab = driver.current_window_handle
    main_domain = urlparse(driver.current_url).netloc

    try:
        download_button.click()
        time.sleep(2)

        new_tabs = driver.window_handles
        if len(new_tabs) > 1:
            for tab in new_tabs:
                if tab != main_tab:
                    driver.switch_to.window(tab)
                    redirect_domain = urlparse(driver.current_url).netloc
                    time.sleep(2)
                    if redirect_domain != main_domain:
                        print(f"Redirect detected: {redirect_domain}. Closing tab.")
                        driver.close()
                    driver.switch_to.window(main_tab)
                    break

        time.sleep(1)
        download_button.click()

        start_time = time.time()
        while time.time() - start_time < 300:
            percentage = get_download_percentage(driver)
            if percentage is not None:
                print(f"Download Progress: {percentage}%")

            if wait_for_download_to_complete(download_dir):
                print("Download completed successfully.")
                return True

            time.sleep(2)

        print("Download did not complete within timeout.")
        return False
    except Exception as e:
        print(f"Error in download process: {e}")
        return False


def process_links_sequentially(links, download_dir, extension_path):
    driver = create_driver_with_extension(download_dir, extension_path)
    try:
        for index, link in enumerate(links):
            print(f"Downloading: Part {str(index + 1).zfill(2)}")
            driver.get(link)
            time.sleep(5)

            wait = WebDriverWait(driver, 10)
            download_button = wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/div[2]/div/div[1]/button')))

            handle_redirect_and_click(driver, download_button, download_dir)
            time.sleep(2)
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()


def search_game(driver, game_name):
    search_url = f"https://fitgirl-repacks.site/?s={'+'.join(game_name.split())}"
    driver.get(search_url)
    time.sleep(2)

    try:
        posts = driver.find_elements(By.XPATH, "//*[contains(@id, 'post-')]")

        if not posts:
            print("No posts found matching the search.")
            return None

        for idx, post in enumerate(posts, 1):
            try:
                title_element = post.find_element(By.XPATH, ".//header/h1/a")
                title = title_element.text
                url = title_element.get_attribute("href")
                print(f"{idx}. {title} - {url}")
            except Exception as e:
                print(f"Error extracting post details: {e}")

        choice = int(input("Enter the number of your choice: ")) - 1
        if 0 <= choice < len(posts):
            selected_post = posts[choice]
            game_url = selected_post.find_element(By.XPATH, ".//header/h1/a").get_attribute("href")
            post_id = selected_post.get_attribute("id")
            driver.get(game_url)
            time.sleep(2)

            fast_link = driver.find_element(By.XPATH, f'//*[@id="{post_id}"]/div/ul[1]/li[2]/a').get_attribute("href")
            return fast_link
        else:
            print("Invalid choice, please try again.")
            return None
    except Exception as e:
        print(f"An error occurred while searching for the game: {e}")
        return None


def main():
    game_name = input("Enter the name of the game you want to download: ")
    base_download_dir = r"G:\Downloads"
    extension_path = r"C:\chromedriver-win64\uBlock.crx"

    download_dir = create_game_download_directory(base_download_dir, game_name)

    driver = create_driver_with_extension(download_dir, extension_path)

    try:
        while True:
            game_link = search_game(driver, game_name)
            if game_link:
                driver.get(game_link)
                time.sleep(5)
                links = [a.get_attribute("href") for a in
                         driver.find_elements(By.XPATH, '//*[@id="plaintext"]/ul/li/a')]
                process_links_sequentially(links, download_dir, extension_path)
                break
            else:
                print("Game not found.")
                game_name = input("Enter the name of the game you want to download: ")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
