import fetch from "node-fetch";
import 'dotenv/config';

const API_KEY = process.env.API_KEY;
const API_SECRET = process.env.API_SECRET;

const auth = Buffer.from(`${API_KEY}:${API_SECRET}`).toString("base64");



const params = new URLSearchParams({
    sortBy: 'modifyDate',
    sortDir: 'Desc',
    pageSize: 10
});

const res = await fetch(`https://ssapi.shipstation.com/orders?${params}`, {
    headers: {
        "Authorization": `Basic ${auth}`
    }
});

const data = await res.json();
console.log(data);
