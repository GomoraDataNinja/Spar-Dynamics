// ============================================
// CONFIGURATION FILE - SPAR Dynamics 365
// ============================================

// Your Cloudflare URL - Change this when URL changes
const CLOUDFLARE_URL = 'http://localhost:8000';

// For Cloudflare tunnel, use:
const CLOUDFLARE_URL = 'https://venues-antivirus-occupied-procurement.trycloudflare.com';

const API_URL = CLOUDFLARE_URL;

if (typeof window !== 'undefined') {
    window.API_URL = API_URL;
    window.CLOUDFLARE_URL = CLOUDFLARE_URL;
}

console.log('🌐 Cloudflare URL:', CLOUDFLARE_URL);
console.log('📡 API URL:', API_URL);