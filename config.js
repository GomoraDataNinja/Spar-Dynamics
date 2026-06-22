// ============================================
// CONFIGURATION FILE - SPAR Dynamics 365
// ============================================

// Your Render Backend URL (after deploying on Render)
const API_URL = 'https://spar-etl-receiver.onrender.com';

// Your Cloudflare URL (for local testing)
const CLOUDFLARE_URL = 'https://mentioned-carolina-pump-inputs.trycloudflare.com';

if (typeof window !== 'undefined') {
    window.API_URL = API_URL;
    window.CLOUDFLARE_URL = CLOUDFLARE_URL;
}

console.log('🌐 Cloudflare URL:', CLOUDFLARE_URL);
console.log('📡 API URL:', API_URL);
