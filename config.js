// ============================================
// STUDENT CONFIGURATION FILE
// ============================================
// This file reads your Supabase credentials from config.public.json.
// config.public.json contains values that are SAFE to commit:
//   - Supabase URL
//   - Supabase anon key (protected by Row Level Security)
//
// SECRET values (API keys, service keys) go in config.secret.json
// which is git-ignored and NEVER committed.

// Default placeholder config — overwritten when config.public.json loads
const SUPABASE_CONFIG = {
    url: 'YOUR_SUPABASE_URL_HERE',
    anonKey: 'YOUR_SUPABASE_ANON_KEY_HERE'
};

// Load config.public.json and update SUPABASE_CONFIG
fetch('config.public.json')
    .then(response => {
        if (!response.ok) throw new Error('config.public.json not found');
        return response.json();
    })
    .then(config => {
        if (config.SUPABASE_URL) SUPABASE_CONFIG.url = config.SUPABASE_URL;
        if (config.SUPABASE_ANON_KEY) SUPABASE_CONFIG.anonKey = config.SUPABASE_ANON_KEY;
        // Let app.js attach its listener before announcing that config is ready.
        // The fetch can complete from cache while the browser is still parsing
        // index.html, before app.js has registered its listener.
        setTimeout(() => window.dispatchEvent(new Event('config-loaded')), 0);
    })
    .catch(err => {
        console.warn('⚠️ Could not load config.public.json:', err.message);
        console.warn('   Create config.public.json with your Supabase URL and anon key.');
    });
