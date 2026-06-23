// ============================================
// CONFIGURATION FILE - SPAR Dynamics 365
// ============================================

// IMPORTANT: This points to your Render Web Service
// This URL NEVER changes - only update if you redeploy the Web Service
const API_URL = 'https://spar-etl-receiver.onrender.com';

// Keep Cloudflare URL for reference (not used directly)
const CLOUDFLARE_URL = API_URL;

if (typeof window !== 'undefined') {
    window.API_URL = API_URL;
    window.CLOUDFLARE_URL = CLOUDFLARE_URL;
}

console.log('📡 API URL:', API_URL);
