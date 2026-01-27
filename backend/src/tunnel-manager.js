/**
 * Antigravity Remote Controller - Tunnel Manager
 * Fixed Network Tunneling with Better Error Handling
 */

const config = require('./config');

class TunnelManager {
    constructor() {
        this.tunnel = null;
        this.publicUrl = null;
        this.isConnected = false;
        this.provider = config.tunnel.provider;
    }

    /**
     * Start tunnel connection using ngrok
     */
    async connect(port) {
        if (this.isConnected) {
            return this.publicUrl;
        }

        console.log('Attempting to connect ngrok tunnel...');

        try {
            const ngrok = require('ngrok');

            // Kill any existing ngrok processes first
            try {
                await ngrok.kill();
            } catch (e) {
                // Ignore
            }

            const options = {
                addr: port,
                proto: 'http',
                region: 'ap' // Asia Pacific for better latency in Korea
            };

            // Add auth token if available
            if (config.tunnel.ngrokAuthToken) {
                options.authtoken = config.tunnel.ngrokAuthToken;
            }

            this.publicUrl = await ngrok.connect(options);
            this.isConnected = true;
            this.provider = 'ngrok';

            console.log(`ngrok tunnel connected: ${this.publicUrl}`);
            return this.publicUrl;

        } catch (error) {
            console.error('ngrok connection failed:', error.message);
            throw error;
        }
    }

    /**
     * Disconnect tunnel
     */
    async disconnect() {
        if (!this.isConnected) return;

        try {
            const ngrok = require('ngrok');
            await ngrok.kill();
        } catch (error) {
            console.error('Error disconnecting tunnel:', error);
        }

        this.isConnected = false;
        this.publicUrl = null;
    }

    /**
     * Get connection info
     */
    getInfo() {
        return {
            isConnected: this.isConnected,
            provider: this.provider,
            publicUrl: this.publicUrl
        };
    }
}

module.exports = new TunnelManager();
