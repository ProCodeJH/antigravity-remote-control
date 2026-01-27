/**
 * Antigravity Remote Controller - Authentication System
 * Enterprise-Grade JWT Authentication
 */

const jwt = require('jsonwebtoken');
const config = require('./config');

class AuthManager {
    constructor() {
        this.activeSessions = new Map();
    }

    /**
     * Generate JWT token for authenticated user
     */
    generateToken(clientId, deviceInfo = {}) {
        const payload = {
            clientId,
            deviceInfo,
            iat: Date.now()
        };

        const token = jwt.sign(payload, config.auth.jwtSecret, {
            expiresIn: config.auth.tokenExpiration
        });

        this.activeSessions.set(clientId, {
            token,
            deviceInfo,
            connectedAt: new Date(),
            lastActive: new Date()
        });

        return token;
    }

    /**
     * Verify JWT token
     */
    verifyToken(token) {
        try {
            const decoded = jwt.verify(token, config.auth.jwtSecret);
            return { valid: true, payload: decoded };
        } catch (error) {
            return { valid: false, error: error.message };
        }
    }

    /**
     * Verify PIN access
     */
    verifyPin(pin) {
        return pin === config.auth.accessPin;
    }

    /**
     * Socket.IO authentication middleware
     */
    socketMiddleware() {
        return (socket, next) => {
            const token = socket.handshake.auth.token;
            const pin = socket.handshake.auth.pin;

            // Try token authentication first
            if (token) {
                const result = this.verifyToken(token);
                if (result.valid) {
                    socket.clientId = result.payload.clientId;
                    socket.authenticated = true;
                    return next();
                }
            }

            // Try PIN authentication
            if (pin && this.verifyPin(pin)) {
                const clientId = `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                socket.clientId = clientId;
                socket.authenticated = true;
                socket.token = this.generateToken(clientId, {
                    userAgent: socket.handshake.headers['user-agent'],
                    ip: socket.handshake.address
                });
                return next();
            }

            // No valid authentication
            return next(new Error('Authentication required'));
        };
    }

    /**
     * Express middleware for REST API
     */
    expressMiddleware() {
        return (req, res, next) => {
            const authHeader = req.headers.authorization;

            if (!authHeader || !authHeader.startsWith('Bearer ')) {
                return res.status(401).json({ error: 'No token provided' });
            }

            const token = authHeader.split(' ')[1];
            const result = this.verifyToken(token);

            if (!result.valid) {
                return res.status(401).json({ error: 'Invalid token' });
            }

            req.clientId = result.payload.clientId;
            next();
        };
    }

    /**
     * Update session activity
     */
    updateActivity(clientId) {
        const session = this.activeSessions.get(clientId);
        if (session) {
            session.lastActive = new Date();
        }
    }

    /**
     * Remove session
     */
    removeSession(clientId) {
        this.activeSessions.delete(clientId);
    }

    /**
     * Get all active sessions
     */
    getActiveSessions() {
        return Array.from(this.activeSessions.entries()).map(([id, session]) => ({
            clientId: id,
            ...session,
            token: undefined // Don't expose tokens
        }));
    }
}

module.exports = new AuthManager();
