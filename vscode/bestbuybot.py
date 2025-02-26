from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from datetime import datetime, time
import pytz
import time as time_module
from plyer import notification
import winsound
import os
import sys
from dotenv import load_dotenv
import random

# Load environment variables
load_dotenv()

class BestBuyMonitor:
    def __init__(self):
        self.url = os.getenv("PRODUCT_URL")
        self.pst_timezone = pytz.timezone('US/Pacific')
        
        # Check intervals (in seconds)
        self.intensive_check_interval = 60  # Every minute
        self.tuesday_check_interval = 3600  # Every hour
        self.default_check_interval = 10800  # Every 3 hours
        
        # Status tracking
        self.last_status = None
        
        # Browser health tracking
        self.check_count = 0
        self.max_checks_before_restart = 20
        
        # Chrome setup with error suppression
        self.options = self._configure_chrome_options()
        self.driver = self._setup_driver()

    def _configure_chrome_options(self):
        """Configure Chrome options with error suppression settings."""
        options = Options()
        
        # Basic headless mode settings
        options.add_argument("--headless=new")  # Use the new headless mode
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Memory and performance optimization
        options.add_argument("--js-flags=--expose-gc")
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--memory-pressure-off")
        options.add_argument("--single-process")  # More stable in some environments
        
        # Simplified error suppression (reduced from original)
        options.add_argument("--disable-notifications")
        options.add_argument("--log-level=3")  # Only show fatal errors
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        
        # Disable UI elements
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        return options

    def _setup_driver(self):
        """Initialize and configure Chrome WebDriver."""
        try:
            # Redirect stderr to suppress driver manager messages
            original_stderr = sys.stderr
            sys.stderr = open(os.devnull, 'w')
            
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=self.options
            )
            
            # Restore stderr
            sys.stderr = original_stderr
            
            # Set page load timeout (increased for reliability)
            driver.set_page_load_timeout(60)
            
            return driver
        except Exception as e:
            print(f"Error setting up Chrome driver: {e}")
            # Restore stderr before raising
            if sys.stderr != original_stderr:
                sys.stderr = original_stderr
            raise

    def is_business_hours(self):
        """Check if current time is within 8:00 AM - 6:00 PM PST."""
        current_time = datetime.now(self.pst_timezone)
        current_time = current_time.time()
        business_start = time(8, 0)   # 8:00 AM PST
        business_end = time(18, 0)    # 6:00 PM PST
        
        return business_start <= current_time <= business_end

    def is_intensive_monitoring_window(self):
        """Check if current time is Wed/Thu 8-10 AM PST."""
        current_time = datetime.now(self.pst_timezone)
        current_weekday = current_time.weekday()
        current_time = current_time.time()
        
        # Wednesday is 2, Thursday is 3
        is_target_day = current_weekday in [2, 3]
        is_target_time = time(8, 0) <= current_time <= time(10, 0)
        
        return is_target_day and is_target_time

    def get_check_interval(self):
        """Determine the appropriate check interval based on current time."""
        current_time = datetime.now(self.pst_timezone)
        current_weekday = current_time.weekday()
        
        # If not business hours, use default interval
        if not self.is_business_hours():
            return self.default_check_interval
            
        # Wednesday/Thursday 8-10 AM: check every minute
        if self.is_intensive_monitoring_window():
            return self.intensive_check_interval
            
        # Tuesday: check every hour
        if current_weekday == 1:  # Tuesday
            return self.tuesday_check_interval
            
        # Default: check every 3 hours
        return self.default_check_interval

    def get_button_status(self):
        """Check the status of the product button."""
        try:
            WebDriverWait(self.driver, 15).until(  # Increased wait time
                EC.presence_of_element_located((By.CSS_SELECTOR, ".add-to-cart-button"))
            )
            
            button = self.driver.find_element(By.CSS_SELECTOR, ".add-to-cart-button")
            button_text = button.text.strip().upper()
            
            # Exact text matching for Best Buy's button states
            if button_text == "COMING SOON":
                return "COMING_SOON"
            elif button_text == "SOLD OUT":
                return "SOLD_OUT"
            elif "ADD TO CART" in button_text:
                return "AVAILABLE"
            else:
                print(f"Unexpected button text: {button_text}")
                return "UNKNOWN"
                
        except TimeoutException:
            print("Timeout while checking button status")
            return "ERROR"
        except Exception as e:
            print(f"Error checking button status: {e}")
            return "ERROR"

    def send_notification(self, message, title="Best Buy Stock Alert"):
        """Send desktop and sound notifications."""
        # Desktop notification
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Best Buy Monitor",
                timeout=10,
            )
        except Exception as e:
            print(f"Desktop notification failed: {e}")

        # Sound alert
        try:
            for _ in range(3):
                winsound.Beep(1000, 500)
                time_module.sleep(0.5)
        except Exception as e:
            print(f"Sound alert failed: {e}")
        
        # Console output
        print("\n" + "!" * 50)
        print(f"\033[91m{title}: {message}\033[0m")
        print("!" * 50 + "\n")

    def should_notify(self, current_status):
        """Determine if we should send a notification based on status change and context."""
        if self.last_status is None:
            self.last_status = current_status
            return False
            
        should_send = False
        current_time = datetime.now(self.pst_timezone)
        current_weekday = current_time.weekday()
        
        # Always notify for AVAILABLE status
        if current_status == "AVAILABLE":
            should_send = True
            
        # On Tuesday, notify for SOLD_OUT to COMING_SOON transition
        elif current_weekday == 1 and self.last_status == "SOLD_OUT" and current_status == "COMING_SOON":
            should_send = True
            
        # During intensive monitoring, notify for any status change
        elif self.is_intensive_monitoring_window() and self.last_status != current_status:
            should_send = True
            
        # During other times, only notify for significant changes
        elif self.last_status != current_status and current_status in ["COMING_SOON", "SOLD_OUT"]:
            should_send = True
            
        self.last_status = current_status
        return should_send

    def get_status_message(self, status, current_interval):
        """Get appropriate message for each status."""
        interval_text = "minute" if current_interval == 60 else "hour" if current_interval == 3600 else "3 hours"
        messages = {
            "COMING_SOON": f"Status changed to COMING SOON! Checking every {interval_text}.",
            "SOLD_OUT": f"Status changed to SOLD OUT. Checking every {interval_text}.",
            "AVAILABLE": "RTX 5080 IS AVAILABLE! GO TO BEST BUY WEBSITE NOW!",
            "UNKNOWN": f"Unknown status detected. Checking every {interval_text}.",
            "ERROR": f"Error checking status. Will retry in {interval_text}..."
        }
        return messages.get(status, "Unexpected status encountered")

    def load_page_with_retry(self, max_retries=3):
        """Load the Best Buy page with retry logic."""
        for attempt in range(1, max_retries + 1):
            try:
                print(f"Loading page, attempt {attempt}/{max_retries}")
                self.driver.get(self.url)
                return True
            except TimeoutException:
                print(f"Page load timeout (attempt {attempt}/{max_retries})")
                if attempt < max_retries:
                    backoff_time = 5 + random.randint(1, 5) * attempt
                    print(f"Retrying in {backoff_time} seconds...")
                    time_module.sleep(backoff_time)
                else:
                    print("Maximum retries reached, restarting browser")
                    self.restart_browser()
                    return False
            except WebDriverException as e:
                print(f"WebDriver error: {e}")
                self.restart_browser()
                return False
        return False

    def restart_browser(self):
        """Safely restart the Chrome browser."""
        print("Restarting Chrome browser...")
        try:
            self.driver.quit()
        except Exception as e:
            print(f"Error closing browser: {e}")
        
        time_module.sleep(5)  # Wait a bit before restarting
        self.driver = self._setup_driver()
        self.check_count = 0
        print("Browser restarted successfully")

    def monitor_stock(self):
        """Main monitoring loop."""
        print(f"Starting Best Buy stock monitoring for: {self.url}")
        print("Monitoring Schedule:")
        print("- Tuesday: Checking every hour")
        print("- Wednesday/Thursday 8-10 AM PST: Checking every minute")
        print("- Other business hours (8 AM - 6 PM PST): Checking every 3 hours")
        print("- Browser will be restarted every 20 checks to prevent timeouts")
        
        while True:
            try:
                current_time = datetime.now(self.pst_timezone)
                current_interval = self.get_check_interval()
                
                print(f"\nChecking at {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                
                # Increment check counter and restart browser if needed
                self.check_count += 1
                if self.check_count >= self.max_checks_before_restart:
                    print(f"Performed {self.check_count} checks, restarting browser as preventive measure")
                    self.restart_browser()
                
                # Load page with retry logic
                if not self.load_page_with_retry():
                    print("Failed to load page after retries, will try again later")
                    time_module.sleep(self.intensive_check_interval)
                    continue
                
                # Check product status
                status = self.get_button_status()
                
                if self.should_notify(status):
                    message = self.get_status_message(status, current_interval)
                    self.send_notification(message, "Stock Status Update")
                else:
                    print(f"Current status: {status}")
                    print(f"Next check in {current_interval/60:.1f} minutes")
                
                # Add a small random variation to the interval to avoid detection
                jitter = random.uniform(0.9, 1.1)
                actual_interval = int(current_interval * jitter)
                time_module.sleep(actual_interval)
                    
            except Exception as e:
                print(f"Error during monitoring: {e}")
                time_module.sleep(self.intensive_check_interval)
            
    def cleanup(self):
        """Clean up resources."""
        try:
            self.driver.quit()
        except Exception as e:
            print(f"Error during cleanup: {e}")

if __name__ == "__main__":
    # Redirect standard error to suppress WebDriver messages
    if not os.getenv("DEBUG", "False").lower() == "true":
        sys.stderr = open(os.devnull, 'w')
    
    monitor = BestBuyMonitor()
    try:
        monitor.monitor_stock()
    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        print("Cleaning up resources...")
        monitor.cleanup()
        # Restore stderr
        sys.stderr = sys.__stderr__