// ============================================
// CONFIGURATION FILE - SPAR Dynamics 365
// ============================================

// Your Render Backend URL (NEVER changes)
const API_URL = 'https://spar-erp-2026.onrender.com';

// Keep Cloudflare URL for reference (not used directly)
const CLOUDFLARE_URL = API_URL;

if (typeof window !== 'undefined') {
    window.API_URL = API_URL;
    window.CLOUDFLARE_URL = CLOUDFLARE_URL;
}

console.log('📡 API URL:', API_URL);
