import pyautogui
import time
from PIL import Image
from datetime import datetime
from pyscreeze import ImageNotFoundException

# SETTINGS
CHECK_INTERVAL = 1  # Check interval in seconds
CONFIDENCE = 0.7    # Confidence level (DO NOT LOWER)
RIGHT_CLICK_DELAY = 0.5  # Delay after right click
SECOND_IMAGE_CONFIDENCE = 0.7  # Confidence for finding the second image

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

def find_and_click_second_image(image_path, confidence=SECOND_IMAGE_CONFIDENCE):
    """
    Finds the second image on screen and left-clicks it
    """
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
        
        if second_image_found:
            return True
        else:
            print("⚠️ Second image not found after right click")
            return False
    else:
        return False

# Main program
print("=== Fishbowl Auto-Finish Script (UPDATED) ===")
print(f"Check interval: {CHECK_INTERVAL} seconds")
print(f"Confidence level: {CONFIDENCE}")
print(f"Delay after right click: {RIGHT_CLICK_DELAY} sec")
print("Switch to Fishbowl Client window")
print("Press Ctrl+C to stop")
print()

time.sleep(3)

iteration = 0
success_count = 0
failure_count = 0

try:
    while True:
        iteration += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        
        if process_button():
            success_count += 1
            print(f"[{current_time}] ✅ Full success #{success_count} (total checks: {iteration})")
        else:
            failure_count += 1
            print(f"[{current_time}] ❌ Failed attempt #{failure_count} (total checks: {iteration})")
            # Press Ctrl+1 after failed attempt
            press_ctrl_1()
        
        # Every 50 checks show status
        if iteration % 50 == 0:
            print(f"[{current_time}] 📊 Alive. Successes: {success_count} out of {iteration} checks")
        
        time.sleep(CHECK_INTERVAL)
        
except KeyboardInterrupt:
    print(f"\n\n{'='*45}")
    print(f"⏹️ SCRIPT STOPPED")
    print(f"{'='*45}")
    print(f"📊 FINAL STATISTICS:")
    print(f"   - Total checks: {iteration}")
    print(f"   - Successful operations: {success_count}")
    print(f"   - Failed operations: {failure_count}")
    if iteration > 0:
        print(f"   - Success rate: {success_count/iteration*100:.1f}%")
    print(f"{'='*45}")