/**
 * Antigravity Remote Controller - Main Server
 * Enterprise-Grade Real-time WebSocket Server
 */

const express = require('express');
const { createServer } = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const path = require('path');

const config = require('./config');
const authManager = require('./auth');
const windowManager = require('./window-manager');

// Initialize Express
const app = express();
const httpServer = createServer(app);

// Initialize Socket.IO
const io = new Server(httpServer, {
    cors: {
        origin: config.server.corsOrigins,
        methods: ['GET', 'POST']
    },
    pingTimeout: 60000,
    pingInterval: 25000
});

// ===========================================
// Express Middleware
// ===========================================

// Security headers
app.use(helmet({
    contentSecurityPolicy: false // Disable for development
}));

// CORS
app.use(cors({
    origin: config.server.corsOrigins
}));

// Rate limiting
app.use(rateLimit({
    windowMs: config.auth.rateLimit.windowMs,
    max: config.auth.rateLimit.max,
    message: { error: 'Too many requests, please try again later.' }
}));

// JSON parsing
app.use(express.json());

// Static files
app.use(express.static(path.join(__dirname, 'public')));

// ===========================================
// REST API Routes
// ===========================================

// Health check
app.get('/api/health', (req, res) => {
    res.json({
        status: 'ok',
        uptime: process.uptime(),
        windows: windowManager.getAllWindows().length
    });
});

// Authenticate with PIN
app.post('/api/auth', (req, res) => {
    const { pin } = req.body;

    if (!pin) {
        return res.status(400).json({ error: 'PIN required' });
    }

    if (!authManager.verifyPin(pin)) {
        return res.status(401).json({ error: 'Invalid PIN' });
    }

    const clientId = `client_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const token = authManager.generateToken(clientId, {
        ip: req.ip,
        userAgent: req.headers['user-agent']
    });

    res.json({ token, clientId });
});

// Get windows list (requires auth)
app.get('/api/windows', authManager.expressMiddleware(), (req, res) => {
    res.json({ windows: windowManager.getAllWindows() });
});

// ===========================================
// Socket.IO Authentication & Events
// ===========================================

// Apply authentication middleware
io.use(authManager.socketMiddleware());

// Connection handler
io.on('connection', (socket) => {
    console.log(`Client connected: ${socket.clientId}`);

    // Send token if authenticated via PIN
    if (socket.token) {
        socket.emit('auth:token', { token: socket.token });
    }

    // Send current windows state
    socket.emit('windows:list', {
        windows: windowManager.getAllWindows()
    });

    // =========================================
    // Window Management Events
    // =========================================

    // Create new window
    socket.on('window:create', (options = {}) => {
        try {
            const window = windowManager.createWindow(options);

            // Send buffer history
            socket.emit('window:created', {
                window: window.getInfo(),
                buffer: window.getBuffer()
            });

            // Broadcast to all clients
            socket.broadcast.emit('windows:list', {
                windows: windowManager.getAllWindows()
            });
        } catch (error) {
            socket.emit('error', { message: error.message });
        }
    });

    // Close window
    socket.on('window:close', ({ windowId }) => {
        if (windowManager.removeWindow(windowId)) {
            io.emit('window:closed', { windowId });
            io.emit('windows:list', {
                windows: windowManager.getAllWindows()
            });
        }
    });

    // Write to window
    socket.on('window:input', ({ windowId, data }) => {
        if (!windowManager.writeToWindow(windowId, data)) {
            socket.emit('error', { message: `Window ${windowId} not found or not running` });
        }
    });

    // Send command (auto-appends newline)
    socket.on('window:command', ({ windowId, command }) => {
        if (!windowManager.writeToWindow(windowId, command + '\r\n')) {
            socket.emit('error', { message: `Window ${windowId} not found or not running` });
        }
    });

    // Resize window
    socket.on('window:resize', ({ windowId, cols, rows }) => {
        windowManager.resizeWindow(windowId, cols, rows);
    });

    // Get window buffer
    socket.on('window:getBuffer', ({ windowId, limit }) => {
        const buffer = windowManager.getWindowBuffer(windowId, limit);
        socket.emit('window:buffer', { windowId, buffer });
    });

    // Get all windows
    socket.on('windows:get', () => {
        socket.emit('windows:list', {
            windows: windowManager.getAllWindows()
        });
    });

    // =========================================
    // Connection Events
    // =========================================

    socket.on('ping', () => {
        socket.emit('pong', { timestamp: Date.now() });
    });

    socket.on('disconnect', (reason) => {
        console.log(`Client disconnected: ${socket.clientId} (${reason})`);
        authManager.removeSession(socket.clientId);
    });
});

// ===========================================
// Window Manager Events -> Socket.IO
// ===========================================

windowManager.on('output', ({ windowId, data }) => {
    io.emit('window:output', { windowId, data });
});

windowManager.on('exit', ({ windowId, exitCode, signal }) => {
    io.emit('window:exit', { windowId, exitCode, signal });
});

windowManager.on('error', ({ windowId, error }) => {
    io.emit('window:error', { windowId, error });
});

windowManager.on('removed', ({ windowId }) => {
    io.emit('window:removed', { windowId });
});

// ===========================================
// Server Start
// ===========================================

function startServer(port = config.server.port) {
    return new Promise((resolve) => {
        httpServer.listen(port, config.server.host, () => {
            console.log(`\n🚀 Antigravity Remote Server running on port ${port}`);
            resolve({ port, server: httpServer, io });
        });
    });
}

// Graceful shutdown
function shutdown() {
    console.log('\nShutting down...');
    windowManager.destroyAll();
    httpServer.close(() => {
        console.log('Server closed');
        process.exit(0);
    });
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

// Export for launcher
module.exports = { startServer, app, io, httpServer };

// Direct run
if (require.main === module) {
    startServer();
}
