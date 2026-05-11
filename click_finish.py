import pyautogui
import time
import gc
import sys
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
from datetime import datetime
from pyscreeze import ImageNotFoundException
import re
import os
import numpy as np

# ========== EASYOCR SETUP ==========
import easyocr
# ===================================

# ========== TELEGRAM SETTINGS ==========
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your bot token
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"  # Replace with your chat ID
TELEGRAM_ENABLED = False  # Set to True to enable Telegram notifications
# =======================================

# ========== SCRIPT SETTINGS ==========
CHECK_INTERVAL = 2  # Check interval in seconds
CONFIDENCE = 0.7    # Confidence level (DO NOT LOWER)
RIGHT_CLICK_DELAY = 0.5  # Delay after right click
SECOND_IMAGE_CONFIDENCE = 0.7  # Confidence for finding the second image
GC_INTERVAL = 1000  # Run garbage collection every N iterations
REPORT_INTERVAL = 60  # Send Telegram report every N seconds (60 = 1 minute)
STATUS_PRINT_INTERVAL = 50  # Print status every N iterations
# =======================================

# ========== TEST MODE SETTINGS ==========
TEST_MODE = True  # Set to True to ONLY check and visualize, NOT click anything
TEST_MODE_DELAY = 3  # Seconds to wait after each detection in test mode
# =========================================

# ========== SKIP CONDITIONS ==========
# Regular expressions for skipping based on Pick column text
SKIP_PICK_PATTERNS = [
    r'^W.*$',    # Starts with W (e.g., W, W123, WORD)
    r'^T.*$',    # Starts with T (e.g., T, T123, TEXT)
    r'POS',      # Contains POS
]
USE_SIMPLE_TEXT_MATCH = False  # Set to True to use simple text matching instead of regex
SKIP_PICK_TEXTS = []  # Simple text list for matching (e.g., ["Commit...", "Entered"])
# ===========================================

# ========== OCR REGION SETTINGS ==========
PICK_COLUMN_X_OFFSET = 5   # Distance from button center to start of Pick column (pixels)
PICK_COLUMN_WIDTH = 150    # Width of the region to check (pixels)
PICK_COLUMN_VERTICAL_PADDING = 10  # Extra pixels above and below button for OCR region
OCR_IMAGE_SCALE = 4        # Scale factor for image before OCR (higher = better but slower)
OCR_CONTRAST_ENHANCE = 2.5  # Contrast enhancement factor (1.0 = no change)
OCR_USE_SHARPEN = True     # Apply sharpening filter before OCR
# ===========================================

# ========== COLOR DETECTION SETTINGS ==========
GREEN_THRESHOLD = 50  # Threshold for detecting green color (higher = stricter)
RED_THRESHOLD = 50    # Threshold for detecting red color (higher = stricter)
# ===============================================

# ========== VISUALIZATION SETTINGS ==========
VISUALIZE_DEBUG = True  # Set to True to save debug images
DEBUG_IMAGES_FOLDER = "debug_images"  # Folder to save debug images
SAVE_OCR_REGIONS = True  # Save cropped OCR regions for debugging
MAX_DEBUG_IMAGES = 100  # Maximum number of debug images to keep
# ===========================================

# ========== FILE SETTINGS ==========
FINISH_BUTTON_IMAGE = 'finish_button.png'
SECOND_IMAGE = 'finish_button_inner.png'
# ===================================

# ========== INITIALIZATION ==========
# Create debug folder if it doesn't exist
if VISUALIZE_DEBUG and not os.path.exists(DEBUG_IMAGES_FOLDER):
    os.makedirs(DEBUG_IMAGES_FOLDER)

# Initialize EasyOCR reader
if TELEGRAM_ENABLED or TEST_MODE or True:  # Always initialize if OCR is needed
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    print("✅ EasyOCR initialized successfully")
# ===================================

# Global variables
last_report_time = time.time()
report_counter = 0
skip_count = 0
detection_count = 0

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

def send_periodic_report(current_time, detection_count, skip_count, uptime_seconds):
    """Sends a summary report to Telegram every minute"""
    global last_report_time, report_counter
    
    current_time_float = time.time()
    if current_time_float - last_report_time >= REPORT_INTERVAL:
        last_report_time = current_time_float
        report_counter += 1
        
        skip_rate = (skip_count / detection_count * 100) if detection_count > 0 else 0
        
        uptime_hours = uptime_seconds / 3600
        uptime_minutes = (uptime_seconds % 3600) / 60
        
        mode_text = "🔬 TEST MODE (No clicks)" if TEST_MODE else "🎯 NORMAL MODE"
        
        message = (
            f"📊 *FISHBOWL SCRIPT REPORT #{report_counter}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{mode_text}\n"
            f"🕐 *Time:* {current_time}\n"
            f"⏱️ *Uptime:* {uptime_hours:.1f}h ({uptime_minutes:.0f}m)\n"
            f"🔄 *Total detections:* `{detection_count:,}`\n"
            f"⏭️ *Skipped:* `{skip_count:,}`\n"
            f"📈 *Skip rate:* `{skip_rate:.1f}%`\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"🤖 *Status:* {'🟢 RUNNING' if skip_rate < 90 else '🟡 ACTIVE'}"
        )
        
        send_telegram_message(message)
        print(f"📤 [REPORT] Summary #{report_counter} sent to Telegram")

def visualize_search_regions(button_location, pick_region_coords, screenshot, pick_text=None, should_skip=False, skip_reason=None):
    """Draws rectangles on the screenshot to visualize search regions"""
    if not VISUALIZE_DEBUG:
        return
    
    img_copy = screenshot.copy()
    draw = ImageDraw.Draw(img_copy)
    
    # Draw button region (green rectangle)
    button_left = button_location.left
    button_top = button_location.top
    button_right = button_location.left + button_location.width
    button_bottom = button_location.top + button_location.height
    
    draw.rectangle([button_left, button_top, button_right, button_bottom], 
                   outline="green", width=3)
    
    # Draw pick column region (blue rectangle)
    pick_left, pick_top, pick_right, pick_bottom = pick_region_coords
    draw.rectangle([pick_left, pick_top, pick_right, pick_bottom], 
                   outline="blue", width=3)
    
    # Add text labels
    draw.text((button_left, button_top - 20), "Finish Button", fill="green")
    draw.text((pick_left, pick_top - 20), "Pick Column OCR Region", fill="blue")
    
    # Add text detection result
    if pick_text:
        status_color = "red" if should_skip else "green"
        status_text = f"Detected: '{pick_text}' → {'SKIP' if should_skip else 'PROCESS'}"
        draw.text((pick_left, pick_bottom + 5), status_text, fill=status_color)
        
        if skip_reason:
            draw.text((pick_left, pick_bottom + 25), f"Reason: {skip_reason}", fill="yellow")
    
    # Add test mode info
    if TEST_MODE:
        draw.text((10, 50), "🔬 TEST MODE - No clicks will be performed", fill="orange")
    
    # Add coordinates info
    coords_text = f"Button: ({button_left}, {button_top}) | Pick Region: X:{pick_left}-{pick_right}, Y:{pick_top}-{pick_bottom}"
    draw.text((10, 10), coords_text, fill="yellow")
    
    # Add regex info
    if not USE_SIMPLE_TEXT_MATCH:
        draw.text((10, 30), f"Using regex patterns: {len(SKIP_PICK_PATTERNS)} patterns", fill="cyan")
        y_offset = 70
        for i, pattern in enumerate(SKIP_PICK_PATTERNS):
            draw.text((10, y_offset + i * 15), f"  • {pattern}", fill="cyan")
    
    # Save the image
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"debug_{timestamp}_{'SKIP' if should_skip else 'PROCESS'}.png"
    filepath = os.path.join(DEBUG_IMAGES_FOLDER, filename)
    img_copy.save(filepath)
    print(f"📸 Debug image saved: {filepath}")

def is_green_color(rgb, threshold=GREEN_THRESHOLD):
    r, g, b = rgb
    return g > r + threshold and g > b + threshold

def is_red_color(rgb, threshold=RED_THRESHOLD):
    r, g, b = rgb
    return r > g + threshold and r > b + threshold

def get_pick_column_text(button_center_x, button_center_y, button_location, screenshot):
    """Extracts text from the Pick column using EasyOCR with image enhancement"""
    # Calculate region for Pick column
    pick_x = button_center_x + PICK_COLUMN_X_OFFSET
    
    # EXACTLY button height - NO vertical padding
    pick_y_start = button_location.top
    pick_y_end = button_location.top + button_location.height
    
    pick_x = min(screenshot.width - PICK_COLUMN_WIDTH, pick_x)
    pick_y_start = max(0, pick_y_start)
    pick_y_end = min(screenshot.height, pick_y_end)
    
    region_coords = (pick_x, pick_y_start, pick_x + PICK_COLUMN_WIDTH, pick_y_end)
    
    button_height = button_location.height
    region_height = pick_y_end - pick_y_start
    print(f"   Pick region: {PICK_COLUMN_WIDTH}x{region_height}px (EXACT match button height: {button_height}px)")
    
    try:
        # Crop the region
        pick_region = screenshot.crop(region_coords)
        
        # Save raw OCR region for debugging
        if SAVE_OCR_REGIONS and VISUALIZE_DEBUG:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            pick_region.save(os.path.join(DEBUG_IMAGES_FOLDER, f"ocr_raw_{timestamp}.png"))
        
        # Enhance image for better OCR
        # 1. Scale up the image
        new_size = (pick_region.width * OCR_IMAGE_SCALE, pick_region.height * OCR_IMAGE_SCALE)
        pick_region_big = pick_region.resize(new_size, Image.Resampling.LANCZOS)
        
        # 2. Convert to grayscale
        pick_region_gray = pick_region_big.convert('L')
        
        # 3. Enhance contrast
        enhancer = ImageEnhance.Contrast(pick_region_gray)
        pick_region_contrast = enhancer.enhance(OCR_CONTRAST_ENHANCE)
        
        # 4. Apply sharpening
        if OCR_USE_SHARPEN:
            pick_region_final = pick_region_contrast.filter(ImageFilter.SHARPEN)
        else:
            pick_region_final = pick_region_contrast
        
        # Save processed OCR region for debugging
        if SAVE_OCR_REGIONS and VISUALIZE_DEBUG:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            pick_region_final.save(os.path.join(DEBUG_IMAGES_FOLDER, f"ocr_processed_{timestamp}.png"))
        
        # Convert to numpy array for EasyOCR
        img_np = np.array(pick_region_final)
        
        # Perform OCR using EasyOCR
        results = reader.readtext(img_np, detail=0, paragraph=False)
        
        if results and len(results) > 0:
            text = results[0].strip().upper()
            print(f"📝 Pick column text detected: '{text}'")
            return text, region_coords
        else:
            print(f"⚠️ No text detected in Pick column region")
            return None, region_coords
        
    except Exception as e:
        print(f"⚠️ OCR error: {e}")
        return None, region_coords

def should_skip_by_pick_text(pick_text):
    """Determines if button should be skipped based on Pick column text"""
    if not pick_text:
        return False, "no text detected"
    
    if USE_SIMPLE_TEXT_MATCH:
        for skip_text in SKIP_PICK_TEXTS:
            if pick_text == skip_text:
                return True, f"exact match: '{skip_text}'"
            if skip_text.upper() in pick_text:
                return True, f"contains: '{skip_text}'"
    else:
        for pattern in SKIP_PICK_PATTERNS:
            try:
                if re.search(pattern, pick_text, re.IGNORECASE):
                    return True, f"regex match: '{pattern}' → '{pick_text}'"
            except re.error as e:
                print(f"⚠️ Invalid regex pattern '{pattern}': {e}")
                continue
    
    return False, None

def find_green_finish_button(template_path, confidence=CONFIDENCE):
    """Finds the Finish button by checking the color at its center"""
    screenshot = None
    all_locations = None
    
    try:
        all_locations = list(pyautogui.locateAllOnScreen(template_path, confidence=confidence))
        
        if not all_locations:
            return None, None, None, None
        
        screenshot = pyautogui.screenshot()
        
        for location in all_locations:
            center_x = location.left + location.width // 2
            center_y = location.top + location.height // 2
            pixel_color = screenshot.getpixel((center_x, center_y))
            
            if is_green_color(pixel_color):
                print(f"\n{'='*60}")
                print(f"✅ Found GREEN button at position ({center_x}, {center_y})")
                print(f"   Button bounds: Left={location.left}, Top={location.top}, Width={location.width}, Height={location.height}")
                
                pick_text, region_coords = get_pick_column_text(center_x, center_y, location, screenshot)
                should_skip, skip_reason = should_skip_by_pick_text(pick_text)
                
                visualize_search_regions(location, region_coords, screenshot, pick_text, should_skip, skip_reason)
                
                if should_skip:
                    global skip_count
                    skip_count += 1
                    print(f"⏭️ WOULD SKIP button due to Pick column: {skip_reason}")
                    print(f"   Total skipped: {skip_count}")
                else:
                    print(f"🎯 WOULD PROCESS button (no skip conditions matched)")
                
                print(f"{'='*60}\n")
                return location, pick_text, should_skip, skip_reason
            
            if is_red_color(pixel_color):
                print(f"🔴 Found RED button, skipping. Color: {pixel_color}")
                continue
        
        return None, None, None, None
        
    except ImageNotFoundException:
        return None, None, None, None
    except Exception as e:
        print(f"⚠️ Unexpected error while searching: {e}")
        return None, None, None, None
    finally:
        if screenshot:
            del screenshot
        if all_locations:
            del all_locations

def find_and_click_second_image(image_path, confidence=SECOND_IMAGE_CONFIDENCE):
    """Finds the second image on screen and left-clicks it"""
    location = None
    
    try:
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
    time.sleep(0.3)

def cleanup_old_debug_images():
    """Removes old debug images to save disk space"""
    if not VISUALIZE_DEBUG:
        return
    
    try:
        files = [f for f in os.listdir(DEBUG_IMAGES_FOLDER) if f.endswith('.png')]
        files.sort()
        
        if len(files) > MAX_DEBUG_IMAGES:
            to_delete = files[:-MAX_DEBUG_IMAGES]
            for f in to_delete:
                os.remove(os.path.join(DEBUG_IMAGES_FOLDER, f))
            print(f"🧹 Cleaned up {len(to_delete)} old debug images")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

def optimize_memory():
    """Runs garbage collection and memory optimization"""
    gc.collect()
    cleanup_old_debug_images()

# Main program
print("=== Fishbowl Auto-Finish Script (EASYOCR) ===")
print(f"✅ EasyOCR initialized")
print(f"Check interval: {CHECK_INTERVAL} seconds")
print(f"Confidence level: {CONFIDENCE}")
print(f"Telegram enabled: {'✅ YES' if TELEGRAM_ENABLED else '❌ NO'}")
print(f"\n🔬 TEST MODE: {'✅ ENABLED (No clicks)' if TEST_MODE else '❌ DISABLED'}")
print(f"\n📸 VISUALIZATION:")
print(f"   Debug images: {'✅ ENABLED' if VISUALIZE_DEBUG else '❌ DISABLED'}")
print(f"   Save folder: {DEBUG_IMAGES_FOLDER}")
print(f"   Max images: {MAX_DEBUG_IMAGES}")
print(f"\n🔍 OCR REGION SETTINGS:")
print(f"   X offset from button: {PICK_COLUMN_X_OFFSET}px")
print(f"   Region width: {PICK_COLUMN_WIDTH}px")
print(f"   Vertical padding: ±{PICK_COLUMN_VERTICAL_PADDING}px")
print(f"   Image scale: {OCR_IMAGE_SCALE}x")
print(f"   Contrast enhance: {OCR_CONTRAST_ENHANCE}x")
print(f"\n🚫 SKIP PATTERNS:")
for pattern in SKIP_PICK_PATTERNS:
    if pattern == r'^W.*$':
        print(f"   • {pattern} - Starts with 'W'")
    elif pattern == r'^T.*$':
        print(f"   • {pattern} - Starts with 'T'")
    elif pattern == r'POS':
        print(f"   • {pattern} - Contains 'POS'")
    else:
        print(f"   • {pattern}")
print(f"\n⚠️ Script will run FOREVER - press Ctrl+C to stop")
print("Switch to Fishbowl Client window")
print()

# Send startup message to Telegram
if TELEGRAM_ENABLED:
    send_telegram_message(
        "🚀 *FISHBOWL SCRIPT STARTED (EASYOCR)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"🔬 Mode: {'TEST' if TEST_MODE else 'NORMAL'}\n"
        f"🚫 Skip patterns: Starts with W, Starts with T, Contains POS\n"
        f"📸 Debug images: {DEBUG_IMAGES_FOLDER}"
    )

time.sleep(3)

# Initialize counters
iteration = 0
detection_count = 0
skip_count = 0
start_time = time.time()

try:
    while True:
        iteration += 1
        current_time_str = datetime.now().strftime("%H:%M:%S")
        
        finish_location, pick_text, should_skip, skip_reason = find_green_finish_button(FINISH_BUTTON_IMAGE, confidence=CONFIDENCE)
        
        if finish_location:
            detection_count += 1
            if should_skip:
                skip_count += 1
                print(f"[{current_time_str}] ⏭️ Detection #{detection_count} - SKIPPED (text: '{pick_text}')")
            else:
                print(f"[{current_time_str}] 🎯 Detection #{detection_count} - WOULD PROCESS (text: '{pick_text}')")
            
            if TEST_MODE:
                print(f"[{current_time_str}] 🔬 Waiting {TEST_MODE_DELAY}s...")
                time.sleep(TEST_MODE_DELAY)
            else:
                if not should_skip and finish_location:
                    finish_center = pyautogui.center(finish_location)
                    pyautogui.doubleClick(finish_center)
                    print("✅ Double click on Finish performed!")
                    time.sleep(0.3)
                    pyautogui.rightClick(finish_center)
                    print("✅ Right click performed!")
                    time.sleep(RIGHT_CLICK_DELAY)
                    find_and_click_second_image(SECOND_IMAGE, confidence=SECOND_IMAGE_CONFIDENCE)
                elif should_skip:
                    print("⏭️ Button skipped, pressing Ctrl+1")
                    press_ctrl_1()
        else:
            if iteration % 10 == 0:
                print(f"[{current_time_str}] 🔍 No green button found...")
        
        if iteration % STATUS_PRINT_INTERVAL == 0:
            uptime = time.time() - start_time
            skip_rate = (skip_count / detection_count * 100) if detection_count > 0 else 0
            print(f"[{current_time_str}] 📊 Stats - Detections: {detection_count} | Skipped: {skip_count} ({skip_rate:.1f}%) | Uptime: {uptime/60:.1f} min")
        
        if TELEGRAM_ENABLED and detection_count > 0:
            uptime = time.time() - start_time
            send_periodic_report(current_time_str, detection_count, skip_count, uptime)
        
        if iteration % GC_INTERVAL == 0:
            optimize_memory()
        
        if not TEST_MODE:
            time.sleep(CHECK_INTERVAL)
        
except KeyboardInterrupt:
    uptime = time.time() - start_time
    uptime_hours = uptime / 3600
    uptime_days = uptime / 86400
    
    print(f"\n\n{'='*50}")
    print(f"⏹️ SCRIPT STOPPED")
    print(f"{'='*50}")
    print(f"📊 FINAL STATISTICS:")
    print(f"   - Total detections: {detection_count:,}")
    print(f"   - Skipped: {skip_count:,}")
    if detection_count > 0:
        print(f"   - Skip rate: {skip_count/detection_count*100:.1f}%")
    print(f"   - Uptime: {uptime_days:.1f} days ({uptime_hours:.1f} hours)")
    print(f"   - Debug images saved in: {DEBUG_IMAGES_FOLDER}")
    print(f"{'='*50}")
    
    if TELEGRAM_ENABLED:
        send_telegram_message(f"🛑 *SCRIPT STOPPED*\n━━━━━━━━━━━━━━━━━━━━━\n📊 Detections: {detection_count} | Skipped: {skip_count}\n📈 Skip rate: {skip_count/detection_count*100:.1f}%\n⏱️ Uptime: {uptime_days:.1f} days")