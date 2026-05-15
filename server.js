import express from 'express';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import fetch from 'node-fetch';
import 'dotenv/config';
import fs from 'fs';

// ===== КОНФИГУРАЦИЯ =====
const app = express();
const PORT = 3000;

// API ключи ShipStation (хранятся в .env файле)
const SHIPSTATION_API_KEY = process.env.SHIPSTATION_API_KEY;
const SHIPSTATION_API_SECRET = process.env.SHIPSTATION_API_SECRET;

// Basic Auth для ShipStation
const auth = Buffer.from(`${SHIPSTATION_API_KEY}:${SHIPSTATION_API_SECRET}`).toString('base64');

// ===== MIDDLEWARE =====
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Логгер всех запросов
app.use((req, res, next) => {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
    next();
});

// ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

// Функция для запроса данных из ShipStation по resource_url
async function fetchShipmentData(resourceUrl) {
    try {
        console.log(`🔗 Запрашиваю данные по: ${resourceUrl}`);
        console.log(auth)
        
        const response = await fetch(resourceUrl, {
            method: 'GET',
            headers: {
                'Authorization': `Basic ${auth}`,
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log(`✅ Получены данные об отправлении`);
        return data;
        
    } catch (error) {
        console.error(`❌ Ошибка при запросе данных:`, error);
        throw error;
    }
}

// Функция обновления статуса в Fishbowl (заглушка, потом доработаете)
async function updateFishbowlOrderStatus(orderNumber, status) {
    console.log(`🔄 [Fishbowl TODO] Обновить статус заказа ${orderNumber} на ${status}`);
    // Здесь позже добавите реальный вызов Fishbowl API
    // Для сохранения лога:
    const logEntry = {
        timestamp: new Date().toISOString(),
        orderNumber,
        status,
        action: 'pending_fishbowl_update'
    };
    fs.appendFileSync('fishbowl_updates.log', JSON.stringify(logEntry) + '\n');
}

// ===== ENDPOINTS =====

// ГЛАВНЫЙ Webhook для ShipStation
app.post('/webhook/shipstation', async (req, res) => {
    console.log('\n=== ПОЛУЧЕН ВЕБХУК ОТ SHIPSTATION ===');
    console.log('Payload:', req.body);
    
    // Сразу отвечаем 200, чтобы ShipStation не повторял отправку
    res.status(200).json({ status: 'received' });
    
    try {
        const { resource_url, resource_type } = req.body;
        
        if (resource_url && resource_type === 'FULFILLMENT_SHIPPED' || resource_url && resource_type === 'SHIP_NOTIFY') {
            // 1. Получаем полные данные об отправлении
            const shipmentData = await fetchShipmentData(resource_url);
            
            // 2. Сохраняем полученные данные в файл для отладки
            fs.appendFileSync('shipments.log', 
                JSON.stringify({ timestamp: new Date().toISOString(), data: shipmentData }, null, 2) + '\n---\n'
            );
            
            // 3. Анализируем полученные данные
            console.log('\n📦 ДЕТАЛИ ОТГРУЗКИ:');
            
            // ShipmentData может содержать shipments массив или быть самим массивом
            const shipments = shipmentData.fulfillments || (Array.isArray(shipmentData) ? shipmentData : [shipmentData]);
            
            if (Array.isArray(shipments) && shipments.length > 0) {
                for (const shipment of shipments) {
                    console.log(`\n--- Отгрузка ---`);
                    console.log(`📦 Order ID: ${shipment.orderId}`);
                    console.log(`🔢 Order Number: ${shipment.orderNumber}`);
                    console.log(`📅 Ship Date: ${shipment.shipDate}`);
                    console.log(`🏷️ Tracking Number: ${shipment.trackingNumber}`);
                    console.log(`🚚 Carrier: ${shipment.carrierCode}`);
                    
                    // 4. Обновляем статус в Fishbowl
                    if (shipment.orderNumber) {
                        await updateFishbowlOrderStatus(shipment.orderNumber, 'shipped');
                    }
                }
            } else {
                console.log('⚠️ Нет данных об отгрузках в ответе');
                console.log('Полученные данные:', JSON.stringify(shipmentData, null, 2));
            }
            
        } else {
            console.log('⚠️ Нет resource_url или не SHIP_NOTIFY тип');
        }
        
    } catch (error) {
        console.error('❌ Ошибка обработки вебхука:', error);
        // Ошибку не бросаем, так как ответ уже отправлен
    }
});

// Тестовый GET endpoint
app.get('/health', (req, res) => {
    res.json({ 
        status: 'ok', 
        service: 'fishbowl-webhook',
        timestamp: new Date().toISOString()
    });
});

// ===== ЗАПУСК СЕРВЕРА =====
app.listen(PORT, () => {
    console.log(`🚀 Сервер запущен на http://localhost:${PORT}`);
    console.log(`📡 Ожидаю вебхуки на:`);
    console.log(`   - http://localhost:${PORT}/webhook/fishbowl (для Fishbowl)`);
    console.log(`   - http://localhost:${PORT}/webhook/shipstation (для ShipStation)`);
    console.log(`🏥 Проверка здоровья: http://localhost:${PORT}/health`);
});