// ============================================
// CONFIGURATION FILE - SPAR Dynamics 365
// ============================================

// Your Cloudflare URL (exposes your local SQL Server)
const CLOUDFLARE_URL = 'https://distinguished-geography-mlb-hebrew.trycloudflare.com';

// Use Cloudflare URL as the main API URL
const API_URL = CLOUDFLARE_URL;

// If you want to use Render API instead, uncomment the line below
// const API_URL = 'https://spar-etl-receiver.onrender.com';

if (typeof window !== 'undefined') {
    window.API_URL = API_URL;
    window.CLOUDFLARE_URL = CLOUDFLARE_URL;
}

console.log('🌐 Cloudflare URL:', CLOUDFLARE_URL);
console.log('📡 API URL:', API_URL);
