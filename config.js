// ============================================
// CONFIGURATION FILE - SPAR Dynamics 365
// ============================================

// YOUR RENDER BACKEND URL - CHANGE THIS TO YOUR ACTUAL URL
// From your screenshot, you have these services:
// - spar-erp-2026 (backend)
// - spar-dynamics-erp_2 (backend)
// Use whichever one is your Python backend

const API_URL = 'https://spar-erp-2026.onrender.com';

// For local development
// const API_URL = 'http://localhost:8000';

const CLOUDFLARE_URL = API_URL;

if (typeof window !== 'undefined') {
    window.API_URL = API_URL;
    window.CLOUDFLARE_URL = CLOUDFLARE_URL;
}

console.log('📡 API URL:', API_URL);
console.log('🌐 Environment:', window.location.hostname);
