/**
 * Antigravity Remote Controller - Configuration
 * Ultra-Premium Enterprise Configuration System
 */

const path = require('path');

module.exports = {
    // Server Configuration
    server: {
        port: process.env.PORT || 3000,
        host: '0.0.0.0',
        corsOrigins: ['*']
    },

    // Authentication Configuration
    auth: {
        // Secret key for JWT (change this in production!)
        jwtSecret: process.env.JWT_SECRET || 'antigravity-remote-secret-key-change-me',
        // Token expiration (24 hours)
        tokenExpiration: '24h',
        // Simple PIN for quick access (optional)
        accessPin: process.env.ACCESS_PIN || '1234',
        // Rate limiting
        rateLimit: {
            windowMs: 15 * 60 * 1000, // 15 minutes
            max: 100 // limit each IP to 100 requests per windowMs
        }
    },

    // Tunnel Configuration
    tunnel: {
        // Primary tunnel provider: 'cloudflare' or 'ngrok'
        provider: process.env.TUNNEL_PROVIDER || 'ngrok',
        // ngrok auth token (optional, for custom domains)
        ngrokAuthToken: process.env.NGROK_AUTH_TOKEN || '',
        // Cloudflare tunnel token
        cloudflareToken: process.env.CLOUDFLARE_TOKEN || '',
        // Auto-start tunnel on server start
        autoStart: true
    },

    // Window Manager Configuration
    windowManager: {
        // Maximum concurrent windows
        maxWindows: 10,
        // Shell to use
        shell: process.platform === 'win32' ? 'powershell.exe' : 'bash',
        // Shell arguments
        shellArgs: process.platform === 'win32'
            ? ['-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass']
            : [],
        // Default terminal size
        defaultCols: 120,
        defaultRows: 30,
        // Output buffer size (lines to keep in memory)
        outputBufferSize: 1000,
        // Timeout for idle windows (ms) - 0 = no timeout
        idleTimeout: 0
    },

    // UI Configuration
    ui: {
        theme: 'dark-neon',
        animationsEnabled: true,
        soundEnabled: false
    },

    // Logging Configuration
    logging: {
        level: process.env.LOG_LEVEL || 'info',
        file: path.join(__dirname, 'logs', 'server.log')
    }
};
