package com.fishbowl.schedule;

import com.fishbowl.fbclient.FBClient;
import com.fishbowl.fbclient.ServiceException;

import java.util.Date;
import java.util.List;
import java.text.SimpleDateFormat;

/**
 * AutoFinishPickingOrders - Scheduler класс для Fishbowl
 * Автоматически завершает все Picking Orders, готовые к переводу в статус Finished
 * 
 * Что такое Picking Order в Fishbowl:
 * - Это процесс сбора товаров со склада для выполнения заказа
 * - Picking Orders создаются для Sales Orders, Work Orders, Transfer Orders
 * - Когда Pick завершен (Finished), товары перемещаются в Shipping или Production зону
 * 
 * Источник: Fishbowl Help - Picking module [citation:8]
 */
public class AutoFinishPickingOrders implements SchedulePlugin {
    
    private FBClient client;
    
    @Override
    public void execute() throws Exception {
        log("=== AutoFinishPickingOrders STARTED at " + getCurrentTime() + " ===");
        
        try {
            // 1. Подключение к Fishbowl
            connect();
            
            // 2. Получение всех незавершенных Picking Orders
            List<Pick> picks = getAllUnfinishedPicks();
            
            if (picks == null || picks.isEmpty()) {
                log("No unfinished picks found.");
                log("=== AutoFinishPickingOrders FINISHED (nothing to do) ===");
                return;
            }
            
            log("Found " + picks.size() + " picks to check.");
            
            int finishedCount = 0;
            int skippedCount = 0;
            int errorCount = 0;
            
            // 3. Обработка каждого Pick
            for (Pick pick : picks) {
                String pickNum = pick.getPickNumber();
                String status = pick.getStatus();
                
                log("Processing pick #" + pickNum + " (status: " + status + ")");
                
                if (canBeFinished(pick)) {
                    boolean success = finishPick(pick);
                    if (success) {
                        finishedCount++;
                        log("✓ FINISHED: Pick #" + pickNum);
                    } else {
                        errorCount++;
                        log("✗ ERROR: Failed to finish pick #" + pickNum);
                    }
                } else {
                    skippedCount++;
                    log("⊘ SKIPPED: Pick #" + pickNum + " - not all items are pickable");
                }
            }
            
            // 4. Итоговый отчет
            log("=== AutoFinishPickingOrders COMPLETED ===");
            log("Finished: " + finishedCount + " picks");
            log("Skipped: " + skippedCount + " picks");
            log("Errors: " + errorCount + " picks");
            
        } catch (Exception e) {
            log("CRITICAL ERROR: " + e.getMessage());
            e.printStackTrace();
            throw e;
        } finally {
            disconnect();
        }
    }
    
    /**
     * Подключение к Fishbowl
     */
    private void connect() throws ServiceException {
        // Адаптируйте под вашу версию Fishbowl
        String host = "localhost";
        int port = 3333;
        String username = "admin";
        String password = "admin";
        
        client = new FBClient(host, port);
        client.login(username, password);
        
        log("Connected to Fishbowl successfully.");
    }
    
    /**
     * Получение всех Picking Orders, которые еще не завершены
     * 
     * В Fishbowl Pick может иметь статусы:
     * - Entered: не начат, достаточно inventory
     * - Started: процесс начат
     * - Committed: инвентарь зарезервирован
     * - Finished: полностью завершен [citation:8]
     */
    private List<Pick> getAllUnfinishedPicks() throws ServiceException {
        // Запрашиваем все Pick со статусами, отличными от "Finished"
        // Статус Finished в Fishbowl имеет иконку галочки [citation:3]
        
        // Способ 1: Через прямой API запрос
        // return client.getPicksByStatuses(List.of("Entered", "Started", "Committed"));
        
        // Способ 2: Через ExecuteQuery
        String query = "SELECT * FROM pick WHERE status != 'Finished' AND dateFinished IS NULL";
        return client.executeQuery(query);
    }
    
    /**
     * Проверка, можно ли завершить Pick
     * 
     * Pick можно завершить, если ВСЕ товары в нем могут быть собраны (pickable)
     * В Fishbowl колонка Finish в поиске Pick показывает статус:
     * - Зеленый: все товары pickable [citation:3]
     * - Желтый: хотя бы один товар pickable
     * - Красный: нет pickable товаров
     * - Иконка Finished: Pick уже завершен [citation:3]
     */
    private boolean canBeFinished(Pick pick) {
        try {
            // Проверка 1: Статус не должен быть уже Finished
            if ("Finished".equals(pick.getStatus())) {
                return false;
            }
            
            // Проверка 2: Все товары в Pick должны быть pickable
            List<PickItem> items = pick.getItems();
            if (items == null || items.isEmpty()) {
                log("Warning: Pick #" + pick.getPickNumber() + " has no items");
                return false;
            }
            
            for (PickItem item : items) {
                // Проверяем, достаточно ли количества для пикинга
                // pickableQuantity - количество, которое можно собрать [citation:3]
                if (item.getPickableQuantity() <= 0) {
                    return false;
                }
                
                // Если есть шорт (недостаток) - нельзя завершить
                if (item.isShort()) {
                    return false;
                }
            }
            
            return true;
            
        } catch (Exception e) {
            log("Error checking pick #" + pick.getPickNumber() + ": " + e.getMessage());
            return false;
        }
    }
    
    /**
     * Завершение Picking Order
     * 
     * В Fishbowl при завершении Pick:
     * - Инвентарь перемещается в Shipping Location (для Sales Order)
     * - Или в Manufacture Location (для Work Order)
     * - Статус товаров становится Finished
     * - Inventory остается Committed до момента отгрузки или потребления [citation:8]
     */
    private boolean finishPick(Pick pick) {
        try {
            String pickNum = pick.getPickNumber();
            
            // Способ 1: Через стандартный метод завершения Pick
            // client.finishPick(pick.getId());
            
            // Способ 2: Через execute команду
            // client.execute("pickFinish", pick.getId());
            
            // Способ 3: Прямое обновление через API
            pick.setStatus("Finished");
            pick.setDateFinished(new Date());
            
            // Для каждого товара в Pick устанавливаем статус Finished
            for (PickItem item : pick.getItems()) {
                item.setStatus("Finished");
                item.setDateFinished(new Date());
            }
            
            boolean result = client.savePick(pick);
            
            if (result) {
                log("Successfully finished pick #" + pickNum);
            }
            
            return result;
            
        } catch (Exception e) {
            log("Exception finishing pick #" + pick.getPickNumber() + ": " + e.getMessage());
            return false;
        }
    }
    
    /**
     * Отключение от Fishbowl
     */
    private void disconnect() {
        try {
            if (client != null) {
                client.logout();
            }
            log("Disconnected from Fishbowl.");
        } catch (Exception e) {
            log("Error during disconnect: " + e.getMessage());
        }
    }
    
    private void log(String message) {
        String timestamp = getCurrentTime();
        System.out.println("[" + timestamp + "] [AutoFinishPickingOrders] " + message);
    }
    
    private String getCurrentTime() {
        SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
        return sdf.format(new Date());
    }
    
    @Override
    public void stop() {
        log("Plugin stopped.");
        disconnect();
    }
}

/**
 * Класс для Picking Order
 * Адаптируйте поля под вашу версию Fishbowl
 */
class Pick {
    private int id;
    private String pickNumber;
    private String status;          // Entered, Started, Committed, Finished
    private Date dateFinished;
    private List<PickItem> items;
    private String orderType;       // Sales, Work, Transfer
    private int sourceOrderId;      // ID исходного заказа
    
    // Getters and Setters
    public int getId() { return id; }
    public void setId(int id) { this.id = id; }
    
    public String getPickNumber() { return pickNumber; }
    public void setPickNumber(String num) { this.pickNumber = num; }
    
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    
    public Date getDateFinished() { return dateFinished; }
    public void setDateFinished(Date date) { this.dateFinished = date; }
    
    public List<PickItem> getItems() { return items; }
    public void setItems(List<PickItem> items) { this.items = items; }
    
    public String getOrderType() { return orderType; }
    public void setOrderType(String type) { this.orderType = type; }
    
    public int getSourceOrderId() { return sourceOrderId; }
    public void setSourceOrderId(int id) { this.sourceOrderId = id; }
}

/**
 * Класс для товара в Picking Order
 */
class PickItem {
    private int id;
    private String partNumber;
    private double quantity;           // Запрошенное количество
    private double pickedQuantity;     // Уже собрано
    private double pickableQuantity;   // Можно собрать [citation:3]
    private String status;             // Entered, Started, Committed, Finished
    private Date dateFinished;
    private boolean isShort;           // Недостаток на складе [citation:8]
    private String location;
    
    // Getters and Setters
    public int getId() { return id; }
    public void setId(int id) { this.id = id; }
    
    public String getPartNumber() { return partNumber; }
    public void setPartNumber(String pn) { this.partNumber = pn; }
    
    public double getQuantity() { return quantity; }
    public void setQuantity(double qty) { this.quantity = qty; }
    
    public double getPickedQuantity() { return pickedQuantity; }
    public void setPickedQuantity(double qty) { this.pickedQuantity = qty; }
    
    public double getPickableQuantity() { return pickableQuantity; }
    public void setPickableQuantity(double qty) { this.pickableQuantity = qty; }
    
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    
    public Date getDateFinished() { return dateFinished; }
    public void setDateFinished(Date date) { this.dateFinished = date; }
    
    public boolean isShort() { return isShort; }
    public void setShort(boolean sh) { this.isShort = sh; }
    
    public String getLocation() { return location; }
    public void setLocation(String loc) { this.location = loc; }
}

interface SchedulePlugin {
    void execute() throws Exception;
    void stop();
}