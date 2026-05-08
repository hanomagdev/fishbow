import pyautogui
import time
from PIL import Image
from datetime import datetime
from pyscreeze import ImageNotFoundException

# НАСТРОЙКИ
CHECK_INTERVAL = 1  # Интервал проверки в секундах
DOUBLE_CLICK = True   # Использовать двойной клик (True) или одиночный (False)
CONFIDENCE = 0.7      # Уровень уверенности (НЕ СНИЖАЕМ)

def is_green_color(rgb, threshold=50):
    r, g, b = rgb
    return g > r + threshold and g > b + threshold

def is_red_color(rgb, threshold=50):
    r, g, b = rgb
    return r > g + threshold and r > b + threshold

def find_green_finish_button(template_path, confidence=CONFIDENCE):
    """
    Ищет кнопку Finish, проверяя цвет в её центре
    """
    try:
        # Находим все вхождения кнопки на экране
        all_locations = list(pyautogui.locateAllOnScreen(template_path, confidence=confidence))
        
        if not all_locations:
            return None
        
        # Делаем скриншот для проверки цветов
        screenshot = pyautogui.screenshot()
        
        for location in all_locations:
            # Получаем центр найденной области
            center_x = location.left + location.width // 2
            center_y = location.top + location.height // 2
            
            # Получаем цвет в центре
            pixel_color = screenshot.getpixel((center_x, center_y))
            
            # Проверяем, зеленый ли это цвет
            if is_green_color(pixel_color):
                print(f"Найдена ЗЕЛЕНАЯ кнопка! Цвет в центре: {pixel_color}")
                return location
            
            # Если найдена красная - пропускаем
            if is_red_color(pixel_color):
                print(f"Найдена КРАСНАЯ кнопка, пропускаем. Цвет: {pixel_color}")
                continue
        
        return None
        
    except ImageNotFoundException:
        # Изображение не найдено с заданным confidence - это НЕ ОШИБКА, просто нет кнопки
        return None
    except Exception as e:
        print(f"⚠️ Неожиданная ошибка при поиске: {e}")
        return None

def process_button():
    finish_location = find_green_finish_button('finish_button.png', confidence=CONFIDENCE)
    
    if finish_location:
        finish_center = pyautogui.center(finish_location)
        
        if DOUBLE_CLICK:
            pyautogui.doubleClick(finish_center)
            print("✅ Двойной клик выполнен!")
        else:
            pyautogui.click(finish_center)
            print("✅ Одиночный клик выполнен!")
        
        time.sleep(0.5)
        pyautogui.hotkey('ctrl', 'f')
        print("✅ Комбинация Ctrl+F отправлена!")
        return True
    else:
        # Без лишнего шума (можно раскомментировать для отладки)
        # print("🔍 Зеленая кнопка Finish не найдена")
        return False

# Основная программа
print("=== Fishbowl Auto-Finish Script ===")
print(f"Интервал проверки: {CHECK_INTERVAL} секунд")
print(f"Двойной клик: {'Да' if DOUBLE_CLICK else 'Нет'}")
print(f"Уровень уверенности (confidence): {CONFIDENCE}")
print("Переключитесь на окно Fishbowl Client")
print("Нажмите Ctrl+C для остановки")
print()

time.sleep(3)

iteration = 0
success_count = 0

try:
    while True:
        iteration += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        
        if process_button():
            success_count += 1
            print(f"[{current_time}] ✅ Успех #{success_count} (всего проверок: {iteration})")
        
        # Каждые 50 проверок выводим статус (чтобы видеть, что скрипт жив)
        if iteration % 50 == 0:
            print(f"[{current_time}] 📊 Жив. Успехов: {success_count} из {iteration} проверок")
        
        time.sleep(CHECK_INTERVAL)
        
except KeyboardInterrupt:
    print(f"\n\n{'='*45}")
    print(f"⏹️ СКРИПТ ОСТАНОВЛЕН")
    print(f"{'='*45}")
    print(f"📊 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"   - Всего проверок: {iteration}")
    print(f"   - Успешных кликов: {success_count}")
    if iteration > 0:
        print(f"   - Процент успеха: {success_count/iteration*100:.1f}%")
    print(f"{'='*45}")