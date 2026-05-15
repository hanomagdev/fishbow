import express from 'express';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import fetch from 'node-fetch';
import 'dotenv/config';
import fs from 'fs';

// ===== КОНФИГУРАЦИЯ =====
const app = express();
const PORT = 3000;

// Fishbowl API конфигурация (хранятся в .env файле)
const FISHBOWL_URL = process.env.FISHBOWL_URL || 'http://localhost:2456/api';
const FISHBOWL_USERNAME = process.env.FISHBOWL_USERNAME;
const FISHBOWL_PASSWORD = process.env.FISHBOWL_PASSWORD;

// ShipStation API ключи (хранятся в .env файле)
const SHIPSTATION_API_KEY = process.env.SHIPSTATION_API_KEY;
const SHIPSTATION_API_SECRET = process.env.SHIPSTATION_API_SECRET;

// Basic Auth для ShipStation
const shipstationAuth = Buffer.from(`${SHIPSTATION_API_KEY}:${SHIPSTATION_API_SECRET}`).toString('base64');

// Хранилище для токена Fishbowl
let fishbowlToken = null;
let tokenExpiryTime = null;

// ===== MIDDLEWARE =====
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Логгер всех запросов
app.use((req, res, next) => {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
    next();
});

// ===== ФУНКЦИИ ДЛЯ РАБОТЫ С FISHBOWL API =====

// 1. Логин в Fishbowl и получение токена
async function loginToFishbowl() {
    try {
        console.log('🔐 Выполняю вход в Fishbowl API...');

        const response = await fetch(`${FISHBOWL_URL}/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                "appName": "FishbowlAutoShip",
                "appDescription": "Automatic order fulfillment script for pickable orders",
                "appId": 2286,
                username: FISHBOWL_USERNAME,
                password: FISHBOWL_PASSWORD
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // Предполагаем, что токен приходит в поле token или access_token
        // В зависимости от реальной структуры ответа Fishbowl
        fishbowlToken = data.token || data.access_token;

        // Устанавливаем время истечения токена (обычно 1 час)
        tokenExpiryTime = Date.now() + 60 * 60 * 1000;

        console.log('✅ Успешный вход в Fishbowl, токен получен');
        return fishbowlToken;

    } catch (error) {
        console.error('❌ Ошибка при логине в Fishbowl:', error);
        throw error;
    }
}

// Проверка и обновление токена при необходимости
async function ensureValidToken() {
    if (!fishbowlToken || (tokenExpiryTime && Date.now() >= tokenExpiryTime - 5 * 60 * 1000)) {
        console.log('🔄 Токен устарел или отсутствует, выполняю повторный вход...');
        await loginToFishbowl();
    }
    return fishbowlToken;
}

// 2. Поиск отгрузки по номеру заказа
async function findShipmentByOrderNumber(orderNumber) {
    try {
        const token = await ensureValidToken();

        console.log(`🔍 Ищу отгрузку с номером заказа: ${orderNumber}`);

        const response = await fetch(`${FISHBOWL_URL}/shipments?orderNumber=${orderNumber}`, {
            method: 'GET',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // Анализируем ответ - может быть массивом или объектом с полем shipments
        const shipments = data.results || (Array.isArray(data) ? data : [data]);

        if (shipments && shipments.length > 0) {
            console.log(`✅ Найдена отгрузка: ID=${shipments[0].id}`);
            return shipments[0]; // Возвращаем первую найденную отгрузку
        } else {
            console.log(`⚠️ Отгрузка с номером ${orderNumber} не найдена`);
            return null;
        }

    } catch (error) {
        console.error(`❌ Ошибка при поиске отгрузки ${orderNumber}:`, error);
        throw error;
    }
}

// 3. Отгрузка товара в Fishbowl
async function shipOrder(shipmentId, shipmentData = {}) {
    try {
        const token = await ensureValidToken();

        console.log(`🚚 Отгружаю товар для shipment ID: ${shipmentId}`);

        const response = await fetch(`${FISHBOWL_URL}/shipments/${shipmentId}/ship`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                // Дополнительные параметры, если нужны
                shipDate: new Date().toISOString(),
                ...shipmentData
            })
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        const result = await response.json();
        console.log(`✅ Успешная отгрузка для shipment ${shipmentId}`);
        return result;

    } catch (error) {
        console.error(`❌ Ошибка при отгрузке shipment ${shipmentId}:`, error);
        throw error;
    }
}

// 4. Комбинированная функция: полный процесс отгрузки по номеру заказа
async function processOrderShipment(orderNumber, additionalData = {}) {
    try {
        console.log(`\n========== НАЧАЛО ОБРАБОТКИ ОТГРУЗКИ ДЛЯ ЗАКАЗА ${orderNumber} ==========`);

        // Шаг 1: Находим отгрузку по номеру заказа
        const shipment = await findShipmentByOrderNumber(orderNumber);

        if (!shipment) {
            throw new Error(`Отгрузка для заказа ${orderNumber} не найдена`);
        }

        // Шаг 2: Выполняем отгрузку
        const result = await shipOrder(shipment.id, additionalData);

        // Логируем успешную операцию
        const logEntry = {
            timestamp: new Date().toISOString(),
            orderNumber,
            shipmentId: shipment.id,
            status: 'shipped',
            result
        };
        fs.appendFileSync('fishbowl_shipments.log', JSON.stringify(logEntry, null, 2) + '\n---\n');

        console.log(`========== ЗАВЕРШЕНИЕ ОБРАБОТКИ ДЛЯ ЗАКАЗА ${orderNumber} ==========\n`);

        return {
            success: true,
            orderNumber,
            shipmentId: shipment.id,
            result
        };

    } catch (error) {
        console.error(`❌ Ошибка при обработке заказа ${orderNumber}:`, error);

        // Логируем ошибку
        const errorLog = {
            timestamp: new Date().toISOString(),
            orderNumber,
            error: error.message,
            stack: error.stack
        };
        fs.appendFileSync('fishbowl_errors.log', JSON.stringify(errorLog, null, 2) + '\n---\n');

        return {
            success: false,
            orderNumber,
            error: error.message
        };
    }
}

// Функция обновления статуса в Fishbowl (использует новую логику)
async function updateFishbowlOrderStatus(orderNumber, status) {
    if (status === 'shipped') {
        console.log(`🔄 Обновляю статус заказа ${orderNumber} на "отгружен" в Fishbowl...`);
        const result = await processOrderShipment(orderNumber);
        return result;
    } else {
        console.log(`ℹ️ Статус ${status} для заказа ${orderNumber} не требует отгрузки через Fishbowl API`);
        // Сохраняем в лог для других статусов
        const logEntry = {
            timestamp: new Date().toISOString(),
            orderNumber,
            status,
            action: 'status_update_only'
        };
        fs.appendFileSync('fishbowl_updates.log', JSON.stringify(logEntry) + '\n');
        return { success: true, status: 'logged' };
    }
}

// ===== ФУНКЦИИ ДЛЯ РАБОТЫ С SHIPSTATION =====

// Функция для запроса данных из ShipStation по resource_url
async function fetchShipmentData(resourceUrl) {
    try {
        console.log(`🔗 Запрашиваю данные из ShipStation: ${resourceUrl}`);

        const response = await fetch(resourceUrl, {
            method: 'GET',
            headers: {
                'Authorization': `Basic ${shipstationAuth}`,
                'Content-Type': 'application/json'
            }
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log(`✅ Получены данные об отправлении из ShipStation`);
        return data;

    } catch (error) {
        console.error(`❌ Ошибка при запросе данных из ShipStation:`, error);
        throw error;
    }
}

// ===== ENDPOINTS =====

// Тестовый endpoint для ручного вызова отгрузки в Fishbowl
app.post('/api/fishbowl/ship-by-order', async (req, res) => {
    const { orderNumber, ...additionalData } = req.body;

    if (!orderNumber) {
        return res.status(400).json({
            success: false,
            error: 'Необходимо указать orderNumber'
        });
    }

    try {
        const result = await processOrderShipment(orderNumber, additionalData);
        res.json(result);
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// Endpoint для проверки статуса токена Fishbowl
app.get('/api/fishbowl/status', async (req, res) => {
    try {
        await ensureValidToken();
        res.json({
            success: true,
            hasToken: !!fishbowlToken,
            tokenValid: fishbowlToken && (!tokenExpiryTime || Date.now() < tokenExpiryTime)
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

// ГЛАВНЫЙ Webhook для ShipStation
app.post('/webhook/shipstation', async (req, res) => {
    console.log('\n=== ПОЛУЧЕН ВЕБХУК ОТ SHIPSTATION ===');
    console.log('Payload:', JSON.stringify(req.body, null, 2));

    // Сразу отвечаем 200, чтобы ShipStation не повторял отправку
    res.status(200).json({ status: 'received' });

    try {
        const { resource_url, resource_type } = req.body;

        if (resource_url && (resource_type === 'FULFILLMENT_SHIPPED' || resource_type === 'SHIP_NOTIFY')) {
            // 1. Получаем полные данные об отправлении
            const shipmentData = await fetchShipmentData(resource_url);

            // 2. Сохраняем полученные данные в файл для отладки
            fs.appendFileSync('shipments.log',
                JSON.stringify({ timestamp: new Date().toISOString(), data: shipmentData }, null, 2) + '\n---\n'
            );

            // 3. Анализируем полученные данные
            console.log('\n📦 ДЕТАЛИ ОТГРУЗКИ:');

            // ShipmentData может содержать fulfillments массив или быть самим массивом
            const shipments = shipmentData.fulfillments || (Array.isArray(shipmentData) ? shipmentData : [shipmentData]);

            if (Array.isArray(shipments) && shipments.length > 0) {
                for (const shipment of shipments) {
                    console.log(`\n--- Отгрузка ---`);
                    console.log(`📦 Order ID: ${shipment.orderId}`);
                    console.log(`🔢 Order Number: ${shipment.orderNumber}`);
                    console.log(`📅 Ship Date: ${shipment.shipDate}`);
                    console.log(`🏷️ Tracking Number: ${shipment.trackingNumber}`);
                    console.log(`🚚 Carrier: ${shipment.carrierCode}`);

                    // 4. Обновляем статус в Fishbowl (автоматически выполнит отгрузку)
                    if (shipment.orderNumber) {
                        await updateFishbowlOrderStatus(shipment.orderNumber, 'shipped');
                    }
                }
            } else {
                console.log('⚠️ Нет данных об отгрузках в ответе');
                console.log('Полученные данные:', JSON.stringify(shipmentData, null, 2));
            }

        } else {
            console.log('⚠️ Нет resource_url или не поддерживаемый тип');
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
        service: 'fishbowl-shipstation-integration',
        timestamp: new Date().toISOString(),
        fishbowlConnected: !!fishbowlToken
    });
});

// Тестовый endpoint для проверки отгрузки в Fishbowl
app.post('/test/ship-order', async (req, res) => {
    const { orderNumber } = req.body;

    if (!orderNumber) {
        return res.status(400).json({ error: 'orderNumber is required' });
    }

    try {
        const result = await processOrderShipment(orderNumber);
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ===== ИНИЦИАЛИЗАЦИЯ ПРИ ЗАПУСКЕ =====
async function initialize() {
    console.log('🔧 Инициализация сервера...');

    // Проверяем наличие необходимых переменных окружения
    if (!FISHBOWL_USERNAME || !FISHBOWL_PASSWORD) {
        console.error('❌ Ошибка: Не заданы FISHBOWL_USERNAME и FISHBOWL_PASSWORD в .env файле');
    } else {
        // Пытаемся получить токен при старте
        try {
            await loginToFishbowl();
            console.log('✅ Fishbowl API готов к работе');
        } catch (error) {
            console.error('⚠️ Не удалось подключиться к Fishbowl при старте:', error.message);
        }
    }

    if (!SHIPSTATION_API_KEY || !SHIPSTATION_API_SECRET) {
        console.error('❌ Ошибка: Не заданы SHIPSTATION_API_KEY и SHIPSTATION_API_SECRET в .env файле');
    } else {
        console.log('✅ ShipStation API настроен');
    }
}

// ===== ЗАПУСК СЕРВЕРА =====
app.listen(PORT, async () => {
    console.log(`🚀 Сервер запущен на http://localhost:${PORT}`);
    console.log(`📡 Ожидаю вебхуки на:`);
    console.log(`   - http://localhost:${PORT}/webhook/shipstation (для ShipStation)`);
    console.log(`   - http://localhost:${PORT}/api/fishbowl/ship-by-order (для ручной отгрузки)`);
    console.log(`🏥 Проверка здоровья: http://localhost:${PORT}/health`);

    await initialize();
});