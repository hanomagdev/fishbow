import pyautogui
import time
import gc
import sys
import requests
from PIL import Image
from datetime import datetime
from pyscreeze import ImageNotFoundException

# ========== TELEGRAM SETTINGS ==========
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your bot token
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"  # Replace with your chat ID
TELEGRAM_ENABLED = True  # Set to False to disable Telegram notifications
# =======================================

# ========== SCRIPT SETTINGS ==========
CHECK_INTERVAL = 1  # Check interval in seconds
CONFIDENCE = 0.7    # Confidence level (DO NOT LOWER)
RIGHT_CLICK_DELAY = 0.5  # Delay after right click
SECOND_IMAGE_CONFIDENCE = 0.7  # Confidence for finding the second image
GC_INTERVAL = 1000  # Run garbage collection every N iterations
REPORT_INTERVAL = 60  # Send Telegram report every N seconds (60 = 1 minute)
# =====================================

# Global variables for reporting
last_report_time = time.time()
report_counter = 0

def send_telegram_message(message):
    """Sends a message to Telegram"""
    if not TELEGRAM_ENABLED:
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code != 200:
            print(f"⚠️ Telegram API error: {response.text}")
    except Exception as e:
        print(f"⚠️ Failed to send Telegram message: {e}")

def send_periodic_report(current_time, iteration, success_count, failure_count, uptime_seconds):
    """Sends a summary report to Telegram every minute"""
    global last_report_time, report_counter
    
    current_time_float = time.time()
    if current_time_float - last_report_time >= REPORT_INTERVAL:
        last_report_time = current_time_float
        report_counter += 1
        
        success_rate = (success_count / iteration * 100) if iteration > 0 else 0
        
        # Format uptime
        uptime_hours = uptime_seconds / 3600
        uptime_minutes = (uptime_seconds % 3600) / 60
        
        message = (
            f"📊 *FISHBOWL SCRIPT REPORT #{report_counter}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 *Time:* {current_time}\n"
            f"⏱️ *Uptime:* {uptime_hours:.1f}h ({uptime_minutes:.0f}m)\n"
            f"🔄 *Total checks:* `{iteration:,}`\n"
            f"✅ *Successes:* `{success_count:,}`\n"
            f"❌ *Failures:* `{failure_count:,}`\n"
            f"📈 *Success rate:* `{success_rate:.1f}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *Status:* {'🟢 RUNNING' if success_rate > 50 else '🟡 ACTIVE'}"
        )
        
        send_telegram_message(message)
        print(f"📤 [REPORT] Summary #{report_counter} sent to Telegram")

def is_green_color(rgb, threshold=50):
    r, g, b = rgb
    return g > r + threshold and g > b + threshold

def is_red_color(rgb, threshold=50):
    r, g, b = rgb
    return r > g + threshold and r > b + threshold

def find_green_finish_button(template_path, confidence=CONFIDENCE):
    """
    Finds the Finish button by checking the color at its center
    """
    screenshot = None
    all_locations = None
    
    try:
        # Find all button occurrences on the screen
        all_locations = list(pyautogui.locateAllOnScreen(template_path, confidence=confidence))
        
        if not all_locations:
            return None
        
        # Take a screenshot to check colors
        screenshot = pyautogui.screenshot()
        
        for location in all_locations:
            # Get the center of the found area
            center_x = location.left + location.width // 2
            center_y = location.top + location.height // 2
            
            # Get the color at the center
            pixel_color = screenshot.getpixel((center_x, center_y))
            
            # Check if it's green
            if is_green_color(pixel_color):
                print(f"Found GREEN button! Center color: {pixel_color}")
                return location
            
            # If red is found - skip it
            if is_red_color(pixel_color):
                print(f"Found RED button, skipping. Color: {pixel_color}")
                continue
        
        return None
        
    except ImageNotFoundException:
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error while searching: {e}")
        return None
    finally:
        # Explicitly delete large objects to help garbage collector
        if screenshot:
            del screenshot
        if all_locations:
            del all_locations

def find_and_click_second_image(image_path, confidence=SECOND_IMAGE_CONFIDENCE):
    """
    Finds the second image on screen and left-clicks it
    """
    location = None
    
    try:
        # Find the image
        location = pyautogui.locateOnScreen(image_path, confidence=confidence)
        
        if location:
            center = pyautogui.center(location)
            pyautogui.click(center)
            print(f"✅ Second image found and clicked: {image_path}")
            return True
        else:
            print(f"⚠️ Second image not found: {image_path}")
            return False
            
    except ImageNotFoundException:
        print(f"⚠️ Image not found: {image_path}")
        return False
    except Exception as e:
        print(f"⚠️ Error while searching for second image: {e}")
        return False
    finally:
        if location:
            del location

def press_ctrl_1():
    """Presses Ctrl+1 combination"""
    pyautogui.hotkey('ctrl', '1')
    print("✅ Ctrl+1 pressed")
    time.sleep(0.3)  # Small pause after pressing

def process_button():
    # 1. Look for the green Finish button
    finish_location = find_green_finish_button('finish_button.png', confidence=CONFIDENCE)
    
    if finish_location:
        finish_center = pyautogui.center(finish_location)
        
        # 2. Double click
        pyautogui.doubleClick(finish_center)
        print("✅ Double click on Finish performed!")
        
        # Small pause before right click
        time.sleep(0.3)
        
        # 3. Right click at the same position
        pyautogui.rightClick(finish_center)
        print("✅ Right click performed!")
        
        # Pause for context menu / next window to appear
        time.sleep(RIGHT_CLICK_DELAY)
        
        # 4. Find the second image and click it
        second_image_found = find_and_click_second_image('finish_button_inner.png', confidence=SECOND_IMAGE_CONFIDENCE)
        
        # Clean up
        del finish_center
        
        if second_image_found:
            return True
        else:
            print("⚠️ Second image not found after right click")
            return False
    else:
        return False

def optimize_memory():
    """Runs garbage collection and memory optimization"""
    gc.collect()
    # Optional: log memory usage for debugging (uncomment if you have psutil installed)
    # try:
    #     import psutil
    #     memory_mb = psutil.Process().memory_info().rss / 1024 / 1024
    #     print(f"🧹 Memory usage: {memory_mb:.1f} MB")
    # except ImportError:
    #     pass

# Main program
print("=== Fishbowl Auto-Finish Script (OPTIMIZED - INFINITE RUN) ===")
print(f"Check interval: {CHECK_INTERVAL} seconds")
print(f"Confidence level: {CONFIDENCE}")
print(f"Delay after right click: {RIGHT_CLICK_DELAY} sec")
print(f"Garbage collection every: {GC_INTERVAL} iterations")
print(f"Telegram report every: {REPORT_INTERVAL} seconds")
print(f"Telegram enabled: {'✅ YES' if TELEGRAM_ENABLED else '❌ NO'}")
print("⚠️ Script will run FOREVER - press Ctrl+C to stop")
print("Switch to Fishbowl Client window")
print()

# Send startup message to Telegram
if TELEGRAM_ENABLED:
    send_telegram_message(
        "🚀 *FISHBOWL SCRIPT STARTED*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"⚙️ Check interval: {CHECK_INTERVAL}s\n"
        f"♾️ Mode: INFINITE (will run forever)\n"
        f"🤖 Status: Script is now monitoring"
    )

time.sleep(3)

# Initialize counters
iteration = 0
success_count = 0
failure_count = 0
start_time = time.time()

try:
    while True:
        iteration += 1
        
        current_time_str = datetime.now().strftime("%H:%M:%S")
        
        # Process button
        if process_button():
            success_count += 1
            print(f"[{current_time_str}] ✅ Full success #{success_count} (total checks: {iteration})")
        else:
            failure_count += 1
            print(f"[{current_time_str}] ❌ Failed attempt #{failure_count} (total checks: {iteration})")
            # Press Ctrl+1 after failed attempt
            press_ctrl_1()
        
        # Every 50 checks show status
        if iteration % 50 == 0:
            uptime = time.time() - start_time
            success_rate = (success_count / iteration * 100) if iteration > 0 else 0
            print(f"[{current_time_str}] 📊 Alive. Successes: {success_count}/{iteration} ({success_rate:.1f}%) | Uptime: {uptime/60:.1f} min")
        
        # Send periodic report to Telegram (every minute)
        if TELEGRAM_ENABLED:
            uptime = time.time() - start_time
            send_periodic_report(current_time_str, iteration, success_count, failure_count, uptime)
        
        # Garbage collection every N iterations
        if iteration % GC_INTERVAL == 0:
            optimize_memory()
            print(f"🧹 Garbage collection performed at iteration {iteration}")
        
        # Main sleep
        time.sleep(CHECK_INTERVAL)
        
except KeyboardInterrupt:
    # Calculate final uptime
    uptime = time.time() - start_time
    uptime_hours = uptime / 3600
    uptime_days = uptime / 86400
    
    print(f"\n\n{'='*50}")
    print(f"⏹️ SCRIPT STOPPED (Ctrl+C pressed)")
    print(f"{'='*50}")
    print(f"📊 FINAL STATISTICS:")
    print(f"   - Total checks: {iteration:,}")
    print(f"   - Successful operations: {success_count:,}")
    print(f"   - Failed operations: {failure_count:,}")
    if iteration > 0:
        print(f"   - Success rate: {success_count/iteration*100:.1f}%")
    print(f"   - Total uptime: {uptime_days:.1f} days ({uptime_hours:.1f} hours, {uptime/60:.1f} minutes)")
    print(f"{'='*50}")
    
    # Send final report to Telegram
    if TELEGRAM_ENABLED:
        final_message = (
            f"🛑 *FISHBOWL SCRIPT STOPPED*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"⏱️ Total uptime: {uptime_days:.1f} days ({uptime_hours:.1f} hours)\n"
            f"🔄 Total checks: `{iteration:,}`\n"
            f"✅ Successes: `{success_count:,}`\n"
            f"❌ Failures: `{failure_count:,}`\n"
            f"📈 Final success rate: `{success_count/iteration*100:.1f}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👋 Script terminated by user"
        )
        send_telegram_message(final_message)