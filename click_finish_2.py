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
reader = easyocr.Reader(['en'], gpu=False, verbose=False)
print("✅ EasyOCR initialized successfully")
# ===================================

# ========== TELEGRAM SETTINGS ==========
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"  # Replace with your bot token
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"  # Replace with your chat ID
TELEGRAM_ENABLED = False  # Set to True to enable Telegram notifications
# =======================================

# ========== SCRIPT SETTINGS ==========
CHECK_INTERVAL = 0.5  # Check interval in seconds
CONFIDENCE = 0.7    # Confidence level (DO NOT LOWER)
RIGHT_CLICK_DELAY = 0.3  # Delay after right click
SECOND_IMAGE_CONFIDENCE = 0.7  # Confidence for finding the second image
GC_INTERVAL = 1000  # Run garbage collection every N iterations
REPORT_INTERVAL = 60  # Send Telegram report every N seconds (60 = 1 minute)
STATUS_PRINT_INTERVAL = 50  # Print status every N iterations
# =======================================

# ========== TEST MODE SETTINGS ==========
TEST_MODE = False  # Set to True to ONLY check and visualize, NOT click anything
TEST_MODE_DELAY = 3  # Seconds to wait after each detection in test mode
# =========================================

# ========== SKIP CONDITIONS ==========
SKIP_PICK_PATTERNS = [
    r'^W.*$',    # Starts with W
    r'^T.*$',    # Starts with T
    r'POS',      # Contains POS
]
USE_SIMPLE_TEXT_MATCH = False
SKIP_PICK_TEXTS = [
    'COMMIT', 'FINISH','START'
]
# ===========================================

# ========== OCR REGION SETTINGS ==========
PICK_COLUMN_X_OFFSET = 15   # Distance from button center to Pick column
PICK_COLUMN_WIDTH = 70      # Width of the region to check
# NO vertical padding - exactly button height
# ===========================================

# ========== IMAGE ENHANCEMENT SETTINGS ==========
OCR_IMAGE_SCALE = 2         # Scale factor for image before OCR
OCR_CONTRAST_ENHANCE = 1.5  # Contrast enhancement factor
OCR_USE_SHARPEN = False     # Apply sharpening filter
SAVE_OCR_REGIONS = True     # Save cropped OCR regions for debugging
# =================================================

# ========== COLOR DETECTION SETTINGS ==========
GREEN_THRESHOLD = 50
RED_THRESHOLD = 50
# ===============================================

# ========== VISUALIZATION SETTINGS ==========
VISUALIZE_DEBUG = False
DEBUG_IMAGES_FOLDER = "debug_images"
MAX_DEBUG_IMAGES = 100
# ===========================================

# ========== FILE SETTINGS ==========
FINISH_BUTTON_IMAGE = 'finish_button.png'
SECOND_IMAGE = 'finish_button_inner.png'
# ===================================

# Create debug folder
if VISUALIZE_DEBUG and not os.path.exists(DEBUG_IMAGES_FOLDER):
    os.makedirs(DEBUG_IMAGES_FOLDER)

# Global variables
last_report_time = time.time()
report_counter = 0
skip_count = 0
detection_count = 0
is_processing = False  # NEW: Flag to prevent concurrent processing

def send_telegram_message(message):
    if not TELEGRAM_ENABLED:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")

def send_periodic_report(current_time, detection_count, skip_count, uptime_seconds):
    global last_report_time, report_counter
    if time.time() - last_report_time >= REPORT_INTERVAL:
        last_report_time = time.time()
        report_counter += 1
        skip_rate = (skip_count / detection_count * 100) if detection_count > 0 else 0
        uptime_hours = uptime_seconds / 3600
        mode_text = "🔬 TEST MODE" if TEST_MODE else "🎯 NORMAL MODE"
        message = (
            f"📊 *REPORT #{report_counter}*\n"
            f"{mode_text}\n"
            f"🕐 {current_time} | ⏱️ {uptime_hours:.1f}h\n"
            f"🔄 Detections: {detection_count} | Skipped: {skip_count}\n"
            f"📈 Skip rate: {skip_rate:.1f}%"
        )
        send_telegram_message(message)

def visualize_search_regions(button_location, pick_region_coords, screenshot, pick_text=None, should_skip=False, skip_reason=None):
    if not VISUALIZE_DEBUG:
        return
    
    img_copy = screenshot.copy()
    draw = ImageDraw.Draw(img_copy)
    
    button_left, button_top = button_location.left, button_location.top
    button_right = button_left + button_location.width
    button_bottom = button_top + button_location.height
    
    draw.rectangle([button_left, button_top, button_right, button_bottom], outline="green", width=3)
    
    pick_left, pick_top, pick_right, pick_bottom = pick_region_coords
    draw.rectangle([pick_left, pick_top, pick_right, pick_bottom], outline="blue", width=3)
    
    draw.text((button_left, button_top - 20), "Finish Button", fill="green")
    draw.text((pick_left, pick_top - 20), "Pick Column Region", fill="blue")
    
    if pick_text:
        status_color = "red" if should_skip else "green"
        status_text = f"Detected: '{pick_text}' → {'SKIP' if should_skip else 'PROCESS'}"
        draw.text((pick_left, pick_bottom + 5), status_text, fill=status_color)
        if skip_reason:
            draw.text((pick_left, pick_bottom + 25), f"Reason: {skip_reason}", fill="yellow")
    
    if TEST_MODE:
        draw.text((10, 50), "🔬 TEST MODE - No clicks", fill="orange")
    
    coords_text = f"Button: ({button_left}, {button_top}) | Region: {pick_left}-{pick_right}, {pick_top}-{pick_bottom}"
    draw.text((10, 10), coords_text, fill="yellow")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    filename = f"debug_{timestamp}_{'SKIP' if should_skip else 'PROCESS'}.png"
    img_copy.save(os.path.join(DEBUG_IMAGES_FOLDER, filename))
    print(f"📸 Debug image saved")

def is_green_color(rgb, threshold=GREEN_THRESHOLD):
    r, g, b = rgb
    return g > r + threshold and g > b + threshold

def is_red_color(rgb, threshold=RED_THRESHOLD):
    r, g, b = rgb
    return r > g + threshold and r > b + threshold

def get_pick_column_text(button_center_x, button_center_y, button_location, screenshot):
    """Extracts text from Pick column - EXACT button height, NO padding"""
    # Calculate region - EXACTLY button height
    pick_x = button_center_x + PICK_COLUMN_X_OFFSET
    pick_y_start = button_location.top
    pick_y_end = button_location.top + button_location.height
    
    pick_x = min(screenshot.width - PICK_COLUMN_WIDTH, pick_x)
    pick_y_start = max(0, pick_y_start)
    pick_y_end = min(screenshot.height, pick_y_end)
    
    region_coords = (pick_x, pick_y_start, pick_x + PICK_COLUMN_WIDTH, pick_y_end)
    
    print(f"   Pick region: {PICK_COLUMN_WIDTH}x{pick_y_end - pick_y_start}px (EXACT button height: {button_location.height}px)")
    
    try:
        pick_region = screenshot.crop(region_coords)
        
        if SAVE_OCR_REGIONS and VISUALIZE_DEBUG:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            pick_region.save(os.path.join(DEBUG_IMAGES_FOLDER, f"ocr_raw_{timestamp}.png"))
        
        # Enhance image
        new_size = (pick_region.width * OCR_IMAGE_SCALE, pick_region.height * OCR_IMAGE_SCALE)
        pick_region_big = pick_region.resize(new_size, Image.Resampling.LANCZOS)
        pick_region_gray = pick_region_big.convert('L')
        
        enhancer = ImageEnhance.Contrast(pick_region_gray)
        pick_region_contrast = enhancer.enhance(OCR_CONTRAST_ENHANCE)
        
        if OCR_USE_SHARPEN:
            pick_region_final = pick_region_contrast.filter(ImageFilter.SHARPEN)
        else:
            pick_region_final = pick_region_contrast
        
        if SAVE_OCR_REGIONS and VISUALIZE_DEBUG:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            pick_region_final.save(os.path.join(DEBUG_IMAGES_FOLDER, f"ocr_processed_{timestamp}.png"))
        
        img_np = np.array(pick_region_final)
        results = reader.readtext(img_np, detail=0, paragraph=False)
        
        if results and len(results) > 0:
            text = results[0].strip().upper()
            print(f"📝 Pick column text detected: '{text}'")
            return text, region_coords
        
        print(f"⚠️ No text detected")
        return None, region_coords
        
    except Exception as e:
        print(f"⚠️ OCR error: {e}")
        return None, region_coords

def should_skip_by_pick_text(pick_text):
    if not pick_text:
        return False, "no text detected"
    
    if USE_SIMPLE_TEXT_MATCH:
        for skip_text in SKIP_PICK_TEXTS:
            if pick_text == skip_text:
                return True, f"exact match: '{skip_text}'"
    else:
        for pattern in SKIP_PICK_PATTERNS:
            try:
                if re.search(pattern, pick_text, re.IGNORECASE):
                    return True, f"regex match: '{pattern}'"
            except re.error as e:
                print(f"⚠️ Invalid regex: {e}")
                continue
    
    return False, None

def process_single_button():
    """Process a single button from start to finish"""
    global is_processing, skip_count, detection_count
    
    is_processing = True
    
    try:
        finish_location, pick_text, should_skip, skip_reason = find_green_finish_button(FINISH_BUTTON_IMAGE, confidence=CONFIDENCE)
        
        if finish_location:
            detection_count += 1
            
            if should_skip:
                skip_count += 1
                print(f"⏭️ SKIPPED (text: '{pick_text}')")
                
                if not TEST_MODE:
                    press_ctrl_1()
            else:
                print(f"🎯 PROCESSING (text: '{pick_text}')")
                
                if not TEST_MODE:
                    finish_center = pyautogui.center(finish_location)
                    pyautogui.click(finish_center)
                    print("✅ Double click performed")
                    time.sleep(0.1)
                    
                    pyautogui.rightClick(finish_center)
                    print("✅ Right click performed")
                    time.sleep(RIGHT_CLICK_DELAY)
                    
                    # Wait for second image to appear and click it
                    find_and_click_second_image(SECOND_IMAGE)
            
            if TEST_MODE:
                time.sleep(TEST_MODE_DELAY)
        else:
            print(f"🔍 No green button found...")
        
    except Exception as e:
        print(f"⚠️ Error in processing: {e}")
    finally:
        is_processing = False

def find_green_finish_button(template_path, confidence=CONFIDENCE):
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
                print(f"✅ Found GREEN button at ({center_x}, {center_y})")
                print(f"   Button: Left={location.left}, Top={location.top}, Width={location.width}, Height={location.height}")
                
                pick_text, region_coords = get_pick_column_text(center_x, center_y, location, screenshot)
                should_skip, skip_reason = should_skip_by_pick_text(pick_text)
                
                visualize_search_regions(location, region_coords, screenshot, pick_text, should_skip, skip_reason)
                
                if should_skip:
                    print(f"⏭️ WILL SKIP: {skip_reason}")
                else:
                    print(f"🎯 WILL PROCESS")
                
                print(f"{'='*60}\n")
                return location, pick_text, should_skip, skip_reason
            
            if is_red_color(pixel_color):
                print(f"🔴 Found RED button, skipping")
                continue
        
        return None, None, None, None
        
    except Exception as e:
        print(f"⚠️ Error: {e}")
        return None, None, None, None
    finally:
        if screenshot:
            del screenshot
        if all_locations:
            del all_locations

def find_and_click_second_image(image_path, confidence=SECOND_IMAGE_CONFIDENCE):
    """Finds the second image on screen and left-clicks it"""
    max_attempts = 5  # Try 5 times
    for attempt in range(max_attempts):
        try:
            location = pyautogui.locateOnScreen(image_path, confidence=confidence)
            if location:
                center = pyautogui.center(location)
                pyautogui.click(center)
                print(f"✅ Second image clicked (attempt {attempt + 1})")
                time.sleep(0.5)  # Wait after click
                return True
            else:
                print(f"⏳ Waiting for second image... (attempt {attempt + 1}/{max_attempts})")
                time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Error finding second image: {e}")
            time.sleep(0.5)
    
    print(f"⚠️ Second image not found after {max_attempts} attempts")
    return False

def press_ctrl_1():
    pyautogui.hotkey('ctrl', '1')
    print("✅ Ctrl+1 pressed")
    time.sleep(0.3)

def cleanup_old_debug_images():
    if not VISUALIZE_DEBUG:
        return
    try:
        files = [f for f in os.listdir(DEBUG_IMAGES_FOLDER) if f.endswith('.png')]
        files.sort()
        if len(files) > MAX_DEBUG_IMAGES:
            for f in files[:-MAX_DEBUG_IMAGES]:
                os.remove(os.path.join(DEBUG_IMAGES_FOLDER, f))
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

def optimize_memory():
    gc.collect()
    cleanup_old_debug_images()

# Main program
print("=== Fishbowl Script (EASYOCR) ===")
print(f"Check interval: {CHECK_INTERVAL}s | Confidence: {CONFIDENCE}")
print(f"TEST MODE: {'ON (No clicks)' if TEST_MODE else 'OFF'}")
print(f"OCR Region: {PICK_COLUMN_WIDTH}px width, EXACT button height")
print(f"Skip patterns: W*, T*, POS")
print(f"Debug images: {DEBUG_IMAGES_FOLDER}")
print("Press Ctrl+C to stop\n")
time.sleep(2)

iteration = 0
detection_count = 0
skip_count = 0
start_time = time.time()
is_processing = False  # Flag to prevent concurrent processing

try:
    while True:
        iteration += 1
        current_time_str = datetime.now().strftime("%H:%M:%S")
        
        # Only start new processing if not already processing
        if not is_processing:
            process_single_button()
        else:
            # Wait if still processing previous button
            print(f"[{current_time_str}] ⏳ Waiting for previous operation to complete...")
            time.sleep(0.5)
        
        if iteration % STATUS_PRINT_INTERVAL == 0:
            uptime = time.time() - start_time
            skip_rate = (skip_count / detection_count * 100) if detection_count > 0 else 0
            print(f"[{current_time_str}] 📊 Detections: {detection_count} | Skipped: {skip_count} ({skip_rate:.1f}%) | Uptime: {uptime/60:.1f}min")
        
        if TELEGRAM_ENABLED and detection_count > 0:
            send_periodic_report(current_time_str, detection_count, skip_count, time.time() - start_time)
        
        if iteration % GC_INTERVAL == 0:
            optimize_memory()
        
        # Wait before next check (if not in TEST_MODE with processing)
        if not is_processing and not TEST_MODE:
            time.sleep(CHECK_INTERVAL)
        elif TEST_MODE and not is_processing:
            time.sleep(CHECK_INTERVAL)
        
except KeyboardInterrupt:
    uptime = time.time() - start_time
    print(f"\n\n{'='*50}")
    print(f"⏹️ SCRIPT STOPPED")
    print(f"📊 Detections: {detection_count} | Skipped: {skip_count}")
    if detection_count > 0:
        print(f"📈 Skip rate: {skip_count/detection_count*100:.1f}%")
    print(f"⏱️ Uptime: {uptime/3600:.1f} hours")
    print(f"{'='*50}")