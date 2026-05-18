import express from 'express';
import { fileURLToPath } from 'url';
import { dirname } from 'path';
import fetch from 'node-fetch';
import 'dotenv/config';
import fs from 'fs';

const app = express();
const PORT = 3000;

const FISHBOWL_URL = process.env.FISHBOWL_URL || 'http://localhost:2456/api';
const FISHBOWL_USERNAME = process.env.FISHBOWL_USERNAME;
const FISHBOWL_PASSWORD = process.env.FISHBOWL_PASSWORD;
const SHIPSTATION_API_KEY = process.env.SHIPSTATION_API_KEY;
const SHIPSTATION_API_SECRET = process.env.SHIPSTATION_API_SECRET;

const shipstationAuth = Buffer.from(`${SHIPSTATION_API_KEY}:${SHIPSTATION_API_SECRET}`).toString('base64');

let fishbowlToken = null;
let tokenExpiryTime = null;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use((req, res, next) => {
    console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
    next();
});

async function loginToFishbowl() {
    const response = await fetch(`${FISHBOWL_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            appName: "FishbowlAutoShip",
            appDescription: "Automatic order fulfillment script for pickable orders",
            appId: 2286,
            username: FISHBOWL_USERNAME,
            password: FISHBOWL_PASSWORD
        })
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    fishbowlToken = data.token || data.access_token;
    tokenExpiryTime = Date.now() + 60 * 60 * 1000;
    
    return fishbowlToken;
}

async function ensureValidToken() {
    if (!fishbowlToken || (tokenExpiryTime && Date.now() >= tokenExpiryTime - 5 * 60 * 1000)) {
        await loginToFishbowl();
    }
    return fishbowlToken;
}

async function findShipmentByOrderNumber(orderNumber) {
    const token = await ensureValidToken();
    
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
    const shipments = data.results || (Array.isArray(data) ? data : [data]);

    return shipments?.[0] || null;
}

async function shipOrder(shipmentId, shipmentData = {}) {
    const token = await ensureValidToken();

    const response = await fetch(`${FISHBOWL_URL}/shipments/${shipmentId}/ship`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            shipDate: new Date().toISOString(),
            ...shipmentData
        })
    });

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
    }

    return await response.json();
}

async function processOrderShipment(orderNumber, additionalData = {}) {
    try {
        const shipment = await findShipmentByOrderNumber(orderNumber);

        if (!shipment) {
            throw new Error(`Shipment for order ${orderNumber} not found`);
        }

        const result = await shipOrder(shipment.id, additionalData);

        const logEntry = {
            timestamp: new Date().toISOString(),
            orderNumber,
            shipmentId: shipment.id,
            status: 'shipped',
            result
        };
        fs.appendFileSync('fishbowl_shipments.log', JSON.stringify(logEntry, null, 2) + '\n---\n');

        return {
            success: true,
            orderNumber,
            shipmentId: shipment.id,
            result
        };

    } catch (error) {
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

async function updateFishbowlOrderStatus(orderNumber, status) {
    if (status === 'shipped') {
        return await processOrderShipment(orderNumber);
    } else {
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

async function fetchShipmentData(resourceUrl) {
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

    return await response.json();
}

app.post('/api/fishbowl/ship-by-order', async (req, res) => {
    const { orderNumber, ...additionalData } = req.body;

    if (!orderNumber) {
        return res.status(400).json({
            success: false,
            error: 'orderNumber is required'
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

app.post('/webhook/shipstation', async (req, res) => {
    console.log('\n=== SHIPSTATION WEBHOOK RECEIVED ===');
    
    res.status(200).json({ status: 'received' });

    try {
        const { resource_url, resource_type } = req.body;

        if (resource_url && (resource_type === 'FULFILLMENT_SHIPPED' || resource_type === 'SHIP_NOTIFY')) {
            const shipmentData = await fetchShipmentData(resource_url);
            
            fs.appendFileSync('shipments.log',
                JSON.stringify({ timestamp: new Date().toISOString(), data: shipmentData }, null, 2) + '\n---\n'
            );

            const shipments = shipmentData.fulfillments || (Array.isArray(shipmentData) ? shipmentData : [shipmentData]);

            if (Array.isArray(shipments) && shipments.length > 0) {
                for (const shipment of shipments) {
                    if (shipment.orderNumber) {
                        await updateFishbowlOrderStatus(shipment.orderNumber, 'shipped');
                    }
                }
            }
        }
    } catch (error) {
        console.error('Webhook processing error:', error);
    }
});

app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        service: 'fishbowl-shipstation-integration',
        timestamp: new Date().toISOString(),
        fishbowlConnected: !!fishbowlToken
    });
});

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

async function initialize() {
    if (!FISHBOWL_USERNAME || !FISHBOWL_PASSWORD) {
        console.error('Error: FISHBOWL_USERNAME and FISHBOWL_PASSWORD are not set in .env file');
    } else {
        try {
            await loginToFishbowl();
        } catch (error) {
            console.error('Failed to connect to Fishbowl on startup:', error.message);
        }
    }

    if (!SHIPSTATION_API_KEY || !SHIPSTATION_API_SECRET) {
        console.error('Error: SHIPSTATION_API_KEY and SHIPSTATION_API_SECRET are not set in .env file');
    }
}

app.listen(PORT, async () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log(`Webhook endpoint: http://localhost:${PORT}/webhook/shipstation`);
    console.log(`Health check: http://localhost:${PORT}/health`);

    await initialize();
});