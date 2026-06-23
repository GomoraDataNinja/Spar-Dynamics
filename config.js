// config.js
const API_URL = 'https://spar-erp-2026.onrender.com';
const CLOUDFLARE_URL = API_URL;

if (typeof window !== 'undefined') {
    window.API_URL = API_URL;
    window.CLOUDFLARE_URL = CLOUDFLARE_URL;
}

console.log('📡 API URL:', API_URL);
